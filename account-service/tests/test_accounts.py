import os
from uuid import uuid4

import httpx
import pytest

os.environ["ACCOUNT_DB_PATH"] = f"/tmp/account-service-tests-{uuid4()}.db"

from app.main import app


def request_body(transfer_id: str, amount: int) -> dict[str, object]:
    return {"transfer_id": transfer_id, "amount": amount}


@pytest.mark.anyio
async def test_debit_is_idempotent_and_can_be_compensated() -> None:
    transfer_id = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        initial = (await client.get("/accounts/ACC-001")).json()["balance"]
        debit = await client.post(
            "/accounts/ACC-001/debit", json=request_body(transfer_id, 500_000)
        )
        repeated = await client.post(
            "/accounts/ACC-001/debit", json=request_body(transfer_id, 500_000)
        )

        assert debit.status_code == 200
        assert debit.json()["status"] == "DEBITED"
        assert repeated.status_code == 200
        assert (await client.get("/accounts/ACC-001")).json()["balance"] == initial - 500_000

        compensated = await client.post(
            "/accounts/ACC-001/debit/compensate", json=request_body(transfer_id, 500_000)
        )
        repeated_compensation = await client.post(
            "/accounts/ACC-001/debit/compensate", json=request_body(transfer_id, 500_000)
        )

        assert compensated.json()["status"] == "COMPENSATED"
        assert repeated_compensation.status_code == 200
        assert (await client.get("/accounts/ACC-001")).json()["balance"] == initial


@pytest.mark.anyio
async def test_insufficient_funds_does_not_create_a_debit() -> None:
    transfer_id = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        initial = (await client.get("/accounts/ACC-003")).json()["balance"]
        response = await client.post(
            "/accounts/ACC-003/debit", json=request_body(transfer_id, initial + 1)
        )

        assert response.status_code == 409
        assert response.json()["status"] == "REJECTED_FUNDS"
        assert response.json()["error_code"] == "INSUFFICIENT_FUNDS"
        assert (await client.get("/accounts/ACC-003")).json()["balance"] == initial


@pytest.mark.anyio
async def test_credit_must_exist_before_it_can_be_compensated() -> None:
    transfer_id = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        rejected = await client.post(
            "/accounts/ACC-002/credit/compensate", json=request_body(transfer_id, 100)
        )

        assert rejected.status_code == 409
        assert rejected.json()["error_code"] == "ORIGINAL_OPERATION_NOT_FOUND"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
