"""Hands a created transfer over to the Saga layer (contract section 6.1).

The Gateway owns the public record of a transfer but executes no banking
operation itself: it neither debits, evaluates risk, clears nor credits. Once
the transfer exists, it is delivered to the Saga, which becomes the owner of
the outcome and reports it back through the internal status endpoint.
"""

import logging

import httpx

from app.core.config import get_settings
from app.services.transfer_repository import TransferRecord, transfer_repository

logger = logging.getLogger(__name__)


def build_payload(record: TransferRecord) -> dict[str, object]:
    """The body agreed in section 6.1, delivered without modification."""
    return {
        "transfer_id": record.transfer_id,
        "source_account_id": record.source_account_id,
        "destination_account_id": record.destination_account_id,
        "amount": int(record.amount),
        "currency": record.currency,
        "chaos": {
            "force_risk_failure": record.chaos.force_risk_failure,
            "force_clearing_timeout": record.chaos.force_clearing_timeout,
        },
    }


def dispatch(record: TransferRecord, saga_mode: str | None = None) -> None:
    """Deliver the transfer to the Saga and record the attempt in the outbox."""
    settings = get_settings()
    mode = (saga_mode or settings.saga_mode).upper()
    payload = build_payload(record)
    transfer_repository.record_outbox(record.transfer_id, mode, payload)

    url = f"{settings.saga_service_url.rstrip('/')}/api/v1/sagas/transfers"
    try:
        with httpx.Client(timeout=settings.service_timeout_seconds) as client:
            response = client.post(url, json=payload, params={"mode": mode})
        if response.is_success:
            transfer_repository.mark_outbox(record.transfer_id, "DELIVERED")
            logger.info(
                "transfer_id=%s service=api-gateway operation=saga_dispatch status=success mode=%s",
                record.transfer_id,
                mode,
            )
            return
        detail = f"HTTP {response.status_code}: {response.text[:200]}"
    except httpx.HTTPError as error:
        detail = f"{type(error).__name__}: {error}"

    # The transfer stays RECIBIDA and the outbox row keeps the reason, so the
    # delivery can be retried without creating a second operation.
    transfer_repository.mark_outbox(record.transfer_id, "FAILED", detail)
    logger.error(
        "transfer_id=%s service=api-gateway operation=saga_dispatch status=failed error=%s",
        record.transfer_id,
        detail,
    )
