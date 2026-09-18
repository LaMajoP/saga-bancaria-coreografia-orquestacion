"""Autonomous participants of the choreographed saga.

No component here decides the whole flow. Each participant subscribes to the
events it cares about, performs its own local transaction through the public
API of its service, and publishes what happened. The sequence emerges from the
events; the rollback emerges from chaining them backwards.
"""

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from app.choreography.broker import EventBus
from app.choreography.events import DomainEvent, EventType
from app.core.logging import log_step
from app.domain.errors import outcome_for
from app.domain.states import (
    CompensationStatus,
    SagaStatus,
    StepName,
    to_gateway_status,
)
from app.domain.steps import STEP_BY_NAME, compensation_sequence
from app.orchestration.context import SagaContext, SagaRequest
from app.orchestration.steps import compensate_step, execute_step
from app.persistence.repository import SagaRepository

logger = logging.getLogger(__name__)


def context_payload(request: SagaRequest) -> dict[str, Any]:
    """Transfer data carried by every event so participants stay autonomous."""
    return {
        "source_account_id": request.source_account_id,
        "destination_account_id": request.destination_account_id,
        "amount": request.amount,
        "currency": request.currency,
        "force_risk_failure": request.force_risk_failure,
        "force_clearing_timeout": request.force_clearing_timeout,
    }


def request_from(event: DomainEvent) -> SagaRequest:
    return SagaRequest.from_payload({**event.payload, "transfer_id": event.transfer_id})


@dataclass
class Participant:
    """A consumer bound to one queue, with its own deduplication scope."""

    name: str
    queue: str
    handler: Callable[["Participant", DomainEvent], None]
    bus: EventBus
    repository: SagaRepository

    def emit(
        self, event_type: EventType, request: SagaRequest, extra: dict[str, Any] | None = None
    ) -> None:
        self.bus.publish(
            DomainEvent(
                event_type=event_type,
                transfer_id=request.transfer_id,
                payload={**context_payload(request), **(extra or {})},
            )
        )

    def dispatch(self, event: DomainEvent) -> None:
        # Second idempotency barrier: RabbitMQ delivers at least once, this
        # makes the *effect* happen exactly once per participant (CP-05).
        if not self.repository.claim_event(self.name, event.event_id, event.transfer_id):
            log_step(
                transfer_id=event.transfer_id,
                service=self.name,
                operation="consume",
                status="skipped_duplicate",
                event=event.event_type.value,
            )
            return
        self.handler(self, event)


# --------------------------------------------------------------------- account


def account_handler(participant: Participant, event: DomainEvent) -> None:
    request = request_from(event)
    context = SagaContext(request, repository=participant.repository)

    if event.event_type is EventType.TRANSFER_REQUESTED:
        outcome = execute_step(context, STEP_BY_NAME[StepName.DEBIT])
        if outcome.ok:
            participant.emit(
                EventType.BALANCE_DEBITED,
                request,
                {"account_id": request.source_account_id, "amount": request.amount},
            )
        else:
            # CP-02: the debit never happened, so no compensation is requested.
            participant.emit(
                EventType.TRANSFER_FAILED,
                request,
                {
                    "failed_step": StepName.DEBIT.value,
                    "error_code": outcome.error_code,
                    "message": outcome.message,
                },
            )
        return

    if event.event_type in {EventType.RISK_REJECTED, EventType.RISK_COMPENSATED}:
        # Both continue the rollback towards the debit. RiskRejected starts it
        # (CP-03, only the debit ran); RiskCompensated chains it after the risk
        # approval was undone (CP-04), which is what enforces reverse order.
        participant.emit(
            EventType.DEBIT_COMPENSATION_REQUESTED,
            request,
            {"reason": event.payload.get("error_code") or event.payload.get("reason")},
        )
        return

    if event.event_type is EventType.DEBIT_COMPENSATION_REQUESTED:
        step = STEP_BY_NAME[StepName.DEBIT]
        outcome = compensate_step(context, step, compensation_sequence(step))
        if outcome.ok:
            participant.emit(
                EventType.DEBIT_COMPENSATED,
                request,
                {"account_id": request.source_account_id, "amount": request.amount},
            )
            # The debit is the first step, so undoing it closes the rollback.
            participant.emit(
                EventType.TRANSFER_COMPENSATED,
                request,
                {"reason": event.payload.get("reason")},
            )
        return

    if event.event_type is EventType.CLEARING_COMPLETED:
        outcome = execute_step(context, STEP_BY_NAME[StepName.CREDIT])
        if outcome.ok:
            participant.emit(
                EventType.TRANSFER_COMPLETED,
                request,
                {"account_id": request.destination_account_id, "amount": request.amount},
            )
        else:
            # Late failure: the rollback must start from clearing, not from the debit.
            participant.emit(
                EventType.TRANSFER_FAILED,
                request,
                {
                    "failed_step": StepName.CREDIT.value,
                    "error_code": outcome.error_code,
                    "message": outcome.message,
                },
            )
            participant.emit(
                EventType.CLEARING_COMPENSATION_REQUESTED,
                request,
                {"reason": outcome.error_code},
            )


