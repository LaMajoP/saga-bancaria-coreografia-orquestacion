"""Endpoints that expose downstream service availability."""

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["dependencies"])


async def _check_service(client: httpx.AsyncClient, name: str, url: str) -> dict[str, Any]:
    try:
        response = await client.get(f"{url.rstrip('/')}/health")
        return {
            "service": name,
            "status": "UP" if response.is_success else "DOWN",
            "http_status": response.status_code,
        }
    except httpx.HTTPError as error:
        return {"service": name, "status": "DOWN", "detail": str(error)}


@router.get("/dependencies/health")
async def dependencies_health() -> dict[str, Any]:
    """Check Account, Risk and Clearing without changing any transfer state."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.service_timeout_seconds) as client:
        services = await asyncio.gather(
            *(
                _check_service(client, name, url)
                for name, url in settings.service_urls.items()
            )
        )
    overall_status = "UP" if all(item["status"] == "UP" for item in services) else "DEGRADED"
    return {"status": overall_status, "services": services}
