"""Execution context shared by both saga implementations."""

from dataclasses import asdict, dataclass, field
from typing import Any

from app.clients.services import AccountClient, ClearingClient, GatewayClient, RiskClient
from app.core.config import Settings, get_settings
from app.persistence.repository import SagaRepository


@dataclass(frozen=True)
class SagaRequest:
    """The transfer handed over by the Gateway, unchanged (contract 6.1)."""

    transfer_id: str
    source_account_id: str
    destination_account_id: str
    amount: int
    currency: str = "COP"
    force_risk_failure: bool = False
    force_clearing_timeout: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SagaRequest":
        chaos = payload.get("chaos") or {}
        return cls(
            transfer_id=str(payload["transfer_id"]),
            source_account_id=payload["source_account_id"],
            destination_account_id=payload["destination_account_id"],
            amount=int(payload["amount"]),
            currency=payload.get("currency", "COP"),
            force_risk_failure=bool(
                payload.get("force_risk_failure", chaos.get("force_risk_failure", False))
            ),
            force_clearing_timeout=bool(
                payload.get(
                    "force_clearing_timeout", chaos.get("force_clearing_timeout", False)
                )
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SagaContext:
    """Everything a step needs: the request, persistence and the service clients."""

    request: SagaRequest
    repository: SagaRepository = field(default_factory=SagaRepository)
    settings: Settings = field(default_factory=get_settings)
    accounts: AccountClient = field(default=None)  # type: ignore[assignment]
    risk: RiskClient = field(default=None)  # type: ignore[assignment]
    clearing: ClearingClient = field(default=None)  # type: ignore[assignment]
    gateway: GatewayClient = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.accounts is None:
            self.accounts = AccountClient(self.settings)
        if self.risk is None:
            self.risk = RiskClient(self.settings)
        if self.clearing is None:
            self.clearing = ClearingClient(self.settings)
        if self.gateway is None:
            self.gateway = GatewayClient(self.settings)

    @property
    def transfer_id(self) -> str:
        return self.request.transfer_id
