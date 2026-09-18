"""Test doubles that let the saga logic be verified without network or database.

The point of these fakes is that the saga rules — reverse order, never
compensating what did not run, idempotency — are properties of the coordinator
and the participants, not of Supabase or RabbitMQ. Keeping them offline makes
the suite deterministic and fast.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest

from app.core.config import Settings
from app.domain.errors import FailureKind, StepOutcome
from app.domain.states import CompensationStatus, Implementation, SagaStatus, StepName
from app.orchestration.context import SagaContext, SagaRequest
from app.persistence.repository import SagaExecution


def ok(status: str = "OK") -> StepOutcome:
    return StepOutcome(ok=True, status=status, response={"success": True, "status": status})


def business_failure(error_code: str, status: str = "FAILED") -> StepOutcome:
    return StepOutcome(
        ok=False,
        status=status,
        error_code=error_code,
        message=f"rejected: {error_code}",
        response={"success": False, "error_code": error_code},
        failure_kind=FailureKind.BUSINESS,
    )


@dataclass
class FakeRepository:
    """In-memory stand-in for saga.executions / saga_steps / processed_events."""

    executions: dict[str, dict[str, Any]] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    claimed: set[tuple[str, str]] = field(default_factory=set)

    def initialize(self) -> None:  # pragma: no cover - nothing to open
        pass

    def _execution(self, row: dict[str, Any]) -> SagaExecution:
        return SagaExecution(**row)

    def start_execution(self, **kwargs: Any) -> tuple[SagaExecution, bool]:
        transfer_id = kwargs["transfer_id"]
        if transfer_id in self.executions:
            return self._execution(self.executions[transfer_id]), True
        self.executions[transfer_id] = {
            "transfer_id": transfer_id,
            "implementation": kwargs["implementation"],
            "status": SagaStatus.PENDING,
            "compensation_status": CompensationStatus.NOT_REQUIRED,
            "current_step": None,
            "source_account_id": kwargs["source_account_id"],
            "destination_account_id": kwargs["destination_account_id"],
            "amount": kwargs["amount"],
            "currency": kwargs.get("currency", "COP"),
            "force_risk_failure": kwargs.get("force_risk_failure", False),
            "force_clearing_timeout": kwargs.get("force_clearing_timeout", False),
            "error_code": None,
            "message": None,
            "started_at": datetime.now(timezone.utc),
            "finished_at": None,
        }
        return self._execution(self.executions[transfer_id]), False

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
        row = self.executions[transfer_id]
        if status is not None:
            row["status"] = status
        if compensation_status is not None:
            row["compensation_status"] = compensation_status
        if clear_current_step:
            row["current_step"] = None
        elif current_step is not None:
            row["current_step"] = current_step.value
        if error_code is not None:
            row["error_code"] = error_code
        if message is not None:
            row["message"] = message
        if finished:
            row["finished_at"] = datetime.now(timezone.utc)

    def get_execution(self, transfer_id: str) -> SagaExecution | None:
        row = self.executions.get(transfer_id)
        return self._execution(row) if row else None

    def record_step(self, **kwargs: Any) -> None:
        key = (kwargs["transfer_id"], kwargs["step_name"], kwargs["kind"])
        for existing in self.steps:
            if (existing["transfer_id"], existing["step_name"], existing["kind"]) == key:
                existing.update(kwargs)
                return
        self.steps.append(dict(kwargs))

    def list_steps(self, transfer_id: str) -> list[dict[str, Any]]:
        return sorted(
            (s for s in self.steps if s["transfer_id"] == transfer_id),
            key=lambda s: s["sequence"],
        )

    def executed_steps(self, transfer_id: str) -> list[StepName]:
        return [
            s["step_name"]
            for s in self.list_steps(transfer_id)
            if s["kind"] == "ACTION" and s["status"].value == "EXECUTED"
        ]

    def append_event(self, **kwargs: Any) -> None:
        self.events.append(dict(kwargs))

    def list_events(self, transfer_id: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["transfer_id"] == transfer_id]

    def claim_event(self, consumer: str, event_id: str, transfer_id: str) -> bool:
        key = (consumer, event_id)
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    # --- helpers for assertions ---

    def compensations(self, transfer_id: str) -> list[str]:
        """Compensated steps in the order the audit trail records them."""
        return [
            s["step_name"].value
            for s in self.list_steps(transfer_id)
            if s["kind"] == "COMPENSATION"
        ]


class FakeAccounts:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.debit_outcome = ok("DEBITED")
        self.credit_outcome = ok("COMPLETED")
        self.compensate_outcome = ok("COMPENSATED")

    def debit(self, account_id, transfer_id, amount):
        self.calls.append("debit")
        return self.debit_outcome

    def credit(self, account_id, transfer_id, amount):
        self.calls.append("credit")
        return self.credit_outcome

    def compensate_debit(self, account_id, transfer_id, amount):
        self.calls.append("compensate_debit")
        return self.compensate_outcome

    def compensate_credit(self, account_id, transfer_id, amount):
        self.calls.append("compensate_credit")
        return self.compensate_outcome


class FakeRisk:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.check_outcome = ok("RISK_APPROVED")
        self.compensate_outcome = ok("COMPENSATED")

    def check(self, transfer_id, source, destination, amount, force):
        self.calls.append("check")
        return self.check_outcome

    def compensate(self, transfer_id):
        self.calls.append("compensate")
        return self.compensate_outcome


class FakeClearing:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.transfer_outcome = ok("COMPLETED")
        self.compensate_outcome = ok("COMPENSATED")

    def transfer(self, transfer_id, source, destination, amount, force):
        self.calls.append("transfer")
        return self.transfer_outcome

    def compensate(self, transfer_id):
        self.calls.append("compensate")
        return self.compensate_outcome


class FakeGateway:
    def __init__(self) -> None:
        self.notifications: list[tuple[str, str | None]] = []

    def notify_status(self, transfer_id, status, error_code=None, message=None):
        self.notifications.append((status, error_code))
        return True


@pytest.fixture
def settings() -> Settings:
    """No delays and no Gateway calls: the tests measure logic, not latency."""
    return Settings(
        account_service_url="http://account",
        risk_service_url="http://risk",
        clearing_service_url="http://clearing",
        gateway_url="http://gateway",
        internal_token="token",
        step_delay_seconds=0.0,
        connect_timeout_seconds=1.0,
        read_timeout_seconds=1.0,
        max_attempts=1,
        backoff_base_seconds=0.0,
        use_prefect=False,
        notify_gateway=True,
        broker_url="amqp://localhost",
        exchange="saga.events",
    )


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def transfer_request() -> SagaRequest:
    return SagaRequest(
        transfer_id="11111111-1111-4111-8111-111111111111",
        source_account_id="ACC-001",
        destination_account_id="ACC-002",
        amount=50_000,
    )


@pytest.fixture
def context(settings, repository, transfer_request) -> SagaContext:
    # The saga row exists before the first step runs, exactly as the real entry
    # point creates it. execute_saga only advances an execution already opened.
    repository.start_execution(
        transfer_id=transfer_request.transfer_id,
        implementation=Implementation.ORCHESTRATION,
        source_account_id=transfer_request.source_account_id,
        destination_account_id=transfer_request.destination_account_id,
        amount=transfer_request.amount,
        currency=transfer_request.currency,
        force_risk_failure=transfer_request.force_risk_failure,
        force_clearing_timeout=transfer_request.force_clearing_timeout,
    )
    return SagaContext(
        request=transfer_request,
        repository=repository,
        settings=settings,
        accounts=FakeAccounts(),
        risk=FakeRisk(),
        clearing=FakeClearing(),
        gateway=FakeGateway(),
    )
