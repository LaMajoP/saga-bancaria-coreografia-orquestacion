"""Prefect wrapper around the orchestrator.

The workshop admits "un coordinador central (coordinador o flujo de Prefect)".
Each local transaction and each compensation becomes a Prefect task, so the
Prefect UI shows the flow advancing step by step — and, on failure, walking
back. The saga logic itself lives in ``coordinator.py`` and knows nothing about
Prefect: that keeps the tests fast and the orchestration engine replaceable.
"""

from prefect import flow, task

from app.core.config import get_settings
from app.domain.errors import StepOutcome
from app.domain.states import StepName
from app.domain.steps import STEP_BY_NAME, StepDefinition
from app.orchestration.context import SagaContext, SagaRequest
from app.orchestration.coordinator import SagaResult, run_orchestrated_saga
from app.orchestration.steps import compensate_step, execute_step


@task(name="saga-step", task_run_name="{step}", retries=0)
def _action_task(request: dict, step: str) -> StepOutcome:
    """One local transaction, visible as its own task run."""
    context = SagaContext(SagaRequest(**request))
    return execute_step(context, STEP_BY_NAME[StepName(step)])


@task(name="saga-compensation", task_run_name="compensate-{step}", retries=0)
def _compensation_task(request: dict, step: str, sequence: int) -> StepOutcome:
    """One compensation, visible as its own task run."""
    context = SagaContext(SagaRequest(**request))
    return compensate_step(context, STEP_BY_NAME[StepName(step)], sequence)


def _prefect_action_runner(context: SagaContext, step: StepDefinition) -> StepOutcome:
    return _action_task(context.request.as_dict(), step.name.value)


def _prefect_compensation_runner(
    context: SagaContext, step: StepDefinition, sequence: int
) -> StepOutcome:
    return _compensation_task(context.request.as_dict(), step.name.value, sequence)


@flow(name="saga-transferencia-bancaria", flow_run_name="saga-{request[transfer_id]}")
def transfer_saga_flow(request: dict) -> SagaResult:
    return run_orchestrated_saga(
        SagaRequest(**request),
        action_runner=_prefect_action_runner,
        compensation_runner=_prefect_compensation_runner,
    )


def run_saga(request: SagaRequest) -> SagaResult:
    """Run the orchestrated saga, through Prefect when it is enabled."""
    if not get_settings().use_prefect:
        return run_orchestrated_saga(request)
    return transfer_saga_flow(request.as_dict())