# ------------------------------------------------------------------------ risk


def risk_handler(participant: Participant, event: DomainEvent) -> None:
    request = request_from(event)
    context = SagaContext(request, repository=participant.repository)

    if event.event_type is EventType.BALANCE_DEBITED:
        outcome = execute_step(context, STEP_BY_NAME[StepName.RISK])
        if outcome.ok:
            participant.emit(EventType.RISK_APPROVED, request)
        else:
            participant.emit(
                EventType.RISK_REJECTED,
                request,
                {"error_code": outcome.error_code, "message": outcome.message},
            )
            participant.emit(
                EventType.TRANSFER_FAILED,
                request,
                {
                    "failed_step": StepName.RISK.value,
                    "error_code": outcome.error_code,
                    "message": outcome.message,
                },
            )
        return

    if event.event_type is EventType.RISK_COMPENSATION_REQUESTED:
        step = STEP_BY_NAME[StepName.RISK]
        outcome = compensate_step(context, step, compensation_sequence(step))
        if outcome.ok:
            participant.emit(
                EventType.RISK_COMPENSATED,
                request,
                {"reason": event.payload.get("reason")},
            )


# -------------------------------------------------------------------- clearing


def clearing_handler(participant: Participant, event: DomainEvent) -> None:
    request = request_from(event)
    context = SagaContext(request, repository=participant.repository)

    if event.event_type is EventType.RISK_APPROVED:
        # Announce the intention before touching the external network.
        participant.emit(EventType.CLEARING_REQUESTED, request)
        outcome = execute_step(context, STEP_BY_NAME[StepName.CLEARING])
        if outcome.ok:
            participant.emit(EventType.CLEARING_COMPLETED, request)
        else:
            participant.emit(
                EventType.TRANSFER_FAILED,
                request,
                {
                    "failed_step": StepName.CLEARING.value,
                    "error_code": outcome.error_code,
                    "message": outcome.message,
                },
            )
            # CP-04: clearing never completed, so nothing of its own is undone.
            # The rollback starts at the previous step, risk.
            participant.emit(
                EventType.RISK_COMPENSATION_REQUESTED,
                request,
                {"reason": outcome.error_code},
            )
        return

    if event.event_type is EventType.CLEARING_COMPENSATION_REQUESTED:
        step = STEP_BY_NAME[StepName.CLEARING]
        outcome = compensate_step(context, step, compensation_sequence(step))
        if outcome.ok:
            participant.emit(
                EventType.CLEARING_COMPENSATED,
                request,
                {"reason": event.payload.get("reason")},
            )
            participant.emit(
                EventType.RISK_COMPENSATION_REQUESTED,
                request,
                {"reason": event.payload.get("reason")},
            )


# ------------------------------------------------------- projector and audit log

#: Intermediate states. None of these finishes the saga.
_PROGRESS_STATUS: dict[EventType, SagaStatus] = {
    EventType.TRANSFER_REQUESTED: SagaStatus.PENDING,
    EventType.BALANCE_DEBITED: SagaStatus.DEBITED,
    EventType.RISK_APPROVED: SagaStatus.RISK_APPROVED,
    EventType.CLEARING_REQUESTED: SagaStatus.CLEARING_PENDING,
    EventType.CLEARING_COMPLETED: SagaStatus.CLEARING_PENDING,
}

