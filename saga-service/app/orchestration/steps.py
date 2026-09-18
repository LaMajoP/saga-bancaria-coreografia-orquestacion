"""The local transactions and their compensations, as plain functions.

They are deliberately free of Prefect: ``flow.py`` wraps them in tasks so the
Prefect UI shows every micro-step, while the tests call them directly and run
in milliseconds instead of spinning up a Prefect runtime per step.
"""

import time
from typing import Any

from app.core.logging import log_step
from app.domain.errors import StepOutcome
from app.domain.states import StepName, StepStatus
from app.domain.steps import StepDefinition
from app.orchestration.context import SagaContext


def _pause(context: SagaContext, reason: str) -> None:
    """Configurable 2-4 s delay so the flow can be watched during the demo."""
    delay = context.settings.step_delay_seconds
    if delay > 0:
        log_step(
            transfer_id=context.transfer_id,
            service="saga",
            operation="delay",
            status="waiting",
            seconds=delay,
            before=reason,
        )
        time.sleep(delay)


def _action_payload(context: SagaContext, step: StepDefinition) -> dict[str, Any]:
    request = context.request
    common = {"transfer_id": request.transfer_id, "amount": request.amount}
    if step.name is StepName.DEBIT:
        return {**common, "account_id": request.source_account_id}
    if step.name is StepName.CREDIT:
        return {**common, "account_id": request.destination_account_id}
    if step.name is StepName.RISK:
        return {**common, "force_risk_failure": request.force_risk_failure}
    return {**common, "force_clearing_timeout": request.force_clearing_timeout}


def _call_action(context: SagaContext, step: StepDefinition) -> StepOutcome:
    request = context.request
    if step.name is StepName.DEBIT:
        return context.accounts.debit(
            request.source_account_id, request.transfer_id, request.amount
        )
    if step.name is StepName.RISK:
        return context.risk.check(
            request.transfer_id,
            request.source_account_id,
            request.destination_account_id,
            request.amount,
            request.force_risk_failure,
        )
    if step.name is StepName.CLEARING:
        return context.clearing.transfer(
            request.transfer_id,
            request.source_account_id,
            request.destination_account_id,
            request.amount,
            request.force_clearing_timeout,
        )
    return context.accounts.credit(
        request.destination_account_id, request.transfer_id, request.amount
    )


def _call_compensation(context: SagaContext, step: StepDefinition) -> StepOutcome:
    request = context.request
    if step.name is StepName.DEBIT:
        return context.accounts.compensate_debit(
            request.source_account_id, request.transfer_id, request.amount
        )
    if step.name is StepName.RISK:
        return context.risk.compensate(request.transfer_id)
    if step.name is StepName.CLEARING:
        return context.clearing.compensate(request.transfer_id)
    return context.accounts.compensate_credit(
        request.destination_account_id, request.transfer_id, request.amount
    )


def execute_step(context: SagaContext, step: StepDefinition) -> StepOutcome:
    """Run one local transaction and write it to the audit trail."""
    _pause(context, step.operation)
    outcome = _call_action(context, step)

    context.repository.record_step(
        transfer_id=context.transfer_id,
        sequence=step.sequence,
        step_name=step.name,
        kind="ACTION",
        service=step.service,
        operation=step.operation,
        status=StepStatus.EXECUTED if outcome.ok else StepStatus.FAILED,
        attempt=outcome.attempts,
        error_code=outcome.error_code,
        message=outcome.message,
        duration_ms=outcome.duration_ms,
        request=_action_payload(context, step),
        response=outcome.response,
    )
    log_step(
        transfer_id=context.transfer_id,
        service=step.service,
        operation=step.operation,
        status="success" if outcome.ok else "failed",
        error=outcome.error_code,
        attempts=outcome.attempts,
    )
    return outcome


def compensate_step(context: SagaContext, step: StepDefinition, sequence: int) -> StepOutcome:
    """Undo one local transaction that really executed."""
    _pause(context, step.compensation_operation or "compensation")
    outcome = _call_compensation(context, step)

    context.repository.record_step(
        transfer_id=context.transfer_id,
        sequence=sequence,
        step_name=step.name,
        kind="COMPENSATION",
        service=step.service,
        operation=step.compensation_operation or f"{step.operation}_compensate",
        status=StepStatus.COMPENSATED if outcome.ok else StepStatus.COMPENSATION_FAILED,
        attempt=outcome.attempts,
        error_code=outcome.error_code,
        message=outcome.message,
        duration_ms=outcome.duration_ms,
        request={"transfer_id": context.transfer_id},
        response=outcome.response,
    )
    log_step(
        transfer_id=context.transfer_id,
        service=step.service,
        operation=step.compensation_operation or "compensate",
        status="success" if outcome.ok else "failed",
        error=outcome.error_code,
    )
    return outcome


def skip_step(context: SagaContext, step: StepDefinition, reason: str) -> None:
    """Record a step that was never attempted, so the trail shows the whole plan."""
    context.repository.record_step(
        transfer_id=context.transfer_id,
        sequence=step.sequence,
        step_name=step.name,
        kind="ACTION",
        service=step.service,
        operation=step.operation,
        status=StepStatus.SKIPPED,
        message=reason,
    )
