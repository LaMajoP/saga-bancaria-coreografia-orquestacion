import os
from uuid import uuid4

import httpx
import pytest

test_database_url = os.getenv("TEST_CLEARING_DATABASE_URL")
if not test_database_url:
    pytest.skip(
        "TEST_CLEARING_DATABASE_URL is required; tests only run against remote Supabase test data",
        allow_module_level=True,
    )
os.environ["CLEARING_DATABASE_URL"] = test_database_url
os.environ["CLEARING_LATENCY_SECONDS"] = "0"
os.environ["CLEARING_TIMEOUT_SECONDS"] = "3"

from app.main import app


def payload(transfer_id: str) -> dict[str, object]:
    return {
        "transfer_id": transfer_id,
        "source_account_id": "ACC-001",
        "destination_account_id": "ACC-002",
        "amount": 500_000,
    }


@pytest.mark.anyio
async def test_completed_clearing_is_idempotent_and_can_be_compensated() -> None:
    transfer_id = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        completed = await client.post("/clearing/transfer", json=payload(transfer_id))
        retried = await client.post("/clearing/transfer", json=payload(transfer_id))
        compensated = await client.post(
            "/clearing/compensate", json={"transfer_id": transfer_id}
        )

    assert completed.json()["status"] == "COMPLETED"
    assert retried.json()["replayed"] is True
    assert compensated.json()["status"] == "COMPENSATED"


@pytest.mark.anyio
async def test_forced_timeout_is_rejected() -> None:
    transfer_id = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        rejected = await client.post(
            "/clearing/transfer", json={**payload(transfer_id), "force_clearing_timeout": True}
        )

    assert rejected.status_code == 200
    assert rejected.json()["success"] is False
    assert rejected.json()["status"] == "REJECTED_NETWORK"
    assert rejected.json()["error_code"] == "CLEARING_TIMEOUT"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
