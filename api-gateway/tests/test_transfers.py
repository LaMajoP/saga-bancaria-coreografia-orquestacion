import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

test_database_url = os.getenv("TEST_GATEWAY_DATABASE_URL")
if not test_database_url:
    pytest.skip(
        "TEST_GATEWAY_DATABASE_URL is required; tests only run against remote Supabase test data",
        allow_module_level=True,
    )
os.environ["GATEWAY_DATABASE_URL"] = test_database_url

from app.main import app

client = TestClient(app)


def payload() -> dict[str, object]:
    return {
        "source_account_id": "ACC-001",
        "destination_account_id": "ACC-002",
        "amount": "150000.00",
        "currency": "cop",
    }


def test_transfer_is_created_and_can_be_read() -> None:
    key = str(uuid4())
    created = client.post("/api/v1/transfers", json=payload(), headers={"Idempotency-Key": key})

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "RECIBIDA"
    assert body["idempotency_key"] == key

    fetched = client.get(f"/api/v1/transfers/{body['transfer_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["transfer_id"] == body["transfer_id"]


def test_identical_retry_is_idempotent() -> None:
    key = str(uuid4())
    first = client.post("/api/v1/transfers", json=payload(), headers={"Idempotency-Key": key})
    retried = client.post("/api/v1/transfers", json=payload(), headers={"Idempotency-Key": key})

    assert first.status_code == 201
    assert retried.status_code == 200
    assert retried.json()["replayed"] is True
    assert retried.json()["transfer_id"] == first.json()["transfer_id"]


def test_key_cannot_be_reused_with_a_different_payload() -> None:
    key = str(uuid4())
    client.post("/api/v1/transfers", json=payload(), headers={"Idempotency-Key": key})

    conflict = client.post(
        "/api/v1/transfers",
        json={**payload(), "amount": "160000.00"},
        headers={"Idempotency-Key": key},
    )

    assert conflict.status_code == 409
