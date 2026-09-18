"""Configuration loaded from the environment."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    account_service_url: str
    risk_service_url: str
    clearing_service_url: str
    saga_service_url: str
    saga_mode: str
    internal_token: str
    service_timeout_seconds: float
    cors_origins: tuple[str, ...]

    @property
    def service_urls(self) -> dict[str, str]:
        return {
            "account-service": self.account_service_url,
            "risk-service": self.risk_service_url,
            "clearing-service": self.clearing_service_url,
        }


def get_settings() -> Settings:
    origins = tuple(
        item.strip()
        for item in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
        ).split(",")
        if item.strip()
    )
    mode = os.getenv("SAGA_MODE", "ORCHESTRATION").strip().upper()
    if mode not in {"ORCHESTRATION", "CHOREOGRAPHY"}:
        raise RuntimeError("SAGA_MODE must be ORCHESTRATION or CHOREOGRAPHY")
    return Settings(
        account_service_url=os.getenv("ACCOUNT_SERVICE_URL", "http://localhost:8001"),
        risk_service_url=os.getenv("RISK_SERVICE_URL", "http://localhost:8002"),
        clearing_service_url=os.getenv("CLEARING_SERVICE_URL", "http://localhost:8003"),
        saga_service_url=os.getenv("SAGA_SERVICE_URL", "http://localhost:8004"),
        saga_mode=mode,
        internal_token=os.getenv("SAGA_INTERNAL_TOKEN", "local-development-token"),
        service_timeout_seconds=float(os.getenv("SERVICE_TIMEOUT_SECONDS", "10")),
        cors_origins=origins or ("http://localhost:5173",),
    )
