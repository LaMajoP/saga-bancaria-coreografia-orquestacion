"""Configuration loaded from the environment."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    account_service_url: str
    risk_service_url: str
    clearing_service_url: str
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
    return Settings(
        account_service_url=os.getenv("ACCOUNT_SERVICE_URL", "http://localhost:8001"),
        risk_service_url=os.getenv("RISK_SERVICE_URL", "http://localhost:8002"),
        clearing_service_url=os.getenv("CLEARING_SERVICE_URL", "http://localhost:8003"),
        service_timeout_seconds=float(os.getenv("SERVICE_TIMEOUT_SECONDS", "3")),
        cors_origins=origins or ("http://localhost:5173",),
    )
