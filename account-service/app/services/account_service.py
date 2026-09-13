"""Idempotent local account operations persisted in Supabase PostgreSQL."""

from dataclasses import dataclass
import logging
from typing import Any
from uuid import uuid4

from psycopg import Connection

from app.database import AccountRepository
from app.schemas.accounts import AccountResponse, OperationResponse

logger = logging.getLogger(__name__)


class AccountServiceError(Exception):
    def __init__(
        self,
        *,
        transfer_id: str | None,
        status: str,
        error_code: str,
        message: str,
        http_status: int,
    ) -> None:
        super().__init__(message)
        self.transfer_id = transfer_id
        self.status = status
        self.error_code = error_code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class _LedgerResult:
    transfer_id: str
    account_id: str
    amount: int
    new_balance: int
    status: str

    def response(self) -> OperationResponse:
        return OperationResponse(
            transfer_id=self.transfer_id,
            account_id=self.account_id,
            amount=self.amount,
            new_balance=self.new_balance,
            status=self.status,
        )


class AccountService:
    def __init__(self, repository: AccountRepository) -> None:
        self.repository = repository

    def initialize(self) -> None:
        self.repository.initialize()

    @staticmethod
    def _account(
        connection: Connection[Any], account_id: str, *, lock: bool = False
    ) -> dict[str, Any]:
        lock_clause = " FOR UPDATE" if lock else ""
        account = connection.execute(
            f"""
            SELECT account_id, balance, currency
            FROM account.accounts
            WHERE account_id = %s{lock_clause}
            """,
            (account_id,),
        ).fetchone()
        if account is None:
            raise AccountServiceError(
                transfer_id=None,
                status="FAILED",
                error_code="ACCOUNT_NOT_FOUND",
                message="Account not found",
                http_status=404,
            )
        return account

    @staticmethod
    def _existing_operation(
        connection: Connection[Any], transfer_id: str, account_id: str, operation: str
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT transfer_id, account_id, amount, balance_after, status
            FROM account.ledger_entries
            WHERE transfer_id = %s AND account_id = %s AND operation = %s
            """,
            (transfer_id, account_id, operation),
        ).fetchone()

    @staticmethod
    def _assert_same_amount(existing: dict[str, Any], amount: int, transfer_id: str) -> None:
        if existing["amount"] != amount:
            raise AccountServiceError(
                transfer_id=transfer_id,
                status="FAILED",
                error_code="IDEMPOTENCY_CONFLICT",
                message="transfer_id was already used with a different amount",
                http_status=409,
            )

    def get_account(self, account_id: str) -> AccountResponse:
        with self.repository.transaction() as connection:
            account = self._account(connection, account_id)
            return AccountResponse(
                account_id=account["account_id"],
                balance=account["balance"],
                currency=account["currency"],
            )

    def debit(self, account_id: str, transfer_id: str, amount: int) -> OperationResponse:
        return self._apply(account_id, transfer_id, amount, "debit", "DEBITED", direction=-1)

    def credit(self, account_id: str, transfer_id: str, amount: int) -> OperationResponse:
        return self._apply(account_id, transfer_id, amount, "credit", "COMPLETED", direction=1)

    def _apply(
        self,
        account_id: str,
        transfer_id: str,
        amount: int,
        operation: str,
        status: str,
        direction: int,
    ) -> OperationResponse:
        with self.repository.transaction() as connection:
            # Lock before reading the ledger. A concurrent retry waits here and
            # then observes the operation already committed by the first request.
            account = self._account(connection, account_id, lock=True)
            existing = self._existing_operation(connection, transfer_id, account_id, operation)
            if existing is not None:
                self._assert_same_amount(existing, amount, transfer_id)
                return _LedgerResult(
                    transfer_id=str(existing["transfer_id"]),
                    account_id=existing["account_id"],
                    amount=existing["amount"],
                    new_balance=existing["balance_after"],
                    status=existing["status"],
                ).response()

            if direction < 0 and account["balance"] < amount:
                raise AccountServiceError(
                    transfer_id=transfer_id,
                    status="REJECTED_FUNDS",
                    error_code="INSUFFICIENT_FUNDS",
                    message="Insufficient funds",
                    http_status=409,
                )

            new_balance = account["balance"] + direction * amount
            connection.execute(
                """
                UPDATE account.accounts
                SET balance = %s, updated_at = now()
                WHERE account_id = %s
                """,
                (new_balance, account_id),
            )
            connection.execute(
                """
                INSERT INTO account.ledger_entries (
                    operation_id, transfer_id, account_id, operation, amount,
                    balance_after, status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                """,
                (
                    str(uuid4()),
                    transfer_id,
                    account_id,
                    operation,
                    amount,
                    new_balance,
                    status,
                ),
            )

        logger.info(
            "transfer_id=%s service=account-service operation=%s status=%s",
            transfer_id,
            operation,
            status,
        )
        return _LedgerResult(transfer_id, account_id, amount, new_balance, status).response()

    def compensate_debit(
        self, account_id: str, transfer_id: str, amount: int
    ) -> OperationResponse:
        return self._compensate(
            account_id, transfer_id, amount, original_operation="debit", direction=1
        )

    def compensate_credit(
        self, account_id: str, transfer_id: str, amount: int
    ) -> OperationResponse:
        return self._compensate(
            account_id, transfer_id, amount, original_operation="credit", direction=-1
        )

    def _compensate(
        self,
        account_id: str,
        transfer_id: str,
        amount: int,
        original_operation: str,
        direction: int,
    ) -> OperationResponse:
        compensation_operation = f"{original_operation}_compensate"
        with self.repository.transaction() as connection:
            account = self._account(connection, account_id, lock=True)
            existing_compensation = self._existing_operation(
                connection, transfer_id, account_id, compensation_operation
            )
            if existing_compensation is not None:
                self._assert_same_amount(existing_compensation, amount, transfer_id)
                return _LedgerResult(
                    transfer_id=str(existing_compensation["transfer_id"]),
                    account_id=existing_compensation["account_id"],
                    amount=existing_compensation["amount"],
                    new_balance=existing_compensation["balance_after"],
                    status=existing_compensation["status"],
                ).response()

            original = self._existing_operation(connection, transfer_id, account_id, original_operation)
            if original is None:
                raise AccountServiceError(
                    transfer_id=transfer_id,
                    status="FAILED",
                    error_code="ORIGINAL_OPERATION_NOT_FOUND",
                    message=f"Cannot compensate a {original_operation} that did not occur",
                    http_status=409,
                )
            self._assert_same_amount(original, amount, transfer_id)

            if direction < 0 and account["balance"] < amount:
                raise AccountServiceError(
                    transfer_id=transfer_id,
                    status="FAILED",
                    error_code="INSUFFICIENT_FUNDS",
                    message="Insufficient funds to compensate credit",
                    http_status=409,
                )

            new_balance = account["balance"] + direction * amount
            connection.execute(
                """
                UPDATE account.accounts
                SET balance = %s, updated_at = now()
                WHERE account_id = %s
                """,
                (new_balance, account_id),
            )
            connection.execute(
                """
                UPDATE account.ledger_entries
                SET compensated = true
                WHERE transfer_id = %s AND account_id = %s AND operation = %s
                """,
                (transfer_id, account_id, original_operation),
            )
            connection.execute(
                """
                INSERT INTO account.ledger_entries (
                    operation_id, transfer_id, account_id, operation, amount,
                    balance_after, status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                """,
                (
                    str(uuid4()),
                    transfer_id,
                    account_id,
                    compensation_operation,
                    amount,
                    new_balance,
                    "COMPENSATED",
                ),
            )

        logger.info(
            "transfer_id=%s service=account-service operation=%s status=COMPENSATED",
            transfer_id,
            compensation_operation,
        )
        return _LedgerResult(transfer_id, account_id, amount, new_balance, "COMPENSATED").response()


account_service = AccountService(AccountRepository())
