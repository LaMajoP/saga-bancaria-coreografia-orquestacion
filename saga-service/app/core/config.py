"""Configuration for the Saga layer, loaded from the environment."""

from dataclasses import dataclass
from functools import lru_cache
import os


def _float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"{name} must be numeric") from error
    if value < 0:
        raise RuntimeError(f"{name} cannot be negative")
    return value


def _int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if value < 1:
        raise RuntimeError(f"{name} must be at least 1")
    return value


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, "true" if default else "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass(frozen=True)
class Settings:
    """Everything the Saga needs to talk to the rest of the system."""

    account_service_url: str
    risk_service_url: str
    clearing_service_url: str
    gateway_url: str
    internal_token: str

    # Observability: the pause between micro-steps that makes the flow visible.
    step_delay_seconds: float

    # Resilience.
    connect_timeout_seconds: float
    read_timeout_seconds: float
    max_attempts: int
    backoff_base_seconds: float

    use_prefect: bool
    notify_gateway: bool

    broker_url: str
    exchange: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Clearing sleeps on purpose to simulate interbank latency. A read timeout
    # shorter than that latency would turn CP-01 into a false CP-04, so the
    # margin is derived from the same variable the Clearing service reads.
    clearing_latency = _float("CLEARING_LATENCY_SECONDS", 0.0)
    default_read_timeout = clearing_latency + 10.0

    return Settings(
        account_service_url=os.getenv("ACCOUNT_SERVICE_URL", "http://localhost:8001"),
        risk_service_url=os.getenv("RISK_SERVICE_URL", "http://localhost:8002"),
        clearing_service_url=os.getenv("CLEARING_SERVICE_URL", "http://localhost:8003"),
        gateway_url=os.getenv("GATEWAY_URL", "http://localhost:8000"),
        internal_token=os.getenv("SAGA_INTERNAL_TOKEN", "local-development-token"),
        step_delay_seconds=_float("SAGA_STEP_DELAY_SECONDS", 3.0),
        connect_timeout_seconds=_float("SAGA_CONNECT_TIMEOUT_SECONDS", 5.0),
        read_timeout_seconds=_float("SAGA_READ_TIMEOUT_SECONDS", default_read_timeout),
        max_attempts=_int("SAGA_MAX_ATTEMPTS", 3),
        backoff_base_seconds=_float("SAGA_BACKOFF_BASE_SECONDS", 0.5),
        use_prefect=_bool("SAGA_USE_PREFECT", True),
        notify_gateway=_bool("SAGA_NOTIFY_GATEWAY", True),
        broker_url=os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
        exchange=os.getenv("SAGA_EXCHANGE", "saga.events"),
    )
