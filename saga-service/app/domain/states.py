"""Saga state machine and its translation to the Gateway's public vocabulary."""

from enum import Enum


class SagaStatus(str, Enum):
    """Outcome of the saga. Says *what happened*, not whether it was undone."""

    PENDING = "PENDING"
    DEBITED = "DEBITED"
    RISK_APPROVED = "RISK_APPROVED"
    CLEARING_PENDING = "CLEARING_PENDING"
    COMPLETED = "COMPLETED"
    COMPENSATING = "COMPENSATING"
    REJECTED_FUNDS = "REJECTED_FUNDS"
    REJECTED_RISK = "REJECTED_RISK"
    REJECTED_NETWORK = "REJECTED_NETWORK"
    FAILED = "FAILED"


class CompensationStatus(str, Enum):
    """Evidence of the rollback. Orthogonal to SagaStatus on purpose.

    CP-03 requires the final state to be REJECTED_RISK, while the contract
    diagrams end at COMPENSATED. Keeping both fields lets the saga report the
    cause and the rollback at the same time instead of choosing one.
    """

    NOT_REQUIRED = "NOT_REQUIRED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"


class StepName(str, Enum):
    DEBIT = "DEBIT"
    RISK = "RISK"
    CLEARING = "CLEARING"
    CREDIT = "CREDIT"


class StepStatus(str, Enum):
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    COMPENSATED = "COMPENSATED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"


class Implementation(str, Enum):
    ORCHESTRATION = "ORCHESTRATION"
    CHOREOGRAPHY = "CHOREOGRAPHY"


class GatewayStatus(str, Enum):
    """Public vocabulary owned by the API Gateway. The saga only translates."""

    RECEIVED = "RECIBIDA"
    IN_PROGRESS = "EN_PROCESO"
    CONFIRMED = "CONFIRMADA"
    REJECTED_FUNDS = "RECHAZADA_FONDOS"
    REJECTED_RISK = "RECHAZADA_RIESGO"
    REJECTED_NETWORK = "RECHAZADA_RED"
    COMPENSATING = "COMPENSANDO"
    COMPENSATED = "COMPENSADA"
    FAILED = "FALLIDA"


_GATEWAY_STATUS: dict[SagaStatus, GatewayStatus] = {
    SagaStatus.PENDING: GatewayStatus.IN_PROGRESS,
    SagaStatus.DEBITED: GatewayStatus.IN_PROGRESS,
    SagaStatus.RISK_APPROVED: GatewayStatus.IN_PROGRESS,
    SagaStatus.CLEARING_PENDING: GatewayStatus.IN_PROGRESS,
    SagaStatus.COMPLETED: GatewayStatus.CONFIRMED,
    SagaStatus.COMPENSATING: GatewayStatus.COMPENSATING,
    SagaStatus.REJECTED_FUNDS: GatewayStatus.REJECTED_FUNDS,
    SagaStatus.REJECTED_RISK: GatewayStatus.REJECTED_RISK,
    SagaStatus.REJECTED_NETWORK: GatewayStatus.REJECTED_NETWORK,
    SagaStatus.FAILED: GatewayStatus.FAILED,
}

TERMINAL_STATUSES = frozenset(
    {
        SagaStatus.COMPLETED,
        SagaStatus.REJECTED_FUNDS,
        SagaStatus.REJECTED_RISK,
        SagaStatus.REJECTED_NETWORK,
        SagaStatus.FAILED,
    }
)


def to_gateway_status(status: SagaStatus) -> GatewayStatus:
    return _GATEWAY_STATUS[status]
