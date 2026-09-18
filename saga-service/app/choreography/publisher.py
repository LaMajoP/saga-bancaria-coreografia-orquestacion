"""Entry point of the choreographed saga: publish TransferRequested and step aside."""

import logging

from app.choreography.broker import EventBus
from app.choreography.events import DomainEvent, EventType
from app.choreography.participants import context_payload
from app.domain.states import Implementation
from app.orchestration.context import SagaRequest
from app.persistence.repository import SagaRepository

logger = logging.getLogger(__name__)


def start_choreographed_saga(
    request: SagaRequest, repository: SagaRepository | None = None
) -> bool:
    """Register the saga and emit the first event. Returns False on a replay.

    Unlike the orchestrator, nothing here decides the sequence: once the event
    is published, the participants drive the flow on their own.
    """
    repository = repository or SagaRepository()
    execution, already_existed = repository.start_execution(
        transfer_id=request.transfer_id,
        implementation=Implementation.CHOREOGRAPHY,
        source_account_id=request.source_account_id,
        destination_account_id=request.destination_account_id,
        amount=request.amount,
        currency=request.currency,
        force_risk_failure=request.force_risk_failure,
        force_clearing_timeout=request.force_clearing_timeout,
    )
    if already_existed:
        # CP-05: republishing would make the participants act twice.
        logger.info(
            "transfer_id=%s service=saga operation=choreography status=replayed original_status=%s",
            request.transfer_id,
            execution.status.value,
        )
        return False

    bus = EventBus()
    try:
        bus.publish(
            DomainEvent(
                event_type=EventType.TRANSFER_REQUESTED,
                transfer_id=request.transfer_id,
                payload=context_payload(request),
            )
        )
    finally:
        bus.close()
    return True
