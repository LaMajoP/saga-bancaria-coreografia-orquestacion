import os
from uuid import uuid4

import httpx
import pytest

test_database_url = os.getenv("TEST_RISK_DATABASE_URL")
if not test_database_url:
    pytest.skip(
        "TEST_RISK_DATABASE_URL is required; tests only run against remote Supabase test data",
        allow_module_level=True,
    )
os.environ["RISK_DATABASE_URL"] = test_database_url

from app.main import app


def payload(transfer_id: str) -> dict[str, object]:
    return {
        "transfer_id": transfer_id,
        "source_account_id": "ACC-001",
        "destination_account_id": "ACC-002",
        "amount": 500_000,
    }


@pytest.mark.anyio
async def test_approved_risk_is_idempotent_and_can_be_compensated() -> None:
    transfer_id = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        approved = await client.post("/risk/check", json=payload(transfer_id))
        retried = await client.post("/risk/check", json=payload(transfer_id))
        compensated = await client.post("/risk/compensate", json={"transfer_id": transfer_id})
        repeated_compensation = await client.post(
            "/risk/compensate", json={"transfer_id": transfer_id}
        )

    assert approved.json()["status"] == "RISK_APPROVED"
    assert retried.json()["replayed"] is True
    assert compensated.json()["status"] == "COMPENSATED"
    assert repeated_compensation.json()["replayed"] is True


@pytest.mark.anyio
async def test_forced_failure_is_rejected() -> None:
    transfer_id = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        rejected = await client.post(
            "/risk/check", json={**payload(transfer_id), "force_risk_failure": True}
        )

    assert rejected.status_code == 200
    assert rejected.json()["success"] is False
    assert rejected.json()["status"] == "RISK_REJECTED"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
