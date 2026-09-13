"""Risk evaluation and compensation endpoints."""

from fastapi import APIRouter

from app.schemas.risk import RiskCheckRequest, RiskCompensationRequest, RiskResponse
from app.services.risk_service import risk_service

router = APIRouter(prefix="/risk", tags=["risk"])


@router.post("/check", response_model=RiskResponse)
def check_risk(request: RiskCheckRequest) -> RiskResponse:
    return risk_service.check(request)


@router.post("/compensate", response_model=RiskResponse)
def compensate_risk(request: RiskCompensationRequest) -> RiskResponse:
    return risk_service.compensate(str(request.transfer_id))
