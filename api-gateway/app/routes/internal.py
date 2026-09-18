"""Internal endpoint the Saga uses to publish the outcome of a transfer."""

import logging
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.schemas.transfers import TransferResponse, TransferStatus
from app.services.transfer_repository import transfer_repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/v1", tags=["internal"])


class StatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: TransferStatus
    error_code: str | None = None
    message: str | None = None


@router.patch("/transfers/{transfer_id}/status", response_model=TransferResponse)
def update_status(
    transfer_id: UUID,
    request: StatusUpdateRequest,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> TransferResponse:
    """Only the Saga may move a transfer out of RECIBIDA."""
    settings = get_settings()
    if x_internal_token != settings.internal_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token"
        )

    record = transfer_repository.update_status(
        str(transfer_id), request.status, request.error_code, request.message
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found"
        )

    logger.info(
        "transfer_id=%s service=api-gateway operation=status_update status=%s error=%s",
        transfer_id,
        request.status.value,
        request.error_code,
    )
    return record.response()