#: Events that mean the rollback is under way.
_COMPENSATING_EVENTS = frozenset(
    {
        EventType.RISK_REJECTED,
        EventType.DEBIT_COMPENSATION_REQUESTED,
        EventType.RISK_COMPENSATION_REQUESTED,
        EventType.CLEARING_COMPENSATION_REQUESTED,
    }
)


def projector_handler(participant: Participant, event: DomainEvent) -> None:
    """Keeps saga.executions current and pushes the public status to the Gateway.

    It is a read model, not a coordinator: it observes events and never emits
    one, so removing it would slow nothing down and change no outcome.
    """
    repository = participant.repository
    execution = repository.get_execution(event.transfer_id)
    if execution is None or execution.finished_at is not None:
        return

    request = request_from(event)
    context = SagaContext(request, repository=repository)

    def notify(status: SagaStatus, error_code: str | None = None, message: str | None = None) -> None:
        if context.settings.notify_gateway:
            context.gateway.notify_status(
                event.transfer_id, to_gateway_status(status).value, error_code, message
            )

    if event.event_type in _PROGRESS_STATUS:
        status = _PROGRESS_STATUS[event.event_type]
        repository.update_execution(event.transfer_id, status=status)
        notify(status)
        return

    if event.event_type is EventType.TRANSFER_COMPLETED:
        repository.update_execution(
            event.transfer_id,
            status=SagaStatus.COMPLETED,
            compensation_status=CompensationStatus.NOT_REQUIRED,
            clear_current_step=True,
            finished=True,
        )
        notify(SagaStatus.COMPLETED)
        return

    if event.event_type is EventType.TRANSFER_FAILED:
        error_code = event.payload.get("error_code")
        message = event.payload.get("message")
        final = outcome_for(error_code, default=SagaStatus.FAILED)
        if final is SagaStatus.REJECTED_FUNDS:
            # Nothing ran, so nothing is compensated: this is already the end.
            repository.update_execution(
                event.transfer_id,
                status=final,
                compensation_status=CompensationStatus.NOT_REQUIRED,
                error_code=error_code,
                message=message,
                clear_current_step=True,
                finished=True,
            )
            notify(final, error_code, message)
            return
        # The cause is recorded now, but the terminal state waits for the
        # rollback to finish, so the frontend can show COMPENSANDO in between.
        repository.update_execution(
            event.transfer_id,
            status=SagaStatus.COMPENSATING,
            compensation_status=CompensationStatus.COMPENSATING,
            error_code=error_code,
            message=message,
        )
        notify(SagaStatus.COMPENSATING, error_code, message)
        return

    if event.event_type in _COMPENSATING_EVENTS:
        repository.update_execution(
            event.transfer_id,
            status=SagaStatus.COMPENSATING,
            compensation_status=CompensationStatus.COMPENSATING,
        )
        notify(SagaStatus.COMPENSATING)
        return

    if event.event_type is EventType.TRANSFER_COMPENSATED:
        final = outcome_for(execution.error_code, default=SagaStatus.FAILED)
        repository.update_execution(
            event.transfer_id,
            status=final,
            compensation_status=CompensationStatus.COMPENSATED,
            clear_current_step=True,
            finished=True,
        )
        notify(final, execution.error_code, execution.message)


def audit_handler(participant: Participant, event: DomainEvent) -> None:
    """Persist every event, so the trace survives the broker."""
    participant.repository.append_event(
        event_id=event.event_id,
        event_type=event.event_type.value,
        transfer_id=event.transfer_id,
        payload=event.payload,
        occurred_at=event.timestamp,
    )


PARTICIPANTS: tuple[tuple[str, str, Callable[[Participant, DomainEvent], None]], ...] = (
    ("account-participant", "saga.account", account_handler),
    ("risk-participant", "saga.risk", risk_handler),
    ("clearing-participant", "saga.clearing", clearing_handler),
    ("status-projector", "saga.projector", projector_handler),
    ("event-audit", "saga.audit", audit_handler),
)
