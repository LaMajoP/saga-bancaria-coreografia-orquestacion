"""Supabase-backed transfer registry and idempotency boundary."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from typing import Any
from uuid import uuid4

from psycopg import Connection

from app.database import GatewayDatabase
from app.schemas.transfers import ChaosOptions, TransferRequest, TransferResponse, TransferStatus


class IdempotencyConflictError(Exception):
    """The key was already used with a different transfer request."""


@dataclass(frozen=True)
class TransferRecord:
    transfer_id: str
    idempotency_key: str
    fingerprint: str
    status: TransferStatus
    source_account_id: str
    destination_account_id: str
    amount: Decimal
    currency: str
    chaos: ChaosOptions
    created_at: datetime
    updated_at: datetime

    def response(self, replayed: bool = False) -> TransferResponse:
        return TransferResponse(
            transfer_id=self.transfer_id,
            idempotency_key=self.idempotency_key,
            status=self.status,
            source_account_id=self.source_account_id,
            destination_account_id=self.destination_account_id,
            amount=self.amount,
            currency=self.currency,
            chaos=self.chaos,
            created_at=self.created_at,
            updated_at=self.updated_at,
            replayed=replayed,
        )


class TransferRepository:
    def __init__(self, database: GatewayDatabase) -> None:
        self.database = database

    def initialize(self) -> None:
        self.database.initialize()

    @staticmethod
    def _fingerprint(request: TransferRequest) -> str:
        payload = json.dumps(
            request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _record_from_row(row: dict[str, Any]) -> TransferRecord:
        return TransferRecord(
            transfer_id=str(row["transfer_id"]),
            idempotency_key=str(row["idempotency_key"]),
            fingerprint=row["request_fingerprint"],
            status=TransferStatus(row["status"]),
            source_account_id=row["source_account_id"],
            destination_account_id=row["destination_account_id"],
            amount=Decimal(row["amount"]),
            currency=row["currency"],
            chaos=ChaosOptions(
                force_risk_failure=row["force_risk_failure"],
                force_clearing_timeout=row["force_clearing_timeout"],
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _get(connection: Connection[Any], transfer_id: str) -> TransferRecord | None:
        row = connection.execute(
            "SELECT * FROM gateway.transfers WHERE transfer_id = %s",
            (transfer_id,),
        ).fetchone()
        return TransferRepository._record_from_row(row) if row is not None else None

    def create_or_retrieve(
        self, request: TransferRequest, idempotency_key: str
    ) -> tuple[TransferRecord, bool]:
        fingerprint = self._fingerprint(request)
        transfer_id = str(uuid4())

        with self.database.transaction() as connection:
            row = connection.execute(
                """
                INSERT INTO gateway.transfers (
                    transfer_id, idempotency_key, request_fingerprint, status,
                    source_account_id, destination_account_id, amount, currency,
                    force_risk_failure, force_clearing_timeout
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING *
                """,
                (
                    transfer_id,
                    idempotency_key,
                    fingerprint,
                    TransferStatus.RECEIVED.value,
                    request.source_account_id,
                    request.destination_account_id,
                    int(request.amount),
                    request.currency,
                    request.chaos.force_risk_failure,
                    request.chaos.force_clearing_timeout,
                ),
            ).fetchone()
            if row is not None:
                return self._record_from_row(row), False

            existing = connection.execute(
                "SELECT * FROM gateway.transfers WHERE idempotency_key = %s",
                (idempotency_key,),
            ).fetchone()
            if existing is None:
                raise RuntimeError("Idempotency record disappeared during transaction")
            if existing["request_fingerprint"] != fingerprint:
                raise IdempotencyConflictError(
                    "Idempotency-Key already belongs to a different transfer request"
                )
            return self._record_from_row(existing), True

    def get(self, transfer_id: str) -> TransferRecord | None:
        with self.database.transaction() as connection:
            return self._get(connection, transfer_id)

    def list(self) -> list[TransferRecord]:
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM gateway.transfers ORDER BY created_at"
            ).fetchall()
            return [self._record_from_row(row) for row in rows]


transfer_repository = TransferRepository(GatewayDatabase())
