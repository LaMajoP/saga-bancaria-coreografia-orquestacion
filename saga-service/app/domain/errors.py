"""Failure classification: it decides whether to retry, compensate or give up."""

from dataclasses import dataclass
from enum import Enum

from app.domain.states import SagaStatus


class FailureKind(str, Enum):
    BUSINESS = "BUSINESS"
    TRANSIENT = "TRANSIENT"
    INTEGRATION = "INTEGRATION"


#: Business rejections. The service answered correctly; the answer was "no".
#: Retrying would only repeat the same rejection, so the saga compensates.
BUSINESS_ERROR_CODES = frozenset(
    {
        "INSUFFICIENT_FUNDS",
        "RISK_REJECTED",
        "RISK_LIMIT_EXCEEDED",
        "CLEARING_TIMEOUT",
    }
)

#: Outcome the saga adopts for each business rejection.
OUTCOME_BY_ERROR_CODE: dict[str, SagaStatus] = {
    "INSUFFICIENT_FUNDS": SagaStatus.REJECTED_FUNDS,
    "RISK_REJECTED": SagaStatus.REJECTED_RISK,
    "RISK_LIMIT_EXCEEDED": SagaStatus.REJECTED_RISK,
    "CLEARING_TIMEOUT": SagaStatus.REJECTED_NETWORK,
}

RETRYABLE_HTTP_STATUS = frozenset({500, 502, 503, 504})


def classify(http_status: int, error_code: str | None) -> FailureKind:
    if error_code in BUSINESS_ERROR_CODES:
        return FailureKind.BUSINESS
    if http_status in RETRYABLE_HTTP_STATUS:
        return FailureKind.TRANSIENT
    return FailureKind.INTEGRATION


def outcome_for(error_code: str | None, default: SagaStatus = SagaStatus.FAILED) -> SagaStatus:
    return OUTCOME_BY_ERROR_CODE.get(error_code or "", default)


@dataclass(frozen=True)
class StepOutcome:
    """Normalized result of one call to a domain service.

    Account answers a rejection with HTTP 409, while Risk and Clearing answer
    with HTTP 200 and ``success: false``. Reading only the status code would
    make CP-03 and CP-04 look successful, so the truth is taken from the body
    and the status code is used only to tell business from technical failures.
    """

    ok: bool
    status: str
    error_code: str | None = None
    message: str | None = None
    response: dict | None = None
    attempts: int = 1
    duration_ms: int = 0
    failure_kind: FailureKind | None = None

    @property
    def is_business_failure(self) -> bool:
        return not self.ok and self.failure_kind is FailureKind.BUSINESS
