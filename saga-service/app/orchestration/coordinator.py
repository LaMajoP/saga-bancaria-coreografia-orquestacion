"""The central coordinator: the Orchestration flavour of the Saga.

One component decides the whole sequence, observes every result and, on
failure, explicitly calls the compensation of each step that had succeeded —
in strictly reverse order.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from app.core.logging import log_step
from app.domain.errors import StepOutcome, outcome_for
from app.domain.states import (
    CompensationStatus,
    GatewayStatus,
    Implementation,
    SagaStatus,
    StepName,
    to_gateway_status,
)
from app.domain.steps import STEPS, StepDefinition, compensation_order, compensation_sequence
from app.orchestration.context import SagaContext, SagaRequest
from app.orchestration.steps import compensate_step, execute_step, skip_step

ActionRunner = Callable[[SagaContext, StepDefinition], StepOutcome]
CompensationRunner = Callable[[SagaContext, StepDefinition, int], StepOutcome]

#: Saga status reached after each step succeeds.
_STATUS_AFTER: dict[StepName, SagaStatus] = {
    StepName.DEBIT: SagaStatus.DEBITED,
    StepName.RISK: SagaStatus.RISK_APPROVED,
    StepName.CLEARING: SagaStatus.CLEARING_PENDING,
    StepName.CREDIT: SagaStatus.COMPLETED,
}


@dataclass(frozen=True)
class SagaResult:
    transfer_id: str
    implementation: Implementation
    status: SagaStatus
    compensation_status: CompensationStatus
    gateway_status: GatewayStatus
    error_code: str | None = None
    message: str | None = None
    executed: list[StepName] = field(default_factory=list)
    compensated: list[StepName] = field(default_factory=list)
    replayed: bool = False


def _notify(
    context: SagaContext,
    status: SagaStatus,
    error_code: str | None = None,
    message: str | None = None,
) -> None:
    """Project the internal status onto the Gateway's public vocabulary."""
    if not context.settings.notify_gateway:
        return
    public = to_gateway_status(status)
    context.gateway.notify_status(context.transfer_id, public.value, error_code, message)


