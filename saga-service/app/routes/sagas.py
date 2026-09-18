"""Entry points of the Saga layer."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from app.domain.states import to_gateway_status
from app.orchestration.context import SagaRequest
from app.orchestration.flow import run_saga
from app.persistence.repository import SagaRepository
from app.schemas.sagas import (
    ChaosOptions,
    SagaAcceptedResponse,
    SagaEventView,
    SagaExecutionListResponse,
    SagaExecutionView,
    SagaStepView,
    SagaTransferRequest,
)

router = APIRouter(prefix="/api/v1/sagas", tags=["sagas"])
repository = SagaRepository()


def _to_saga_request(request: SagaTransferRequest) -> SagaRequest:
    return SagaRequest(
        transfer_id=str(request.transfer_id),
        source_account_id=request.source_account_id,
        destination_account_id=request.destination_account_id,
        amount=request.amount,
        currency=request.currency,
        force_risk_failure=request.chaos.force_risk_failure,
        force_clearing_timeout=request.chaos.force_clearing_timeout,
    )


@router.post(
    "/transfers",
    response_model=SagaAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_transfer(
    request: SagaTransferRequest,
    background: BackgroundTasks,
    mode: str = Query(
        default="ORCHESTRATION",
        description="ORCHESTRATION uses the central coordinator; CHOREOGRAPHY "
        "publishes TransferRequested and lets the participants react.",
    ),
    wait: bool = Query(
        default=False,
        description="Run the saga inline and answer with the final state. "
        "Meant for automated tests; the Gateway always uses the async form.",
    ),
) -> SagaAcceptedResponse:
    """Accept a transfer and coordinate it. Answers 202 as agreed in section 6.1."""
    mode = mode.upper()
    if mode not in {"ORCHESTRATION", "CHOREOGRAPHY"}:
        raise HTTPException(
            status_code=422, detail="mode must be ORCHESTRATION or CHOREOGRAPHY"
        )

    saga_request = _to_saga_request(request)

    if mode == "CHOREOGRAPHY":
        from app.choreography.publisher import start_choreographed_saga

        start_choreographed_saga(saga_request)
        return SagaAcceptedResponse(
            transfer_id=request.transfer_id,
            status="EN_PROCESO",
            implementation="CHOREOGRAPHY",
        )

    if wait:
        result = run_saga(saga_request)
        return SagaAcceptedResponse(
            transfer_id=request.transfer_id,
            status=result.gateway_status.value,
            implementation=result.implementation.value,
        )
    background.add_task(run_saga, saga_request)
    return SagaAcceptedResponse(
        transfer_id=request.transfer_id,
        status="EN_PROCESO",
        implementation="ORCHESTRATION",
    )


def _view(transfer_id: str, *, with_detail: bool = True) -> SagaExecutionView:
    execution = repository.get_execution(transfer_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Saga execution not found")
    steps = repository.list_steps(transfer_id) if with_detail else []
    events = repository.list_events(transfer_id) if with_detail else []
    return SagaExecutionView(
        transfer_id=execution.transfer_id,
        implementation=execution.implementation.value,
        status=execution.status.value,
        compensation_status=execution.compensation_status.value,
        gateway_status=to_gateway_status(execution.status).value,
        current_step=execution.current_step,
        source_account_id=execution.source_account_id,
        destination_account_id=execution.destination_account_id,
        amount=execution.amount,
        currency=execution.currency,
        chaos=ChaosOptions(
            force_risk_failure=execution.force_risk_failure,
            force_clearing_timeout=execution.force_clearing_timeout,
        ),
        error_code=execution.error_code,
        message=execution.message,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        steps=[SagaStepView(**step) for step in steps],
        events=[SagaEventView(**event) for event in events],
    )


@router.get("", response_model=SagaExecutionListResponse)
def list_sagas(limit: int = Query(default=25, ge=1, le=100)) -> SagaExecutionListResponse:
    executions = repository.list_executions(limit)
    return SagaExecutionListResponse(
        executions=[_view(item.transfer_id, with_detail=False) for item in executions]
    )


@router.get("/{transfer_id}", response_model=SagaExecutionView)
def get_saga(transfer_id: UUID) -> SagaExecutionView:
    """Full trace of one saga: state, audit trail and domain events."""
    return _view(str(transfer_id))
