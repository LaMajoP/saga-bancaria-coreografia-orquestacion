"""Request and response schemas for Account & Ledger operations."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MoneyOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transfer_id: UUID
    amount: int = Field(gt=0, le=1_000_000_000_000)


class AccountResponse(BaseModel):
    account_id: str
    balance: int
    currency: str


class OperationResponse(BaseModel):
    success: Literal[True] = True
    transfer_id: UUID
    account_id: str
    amount: int
    new_balance: int
    status: str


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    transfer_id: str | None = None
    status: str
    error_code: str
    message: str
