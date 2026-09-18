from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "saga-service", "status": "UP"}


@router.get("/api/v1/sagas/config")
def config() -> dict[str, object]:
    """Expose the knobs Persona 3 needs for the demo (delays, mode)."""
    settings = get_settings()
    return {
        "step_delay_seconds": settings.step_delay_seconds,
        "use_prefect": settings.use_prefect,
        "notify_gateway": settings.notify_gateway,
        "max_attempts": settings.max_attempts,
        "read_timeout_seconds": settings.read_timeout_seconds,
        "exchange": settings.exchange,
    }
