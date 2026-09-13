"""Thread-safe in-memory transfer registry and idempotency boundary."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from threading import Lock
from uuid import uuid4

from app.schemas.transfers import ChaosOptions, TransferRequest, TransferResponse, TransferStatus


class IdempotencyConflictError(Exception):
    """The key was already used with a different transfer request."""


@dataclass
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


class TransferRegistry:
    def __init__(self) -> None:
        self._records: dict[str, TransferRecord] = {}
        self._transfer_ids_by_key: dict[str, str] = {}
        self._lock = Lock()

    @staticmethod
    def _fingerprint(request: TransferRequest) -> str:
        payload = json.dumps(
            request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def create_or_retrieve(
        self, request: TransferRequest, idempotency_key: str
    ) -> tuple[TransferRecord, bool]:
        fingerprint = self._fingerprint(request)
        with self._lock:
            transfer_id = self._transfer_ids_by_key.get(idempotency_key)
            if transfer_id is not None:
                record = self._records[transfer_id]
                if record.fingerprint != fingerprint:
                    raise IdempotencyConflictError(
                        "Idempotency-Key already belongs to a different transfer request"
                    )
                return record, True

            now = datetime.now(UTC)
            record = TransferRecord(
                transfer_id=str(uuid4()),
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                status=TransferStatus.RECEIVED,
                source_account_id=request.source_account_id,
                destination_account_id=request.destination_account_id,
                amount=request.amount,
                currency=request.currency,
                chaos=request.chaos,
                created_at=now,
                updated_at=now,
            )
            self._records[record.transfer_id] = record
            self._transfer_ids_by_key[idempotency_key] = record.transfer_id
            return record, False

    def get(self, transfer_id: str) -> TransferRecord | None:
        with self._lock:
            return self._records.get(transfer_id)

    def list(self) -> list[TransferRecord]:
        with self._lock:
            return sorted(self._records.values(), key=lambda record: record.created_at)


transfer_registry = TransferRegistry()
