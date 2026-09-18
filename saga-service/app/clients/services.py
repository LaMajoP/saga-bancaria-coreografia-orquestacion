"""Typed wrappers over the endpoints published by Persona 1."""

from typing import Any

from app.clients.base import ServiceClient
from app.core.config import Settings, get_settings
from app.domain.errors import StepOutcome


class AccountClient(ServiceClient):
    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        super().__init__("account-service", settings.account_service_url, settings)

    def get_balance(self, account_id: str) -> int | None:
        outcome = self.call("GET", f"/accounts/{account_id}")
        if not outcome.ok or outcome.response is None:
            return None
        return int(outcome.response["balance"])

    def debit(self, account_id: str, transfer_id: str, amount: int) -> StepOutcome:
        return self.call(
            "POST",
            f"/accounts/{account_id}/debit",
            {"transfer_id": transfer_id, "amount": amount},
        )

    def credit(self, account_id: str, transfer_id: str, amount: int) -> StepOutcome:
        return self.call(
            "POST",
            f"/accounts/{account_id}/credit",
            {"transfer_id": transfer_id, "amount": amount},
        )

    def compensate_debit(self, account_id: str, transfer_id: str, amount: int) -> StepOutcome:
        return self.call(
            "POST",
            f"/accounts/{account_id}/debit/compensate",
            {"transfer_id": transfer_id, "amount": amount},
        )

    def compensate_credit(self, account_id: str, transfer_id: str, amount: int) -> StepOutcome:
        return self.call(
            "POST",
            f"/accounts/{account_id}/credit/compensate",
            {"transfer_id": transfer_id, "amount": amount},
        )


class RiskClient(ServiceClient):
    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        super().__init__("risk-service", settings.risk_service_url, settings)

    def check(
        self,
        transfer_id: str,
        source_account_id: str,
        destination_account_id: str,
        amount: int,
        force_risk_failure: bool,
    ) -> StepOutcome:
        return self.call(
            "POST",
            "/risk/check",
            {
                "transfer_id": transfer_id,
                "source_account_id": source_account_id,
                "destination_account_id": destination_account_id,
                "amount": amount,
                "force_risk_failure": force_risk_failure,
            },
        )

    def compensate(self, transfer_id: str) -> StepOutcome:
        return self.call("POST", "/risk/compensate", {"transfer_id": transfer_id})


class ClearingClient(ServiceClient):
    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        super().__init__("clearing-service", settings.clearing_service_url, settings)

    def transfer(
        self,
        transfer_id: str,
        source_account_id: str,
        destination_account_id: str,
        amount: int,
        force_clearing_timeout: bool,
    ) -> StepOutcome:
        return self.call(
            "POST",
            "/clearing/transfer",
            {
                "transfer_id": transfer_id,
                "source_account_id": source_account_id,
                "destination_account_id": destination_account_id,
                "amount": amount,
                "force_clearing_timeout": force_clearing_timeout,
            },
        )

    def compensate(self, transfer_id: str) -> StepOutcome:
        return self.call("POST", "/clearing/compensate", {"transfer_id": transfer_id})


class GatewayClient(ServiceClient):
    """Pushes the public status back to the Gateway (contract section 6.1)."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        super().__init__("api-gateway", settings.gateway_url, settings)
        self.token = settings.internal_token

    def notify_status(
        self,
        transfer_id: str,
        status: str,
        error_code: str | None = None,
        message: str | None = None,
    ) -> bool:
        payload: dict[str, Any] = {
            "status": status,
            "error_code": error_code,
            "message": message,
        }
        url = f"{self.base_url}/internal/v1/transfers/{transfer_id}/status"
        import httpx

        try:
            with httpx.Client(timeout=self._timeout()) as client:
                response = client.patch(
                    url, json=payload, headers={"X-Internal-Token": self.token}
                )
            return response.is_success
        except httpx.HTTPError:
            # The Gateway is a projection, not a participant: losing a status
            # notification must never abort or alter the saga itself.
            return False
