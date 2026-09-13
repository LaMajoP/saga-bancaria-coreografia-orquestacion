"""Idempotent clearing simulation, timeout rejection and compensation."""

from dataclasses import dataclass
import os
import time
from typing import Any

from psycopg import Connection

from app.database import ClearingDatabase
from app.schemas.clearing import ClearingResponse, ClearingTransferRequest


class ClearingServiceError(Exception):
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
class ClearingSettings:
    latency_seconds: float
    timeout_seconds: float

    @classmethod
    def from_environment(cls) -> "ClearingSettings":
        try:
            latency = float(os.getenv("CLEARING_LATENCY_SECONDS", "0"))
            timeout = float(os.getenv("CLEARING_TIMEOUT_SECONDS", "3"))
        except ValueError as error:
            raise RuntimeError("Clearing latency and timeout must be numeric") from error
        if latency < 0 or timeout < 0:
            raise RuntimeError("Clearing latency and timeout cannot be negative")
        return cls(latency_seconds=latency, timeout_seconds=timeout)


@dataclass(frozen=True)
class _ClearingResult:
    transfer_id: str
    status: str
    error_code: str | None
    message: str | None
    latency_seconds: float

    def response(self, *, replayed: bool = False) -> ClearingResponse:
        return ClearingResponse(
            success=self.status in {"COMPLETED", "COMPENSATED"},
            transfer_id=self.transfer_id,
            status=self.status,
            error_code=self.error_code,
            message=self.message,
            latency_seconds=self.latency_seconds,
            replayed=replayed,
        )


class ClearingService:
    def __init__(self, database: ClearingDatabase) -> None:
        self.database = database

    def initialize(self) -> None:
        self.database.initialize()

    @staticmethod
    def _from_row(row: dict[str, Any]) -> _ClearingResult:
        return _ClearingResult(
            transfer_id=str(row["transfer_id"]),
            status=row["status"],
            error_code=row["error_code"],
            message=row["message"],
            latency_seconds=float(row["latency_seconds"]),
        )

    @staticmethod
    def _matches_request(row: dict[str, Any], request: ClearingTransferRequest) -> bool:
        return (
            str(row["source_account_id"]) == request.source_account_id
            and str(row["destination_account_id"]) == request.destination_account_id
            and row["amount"] == request.amount
            and row["force_timeout"] == request.force_clearing_timeout
        )

    def transfer(self, request: ClearingTransferRequest) -> ClearingResponse:
        transfer_id = str(request.transfer_id)
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM clearing.operations WHERE transfer_id = %s FOR UPDATE",
                (transfer_id,),
            ).fetchone()
            if existing is not None:
                if not self._matches_request(existing, request):
                    raise ClearingServiceError(
                        transfer_id=transfer_id,
                        status="FAILED",
                        error_code="IDEMPOTENCY_CONFLICT",
                        message="transfer_id already belongs to a different clearing request",
                        http_status=409,
                    )
                return self._from_row(existing).response(replayed=True)

        settings = ClearingSettings.from_environment()
        if settings.latency_seconds:
            time.sleep(settings.latency_seconds)

        timed_out = request.force_clearing_timeout or (
            settings.timeout_seconds > 0 and settings.latency_seconds > settings.timeout_seconds
        )
        status = "REJECTED_NETWORK" if timed_out else "COMPLETED"
        error_code = "CLEARING_TIMEOUT" if timed_out else None
        message = "Interbank clearing timeout" if timed_out else None

        with self.database.transaction() as connection:
            row = connection.execute(
                """
                INSERT INTO clearing.operations (
                    transfer_id, source_account_id, destination_account_id, amount,
                    force_timeout, latency_seconds, status, error_code, message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (transfer_id) DO NOTHING
                RETURNING *
                """,
                (
                    transfer_id,
                    request.source_account_id,
                    request.destination_account_id,
                    request.amount,
                    request.force_clearing_timeout,
                    settings.latency_seconds,
                    status,
                    error_code,
                    message,
                ),
            ).fetchone()
            if row is not None:
                return self._from_row(row).response()

            existing = connection.execute(
                "SELECT * FROM clearing.operations WHERE transfer_id = %s FOR UPDATE",
                (transfer_id,),
            ).fetchone()
            if existing is None:
                raise RuntimeError("Clearing operation disappeared during transaction")
            if not self._matches_request(existing, request):
                raise ClearingServiceError(
                    transfer_id=transfer_id,
                    status="FAILED",
                    error_code="IDEMPOTENCY_CONFLICT",
                    message="transfer_id already belongs to a different clearing request",
                    http_status=409,
                )
            return self._from_row(existing).response(replayed=True)

    def compensate(self, transfer_id: str) -> ClearingResponse:
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM clearing.operations WHERE transfer_id = %s FOR UPDATE",
                (transfer_id,),
            ).fetchone()
            if existing is None:
                raise ClearingServiceError(
                    transfer_id=transfer_id,
                    status="FAILED",
                    error_code="ORIGINAL_OPERATION_NOT_FOUND",
                    message="Cannot compensate a clearing operation that did not occur",
                    http_status=409,
                )
            if existing["compensated"]:
                return self._from_row(existing).response(replayed=True)
            if existing["status"] != "COMPLETED":
                raise ClearingServiceError(
                    transfer_id=transfer_id,
                    status="FAILED",
                    error_code="CLEARING_NOT_COMPLETED",
                    message="Only a completed clearing operation can be compensated",
                    http_status=409,
                )

            row = connection.execute(
                """
                UPDATE clearing.operations
                SET status = 'COMPENSATED', compensated = true, updated_at = now()
                WHERE transfer_id = %s
                RETURNING *
                """,
                (transfer_id,),
            ).fetchone()
            return self._from_row(row).response()


clearing_service = ClearingService(ClearingDatabase())
