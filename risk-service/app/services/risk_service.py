"""Idempotent risk decisions and their compensations."""

from dataclasses import dataclass
import os
from typing import Any

from psycopg import Connection

from app.database import RiskDatabase
from app.schemas.risk import RiskCheckRequest, RiskResponse


class RiskServiceError(Exception):
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
class _RiskResult:
    transfer_id: str
    status: str
    error_code: str | None
    message: str | None

    def response(self, *, replayed: bool = False) -> RiskResponse:
        return RiskResponse(
            success=self.status in {"RISK_APPROVED", "COMPENSATED"},
            transfer_id=self.transfer_id,
            status=self.status,
            error_code=self.error_code,
            message=self.message,
            replayed=replayed,
        )


class RiskService:
    def __init__(self, database: RiskDatabase) -> None:
        self.database = database

    def initialize(self) -> None:
        self.database.initialize()

    @staticmethod
    def _from_row(row: dict[str, Any]) -> _RiskResult:
        return _RiskResult(
            transfer_id=str(row["transfer_id"]),
            status=row["status"],
            error_code=row["error_code"],
            message=row["message"],
        )

    @staticmethod
    def _max_amount() -> int:
        value = os.getenv("RISK_MAX_AMOUNT", "1000000")
        try:
            maximum = int(value)
        except ValueError as error:
            raise RuntimeError("RISK_MAX_AMOUNT must be an integer") from error
        if maximum <= 0:
            raise RuntimeError("RISK_MAX_AMOUNT must be greater than zero")
        return maximum

    @staticmethod
    def _matches_request(row: dict[str, Any], request: RiskCheckRequest) -> bool:
        return (
            str(row["source_account_id"]) == request.source_account_id
            and str(row["destination_account_id"]) == request.destination_account_id
            and row["amount"] == request.amount
            and row["force_failure"] == request.force_risk_failure
        )

    def check(self, request: RiskCheckRequest) -> RiskResponse:
        transfer_id = str(request.transfer_id)
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM risk.evaluations WHERE transfer_id = %s FOR UPDATE",
                (transfer_id,),
            ).fetchone()
            if existing is not None:
                if not self._matches_request(existing, request):
                    raise RiskServiceError(
                        transfer_id=transfer_id,
                        status="FAILED",
                        error_code="IDEMPOTENCY_CONFLICT",
                        message="transfer_id already belongs to a different risk request",
                        http_status=409,
                    )
                return self._from_row(existing).response(replayed=True)

            if request.force_risk_failure:
                status = "RISK_REJECTED"
                error_code = "RISK_REJECTED"
                message = "Transfer rejected by forced risk failure"
            elif request.amount > self._max_amount():
                status = "RISK_REJECTED"
                error_code = "RISK_LIMIT_EXCEEDED"
                message = "Transfer amount exceeds the configured risk limit"
            else:
                status = "RISK_APPROVED"
                error_code = None
                message = None

            row = connection.execute(
                """
                INSERT INTO risk.evaluations (
                    transfer_id, source_account_id, destination_account_id, amount,
                    force_failure, status, error_code, message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (transfer_id) DO NOTHING
                RETURNING *
                """,
                (
                    transfer_id,
                    request.source_account_id,
                    request.destination_account_id,
                    request.amount,
                    request.force_risk_failure,
                    status,
                    error_code,
                    message,
                ),
            ).fetchone()
            if row is not None:
                return self._from_row(row).response()

            existing = connection.execute(
                "SELECT * FROM risk.evaluations WHERE transfer_id = %s FOR UPDATE",
                (transfer_id,),
            ).fetchone()
            if existing is None:
                raise RuntimeError("Risk evaluation disappeared during transaction")
            if not self._matches_request(existing, request):
                raise RiskServiceError(
                    transfer_id=transfer_id,
                    status="FAILED",
                    error_code="IDEMPOTENCY_CONFLICT",
                    message="transfer_id already belongs to a different risk request",
                    http_status=409,
                )
            return self._from_row(existing).response(replayed=True)

    def compensate(self, transfer_id: str) -> RiskResponse:
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM risk.evaluations WHERE transfer_id = %s FOR UPDATE",
                (transfer_id,),
            ).fetchone()
            if existing is None:
                raise RiskServiceError(
                    transfer_id=transfer_id,
                    status="FAILED",
                    error_code="ORIGINAL_OPERATION_NOT_FOUND",
                    message="Cannot compensate a risk evaluation that did not occur",
                    http_status=409,
                )
            if existing["compensated"]:
                return self._from_row(existing).response(replayed=True)
            if existing["status"] != "RISK_APPROVED":
                raise RiskServiceError(
                    transfer_id=transfer_id,
                    status="FAILED",
                    error_code="RISK_NOT_APPROVED",
                    message="Only an approved risk evaluation can be compensated",
                    http_status=409,
                )

            row = connection.execute(
                """
                UPDATE risk.evaluations
                SET status = 'COMPENSATED', compensated = true, updated_at = now()
                WHERE transfer_id = %s
                RETURNING *
                """,
                (transfer_id,),
            ).fetchone()
            return self._from_row(row).response()


risk_service = RiskService(RiskDatabase())
