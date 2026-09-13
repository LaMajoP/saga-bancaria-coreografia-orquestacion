import os
from uuid import uuid4

import httpx
import pytest

test_database_url = os.getenv("TEST_ACCOUNT_DATABASE_URL")
if not test_database_url:
    pytest.skip(
        "TEST_ACCOUNT_DATABASE_URL is required; tests only run against remote Supabase test data",
        allow_module_level=True,
    )
os.environ["ACCOUNT_DATABASE_URL"] = test_database_url

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
        assert debit.json()["new_balance"] == initial - 500_000
        assert repeated.status_code == 200
        assert repeated.json()["new_balance"] == initial - 500_000
        assert (await client.get("/accounts/ACC-001")).json()["balance"] == initial - 500_000

        compensated = await client.post(
            "/accounts/ACC-001/debit/compensate", json=request_body(transfer_id, 500_000)
        )
        repeated_compensation = await client.post(
            "/accounts/ACC-001/debit/compensate", json=request_body(transfer_id, 500_000)
        )

        assert compensated.json()["status"] == "COMPENSATED"
        assert compensated.json()["new_balance"] == initial
        assert repeated_compensation.status_code == 200
        assert repeated_compensation.json()["new_balance"] == initial
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
async def test_credit_returns_the_resulting_balance_and_is_idempotent() -> None:
    transfer_id = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        initial = (await client.get("/accounts/ACC-002")).json()["balance"]
        credit = await client.post(
            "/accounts/ACC-002/credit", json=request_body(transfer_id, 500_000)
        )
        repeated = await client.post(
            "/accounts/ACC-002/credit", json=request_body(transfer_id, 500_000)
        )

        assert credit.status_code == 200
        assert credit.json()["status"] == "COMPLETED"
        assert credit.json()["new_balance"] == initial + 500_000
        assert repeated.status_code == 200
        assert repeated.json()["new_balance"] == initial + 500_000
        assert (await client.get("/accounts/ACC-002")).json()["balance"] == initial + 500_000

        compensated = await client.post(
            "/accounts/ACC-002/credit/compensate", json=request_body(transfer_id, 500_000)
        )
        assert compensated.status_code == 200
        assert compensated.json()["new_balance"] == initial


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
