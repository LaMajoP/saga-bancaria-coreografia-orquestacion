"""Public contracts of the Saga service."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChaosOptions(BaseModel):
    force_risk_failure: bool = False
    force_clearing_timeout: bool = False


class SagaTransferRequest(BaseModel):
    """Exactly the body the Gateway hands over (contract 6.1)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    transfer_id: UUID
    source_account_id: str = Field(min_length=1, max_length=64)
    destination_account_id: str = Field(min_length=1, max_length=64)
    amount: int = Field(gt=0, le=1_000_000_000_000)
    currency: str = Field(default="COP", min_length=3, max_length=3)
    chaos: ChaosOptions = Field(default_factory=ChaosOptions)

    @model_validator(mode="after")
    def accounts_must_differ(self) -> "SagaTransferRequest":
        if self.source_account_id == self.destination_account_id:
            raise ValueError("source_account_id and destination_account_id must differ")
        return self


class SagaAcceptedResponse(BaseModel):
    """202 Accepted: the saga owns the outcome from here on."""

    transfer_id: UUID
    status: str = "EN_PROCESO"
    implementation: str


class SagaStepView(BaseModel):
    sequence: int
    step_name: str
    kind: str
    service: str
    operation: str
    status: str
    attempt: int
    error_code: str | None = None
    message: str | None = None
    duration_ms: int | None = None
    created_at: datetime
    updated_at: datetime


class SagaEventView(BaseModel):
    event_id: UUID
    event_type: str
    transfer_id: UUID
    payload: dict[str, Any]
    occurred_at: datetime


class SagaExecutionView(BaseModel):
    transfer_id: UUID
    implementation: str
    status: str
    compensation_status: str
    gateway_status: str
    current_step: str | None = None
    source_account_id: str
    destination_account_id: str
    amount: int
    currency: str
    chaos: ChaosOptions
    error_code: str | None = None
    message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    steps: list[SagaStepView] = Field(default_factory=list)
    events: list[SagaEventView] = Field(default_factory=list)


class SagaExecutionListResponse(BaseModel):
    executions: list[SagaExecutionView]
