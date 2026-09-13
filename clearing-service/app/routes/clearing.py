"""Interbank clearing and compensation endpoints."""

from fastapi import APIRouter

from app.schemas.clearing import (
    ClearingCompensationRequest,
    ClearingResponse,
    ClearingTransferRequest,
)
from app.services.clearing_service import clearing_service

router = APIRouter(prefix="/clearing", tags=["clearing"])


@router.post("/transfer", response_model=ClearingResponse)
def create_clearing(request: ClearingTransferRequest) -> ClearingResponse:
    return clearing_service.transfer(request)


@router.post("/compensate", response_model=ClearingResponse)
def compensate_clearing(request: ClearingCompensationRequest) -> ClearingResponse:
    return clearing_service.compensate(str(request.transfer_id))
