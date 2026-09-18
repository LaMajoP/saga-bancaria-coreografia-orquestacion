"""Persistence of saga executions, the audit trail and the event store."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Json

from app.domain.states import (
    CompensationStatus,
    Implementation,
    SagaStatus,
    StepName,
    StepStatus,
)
from app.persistence.database import SagaDatabase

#: Compensation steps are numbered above the forward steps so that ordering the
#: audit trail by ``sequence`` shows the rollback happening in reverse order.
COMPENSATION_SEQUENCE_BASE = 100


@dataclass(frozen=True)
class SagaExecution:
    transfer_id: str
    implementation: Implementation
    status: SagaStatus
    compensation_status: CompensationStatus
    current_step: str | None
    source_account_id: str
    destination_account_id: str
    amount: int
    currency: str
    force_risk_failure: bool
    force_clearing_timeout: bool
    error_code: str | None
    message: str | None
    started_at: datetime
    finished_at: datetime | None


class SagaRepository:
    def __init__(self, database: SagaDatabase | None = None) -> None:
        self.database = database or SagaDatabase()

    def initialize(self) -> None:
        self.database.initialize()

    # ------------------------------------------------------------------ executions

    @staticmethod
    def _execution(row: dict[str, Any]) -> SagaExecution:
        return SagaExecution(
            transfer_id=str(row["transfer_id"]),
            implementation=Implementation(row["implementation"]),
            status=SagaStatus(row["status"]),
            compensation_status=CompensationStatus(row["compensation_status"]),
            current_step=row["current_step"],
            source_account_id=row["source_account_id"],
            destination_account_id=row["destination_account_id"],
            amount=int(row["amount"]),
            currency=row["currency"],
            force_risk_failure=row["force_risk_failure"],
            force_clearing_timeout=row["force_clearing_timeout"],
            error_code=row["error_code"],
            message=row["message"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    def start_execution(
        self,
        *,
        transfer_id: str,
        implementation: Implementation,
        source_account_id: str,
        destination_account_id: str,
        amount: int,
        currency: str = "COP",
        force_risk_failure: bool = False,
        force_clearing_timeout: bool = False,
    ) -> tuple[SagaExecution, bool]:
        """Register the saga once. Returns ``(execution, already_existed)``.

        A replay of the same ``transfer_id`` must never start a second saga:
        this is the first of the three idempotency barriers (CP-05).
        """
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                INSERT INTO saga.executions (
                    transfer_id, implementation, status, compensation_status,
                    source_account_id, destination_account_id, amount, currency,
                    force_risk_failure, force_clearing_timeout
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (transfer_id) DO NOTHING
                RETURNING *
                """,
                (
                    transfer_id,
                    implementation.value,
                    SagaStatus.PENDING.value,
                    CompensationStatus.NOT_REQUIRED.value,
                    source_account_id,
                    destination_account_id,
                    amount,
                    currency,
                    force_risk_failure,
                    force_clearing_timeout,
                ),
            ).fetchone()
            if row is not None:
                return self._execution(row), False

            existing = connection.execute(
                "SELECT * FROM saga.executions WHERE transfer_id = %s", (transfer_id,)
            ).fetchone()
            if existing is None:
                raise RuntimeError("Saga execution disappeared during transaction")
            return self._execution(existing), True

    def update_execution(
        self,
        transfer_id: str,
        *,
        status: SagaStatus | None = None,
        compensation_status: CompensationStatus | None = None,
        current_step: StepName | None = None,
        clear_current_step: bool = False,
        error_code: str | None = None,
        message: str | None = None,
        finished: bool = False,
    ) -> None:
        assignments: list[str] = ["updated_at = now()"]
        params: list[Any] = []
        if status is not None:
            assignments.append("status = %s")
            params.append(status.value)
        if compensation_status is not None:
            assignments.append("compensation_status = %s")
            params.append(compensation_status.value)
        if clear_current_step:
            assignments.append("current_step = NULL")
        elif current_step is not None:
            assignments.append("current_step = %s")
            params.append(current_step.value)
        if error_code is not None:
            assignments.append("error_code = %s")
            params.append(error_code)
        if message is not None:
            assignments.append("message = %s")
            params.append(message)
        if finished:
            assignments.append("finished_at = now()")
        params.append(transfer_id)

        with self.database.transaction() as connection:
            connection.execute(
                f"UPDATE saga.executions SET {', '.join(assignments)} WHERE transfer_id = %s",
                params,
            )

    def get_execution(self, transfer_id: str) -> SagaExecution | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM saga.executions WHERE transfer_id = %s", (transfer_id,)
            ).fetchone()
            return self._execution(row) if row is not None else None

    def list_executions(self, limit: int = 50) -> list[SagaExecution]:
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM saga.executions ORDER BY started_at DESC LIMIT %s", (limit,)
            ).fetchall()
            return [self._execution(row) for row in rows]

    # ----------------------------------------------------------------- audit trail

    def record_step(
        self,
        *,
        transfer_id: str,
        sequence: int,
        step_name: StepName,
        kind: str,
        service: str,
        operation: str,
        status: StepStatus,
        attempt: int = 1,
        error_code: str | None = None,
        message: str | None = None,
        duration_ms: int | None = None,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
    ) -> None:
        """Write one row per logical step. Retries update the row, not duplicate it."""
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO saga.saga_steps (
                    transfer_id, sequence, step_name, kind, service, operation,
                    status, attempt, error_code, message, duration_ms, request, response
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (transfer_id, step_name, kind) DO UPDATE SET
                    sequence = EXCLUDED.sequence,
                    status = EXCLUDED.status,
                    attempt = EXCLUDED.attempt,
                    error_code = EXCLUDED.error_code,
                    message = EXCLUDED.message,
                    duration_ms = EXCLUDED.duration_ms,
                    response = EXCLUDED.response,
                    updated_at = now()
                """,
                (
                    transfer_id,
                    sequence,
                    step_name.value,
                    kind,
                    service,
                    operation,
                    status.value,
                    attempt,
                    error_code,
                    message,
                    duration_ms,
                    Json(request) if request is not None else None,
                    Json(response) if response is not None else None,
                ),
            )

    def list_steps(self, transfer_id: str) -> list[dict[str, Any]]:
        with self.database.transaction() as connection:
            return connection.execute(
                """
                SELECT sequence, step_name, kind, service, operation, status,
                       attempt, error_code, message, duration_ms, created_at, updated_at
                FROM saga.saga_steps
                WHERE transfer_id = %s
                ORDER BY sequence
                """,
                (transfer_id,),
            ).fetchall()

    def executed_steps(self, transfer_id: str) -> list[StepName]:
        """Steps that really executed, in forward order. Nothing else may be compensated."""
        with self.database.transaction() as connection:
            rows = connection.execute(
                """
                SELECT step_name FROM saga.saga_steps
                WHERE transfer_id = %s AND kind = 'ACTION' AND status = 'EXECUTED'
                ORDER BY sequence
                """,
                (transfer_id,),
            ).fetchall()
            return [StepName(row["step_name"]) for row in rows]

    # ---------------------------------------------------------------- event store

    def append_event(
        self,
        *,
        event_id: str,
        event_type: str,
        transfer_id: str,
        payload: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO saga.saga_events (event_id, event_type, transfer_id, payload, occurred_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    event_id,
                    event_type,
                    transfer_id,
                    Json(payload),
                    occurred_at or datetime.now(timezone.utc),
                ),
            )

    def list_events(self, transfer_id: str) -> list[dict[str, Any]]:
        with self.database.transaction() as connection:
            return connection.execute(
                """
                SELECT event_id, event_type, transfer_id, payload, occurred_at
                FROM saga.saga_events
                WHERE transfer_id = %s
                ORDER BY occurred_at, recorded_at
                """,
                (transfer_id,),
            ).fetchall()

    def claim_event(self, consumer: str, event_id: str, transfer_id: str) -> bool:
        """Return True the first time a consumer sees an event, False on redelivery.

        RabbitMQ guarantees at-least-once delivery; this turns it into an
        exactly-once *effect* per participant (second idempotency barrier).
        """
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                INSERT INTO saga.processed_events (consumer, event_id, transfer_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (consumer, event_id) DO NOTHING
                RETURNING event_id
                """,
                (consumer, event_id, transfer_id),
            ).fetchone()
            return row is not None
