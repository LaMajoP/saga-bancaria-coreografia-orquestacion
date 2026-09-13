"""Public endpoints for creating and reading transfer requests."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Response, status

from app.schemas.transfers import TransferListResponse, TransferRequest, TransferResponse
from app.services.transfer_registry import IdempotencyConflictError, transfer_registry

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])


@router.post("", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
def create_transfer(
    request: TransferRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TransferResponse:
    """Register a transfer once; repeated keys return the original request."""
    if idempotency_key is None:
        key = str(uuid4())
    else:
        try:
            key = str(UUID(idempotency_key))
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Idempotency-Key must be a UUID",
            ) from error

    try:
        record, replayed = transfer_registry.create_or_retrieve(request, key)
    except IdempotencyConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    response.headers["Idempotency-Key"] = record.idempotency_key
    if replayed:
        response.status_code = status.HTTP_200_OK
    return record.response(replayed=replayed)


@router.get("", response_model=TransferListResponse)
def list_transfers() -> TransferListResponse:
    return TransferListResponse(transfers=[record.response() for record in transfer_registry.list()])


@router.get("/{transfer_id}", response_model=TransferResponse)
def get_transfer(transfer_id: UUID) -> TransferResponse:
    record = transfer_registry.get(str(transfer_id))
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found")
    return record.response()
