"""HTTP contracts for interbank clearing operations."""

from typing import Annotated
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class ClearingTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    transfer_id: UUID
    source_account_id: str = Field(min_length=1, max_length=64)
    destination_account_id: str = Field(min_length=1, max_length=64)
    amount: int = Field(gt=0, le=1_000_000_000_000)
    force_clearing_timeout: Annotated[
        bool,
        Field(
            default=False,
            validation_alias=AliasChoices("force_clearing_timeout", "force_timeout"),
        ),
    ]

    @model_validator(mode="after")
    def accounts_must_differ(self) -> "ClearingTransferRequest":
        if self.source_account_id == self.destination_account_id:
            raise ValueError("source_account_id and destination_account_id must differ")
        return self


class ClearingCompensationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transfer_id: UUID


class ClearingResponse(BaseModel):
    success: bool
    transfer_id: UUID
    status: str
    error_code: str | None = None
    message: str | None = None
    latency_seconds: float = 0
    replayed: bool = False