def execute_saga(
    context: SagaContext,
    action_runner: ActionRunner = execute_step,
    compensation_runner: CompensationRunner = compensate_step,
) -> SagaResult:
    repository = context.repository
    transfer_id = context.transfer_id

    _notify(context, SagaStatus.PENDING)

    failure: StepOutcome | None = None
    failed_step: StepDefinition | None = None

    for index, step in enumerate(STEPS):
        repository.update_execution(transfer_id, current_step=step.name)
        outcome = action_runner(context, step)

        if outcome.ok:
            reached = _STATUS_AFTER[step.name]
            repository.update_execution(transfer_id, status=reached)
            if reached is not SagaStatus.COMPLETED:
                _notify(context, reached)
            continue

        failure = outcome
        failed_step = step
        # Leave the untried steps visible in the trail instead of absent.
        for remaining in STEPS[index + 1 :]:
            skip_step(context, remaining, f"not attempted: {step.name.value} failed")
        break

    # The source of truth for "what really executed" is the audit trail, not a
    # variable in memory: nothing may be compensated unless it is recorded.
    executed = repository.executed_steps(transfer_id)

    if failure is None:
        repository.update_execution(
            transfer_id,
            status=SagaStatus.COMPLETED,
            compensation_status=CompensationStatus.NOT_REQUIRED,
            clear_current_step=True,
            finished=True,
        )
        _notify(context, SagaStatus.COMPLETED)
        log_step(
            transfer_id=transfer_id,
            service="saga",
            operation="orchestration",
            status="COMPLETED",
        )
        return SagaResult(
            transfer_id=transfer_id,
            implementation=Implementation.ORCHESTRATION,
            status=SagaStatus.COMPLETED,
            compensation_status=CompensationStatus.NOT_REQUIRED,
            gateway_status=to_gateway_status(SagaStatus.COMPLETED),
            executed=executed,
        )

    final_status = outcome_for(failure.error_code, default=SagaStatus.FAILED)
    pending_compensations = compensation_order(executed)

    if not pending_compensations:
        # CP-02: the debit never happened, so there is nothing to undo.
        # Compensating here would violate the contract's main rule.
        repository.update_execution(
            transfer_id,
            status=final_status,
            compensation_status=CompensationStatus.NOT_REQUIRED,
            error_code=failure.error_code,
            message=failure.message,
            clear_current_step=True,
            finished=True,
        )
        _notify(context, final_status, failure.error_code, failure.message)
        log_step(
            transfer_id=transfer_id,
            service="saga",
            operation="orchestration",
            status=final_status.value,
            error=failure.error_code,
            compensations="none",
        )
        return SagaResult(
            transfer_id=transfer_id,
            implementation=Implementation.ORCHESTRATION,
            status=final_status,
            compensation_status=CompensationStatus.NOT_REQUIRED,
            gateway_status=to_gateway_status(final_status),
            error_code=failure.error_code,
            message=failure.message,
            executed=executed,
        )

    repository.update_execution(
        transfer_id,
        status=SagaStatus.COMPENSATING,
        compensation_status=CompensationStatus.COMPENSATING,
        error_code=failure.error_code,
        message=failure.message,
    )
    _notify(context, SagaStatus.COMPENSATING, failure.error_code, failure.message)
    log_step(
        transfer_id=transfer_id,
        service="saga",
        operation="compensation_started",
        status="COMPENSATING",
        error=failure.error_code,
        failed_step=failed_step.name.value if failed_step else None,
        order="->".join(step.name.value for step in pending_compensations),
    )

    compensated: list[StepName] = []
    every_compensation_succeeded = True
    for step in pending_compensations:
        # Same numbering as the choreography, so one audit trail reads alike in
        # both modes and the two can be compared row by row.
        result = compensation_runner(context, step, compensation_sequence(step))
        if result.ok:
            compensated.append(step.name)
        else:
            every_compensation_succeeded = False

    compensation_status = (
        CompensationStatus.COMPENSATED
        if every_compensation_succeeded
        else CompensationStatus.COMPENSATION_FAILED
    )
    repository.update_execution(
        transfer_id,
        status=final_status,
        compensation_status=compensation_status,
        error_code=failure.error_code,
        message=failure.message,
        clear_current_step=True,
        finished=True,
    )
    _notify(context, final_status, failure.error_code, failure.message)
    log_step(
        transfer_id=transfer_id,
        service="saga",
        operation="orchestration",
        status=final_status.value,
        error=failure.error_code,
        compensations="->".join(name.value for name in compensated),
        compensation_status=compensation_status.value,
    )

    return SagaResult(
        transfer_id=transfer_id,
        implementation=Implementation.ORCHESTRATION,
        status=final_status,
        compensation_status=compensation_status,
        gateway_status=to_gateway_status(final_status),
        error_code=failure.error_code,
        message=failure.message,
        executed=executed,
        compensated=compensated,
    )


def run_orchestrated_saga(
    request: SagaRequest,
    context: SagaContext | None = None,
    action_runner: ActionRunner | None = None,
    compensation_runner: CompensationRunner | None = None,
) -> SagaResult:
    """Entry point of the orchestrated saga, idempotent by ``transfer_id``."""
    context = context or SagaContext(request)
    execution, already_existed = context.repository.start_execution(
        transfer_id=request.transfer_id,
        implementation=Implementation.ORCHESTRATION,
        source_account_id=request.source_account_id,
        destination_account_id=request.destination_account_id,
        amount=request.amount,
        currency=request.currency,
        force_risk_failure=request.force_risk_failure,
        force_clearing_timeout=request.force_clearing_timeout,
    )

    if already_existed and execution.finished_at is not None:
        # CP-05: a retry of a finished saga returns the original outcome and
        # does not touch a single balance again.
        log_step(
            transfer_id=request.transfer_id,
            service="saga",
            operation="orchestration",
            status="replayed",
            original_status=execution.status.value,
        )
        return SagaResult(
            transfer_id=request.transfer_id,
            implementation=execution.implementation,
            status=execution.status,
            compensation_status=execution.compensation_status,
            gateway_status=to_gateway_status(execution.status),
            error_code=execution.error_code,
            message=execution.message,
            executed=context.repository.executed_steps(request.transfer_id),
            replayed=True,
        )

    return execute_saga(
        context,
        action_runner or execute_step,
        compensation_runner or compensate_step,
    )
