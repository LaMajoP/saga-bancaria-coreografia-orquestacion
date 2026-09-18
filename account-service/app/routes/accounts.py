"""HTTP endpoints for Account & Ledger local transactions."""

from fastapi import APIRouter

from app.schemas.accounts import AccountResponse, ErrorResponse, MoneyOperationRequest, OperationResponse
from app.services.account_service import account_service

router = APIRouter(prefix="/accounts", tags=["accounts"])
ERROR_RESPONSES = {404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}


@router.get("/{account_id}", response_model=AccountResponse, responses=ERROR_RESPONSES)
def get_account(account_id: str) -> AccountResponse:
    return account_service.get_account(account_id)


@router.post(
    "/{account_id}/debit", response_model=OperationResponse, responses=ERROR_RESPONSES
)
def debit(account_id: str, request: MoneyOperationRequest) -> OperationResponse:
    return account_service.debit(account_id, str(request.transfer_id), request.amount)


@router.post(
    "/{account_id}/credit", response_model=OperationResponse, responses=ERROR_RESPONSES
)
def credit(account_id: str, request: MoneyOperationRequest) -> OperationResponse:
    return account_service.credit(account_id, str(request.transfer_id), request.amount)


@router.post(
    "/{account_id}/debit/compensate", response_model=OperationResponse, responses=ERROR_RESPONSES
)
def compensate_debit(account_id: str, request: MoneyOperationRequest) -> OperationResponse:
    return account_service.compensate_debit(account_id, str(request.transfer_id), request.amount)


@router.post(
    "/{account_id}/credit/compensate", response_model=OperationResponse, responses=ERROR_RESPONSES
)
def compensate_credit(account_id: str, request: MoneyOperationRequest) -> OperationResponse:
    return account_service.compensate_credit(account_id, str(request.transfer_id), request.amount)
