"""The four local transactions and their compensations, in canonical order."""

from dataclasses import dataclass

from app.domain.states import StepName


@dataclass(frozen=True)
class StepDefinition:
    name: StepName
    sequence: int
    service: str
    operation: str
    compensation_operation: str | None


#: Forward order of the saga. Compensations always run over the reverse of this.
STEPS: tuple[StepDefinition, ...] = (
    StepDefinition(StepName.DEBIT, 1, "account-service", "debit", "debit_compensate"),
    StepDefinition(StepName.RISK, 2, "risk-service", "risk_check", "risk_compensate"),
    StepDefinition(StepName.CLEARING, 3, "clearing-service", "clearing_transfer", "clearing_compensate"),
    # Credit is last: nothing can fail after it, so it needs no compensation
    # inside this saga's own flow.
    StepDefinition(StepName.CREDIT, 4, "account-service", "credit", "credit_compensate"),
)

STEP_BY_NAME: dict[StepName, StepDefinition] = {step.name: step for step in STEPS}


def compensation_order(executed: list[StepName]) -> list[StepDefinition]:
    """Return the steps to compensate, strictly in reverse execution order.

    Only steps that actually executed are returned. Compensating an operation
    that never happened is forbidden by the contract (section 27) and is
    rejected by the services themselves with ORIGINAL_OPERATION_NOT_FOUND.
    """
    executed_set = set(executed)
    return [
        step
        for step in sorted(STEPS, key=lambda item: item.sequence, reverse=True)
        if step.name in executed_set and step.compensation_operation is not None
    ]


def compensation_sequence(step: StepDefinition) -> int:
    """Audit-trail position of a compensation.

    Derived from the forward position so that the later a step ran, the earlier
    it is compensated — and ordering the trail by ``sequence`` proves the
    rollback happened in reverse. It is a pure function of the step, so
    reprocessing the same compensation always lands on the same row.
    """
    from app.persistence.repository import COMPENSATION_SEQUENCE_BASE

    return COMPENSATION_SEQUENCE_BASE + (len(STEPS) + 1 - step.sequence)
