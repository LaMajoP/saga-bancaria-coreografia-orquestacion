"""Models exposed by the public transfer API."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TransferStatus(str, Enum):
    RECEIVED = "RECIBIDA"
    IN_PROGRESS = "EN_PROCESO"
    CONFIRMED = "CONFIRMADA"
    REJECTED_FUNDS = "RECHAZADA_FONDOS"
    REJECTED_RISK = "RECHAZADA_RIESGO"
    REJECTED_NETWORK = "RECHAZADA_RED"
    COMPENSATING = "COMPENSANDO"
    COMPENSATED = "COMPENSADA"
    FAILED = "FALLIDA"


class ChaosOptions(BaseModel):
    """Failure switches to be consumed later by the Saga implementation."""

    force_risk_failure: bool = False
    force_clearing_timeout: bool = False


class TransferRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_account_id: str = Field(min_length=1, max_length=64)
    destination_account_id: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="COP", min_length=3, max_length=3)
    chaos: ChaosOptions = Field(default_factory=ChaosOptions)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("amount")
    @classmethod
    def amount_must_be_whole_cop_pesos(cls, value: Decimal) -> Decimal:
        if value != value.to_integral_value():
            raise ValueError("amount must be a whole number of COP pesos")
        return value

    @model_validator(mode="after")
    def accounts_must_differ(self) -> "TransferRequest":
        if self.source_account_id == self.destination_account_id:
            raise ValueError("source_account_id and destination_account_id must differ")
        return self


class TransferResponse(BaseModel):
    transfer_id: str
    idempotency_key: str
    status: TransferStatus
    source_account_id: str
    destination_account_id: str
    amount: Decimal
    currency: str
    chaos: ChaosOptions
    created_at: datetime
    updated_at: datetime
    replayed: bool = False


class TransferListResponse(BaseModel):
    transfers: list[TransferResponse]
