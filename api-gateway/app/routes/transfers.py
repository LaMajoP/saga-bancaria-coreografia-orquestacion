"""Public endpoints for creating and reading transfer requests."""

from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Response, status

from app.schemas.transfers import TransferListResponse, TransferRequest, TransferResponse
from app.services.saga_dispatcher import dispatch
from app.services.transfer_repository import IdempotencyConflictError, transfer_repository

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])


@router.post("", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
def create_transfer(
    request: TransferRequest,
    response: Response,
    background: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    saga_mode: str | None = Header(default=None, alias="X-Saga-Mode"),
) -> TransferResponse:
    """Register a transfer once, then hand it over to the Saga.

    ``X-Saga-Mode`` lets the demo switch between ORCHESTRATION and CHOREOGRAPHY
    per request. It is a header on purpose: the JSON contract agreed with the
    team stays untouched.
    """
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

    if saga_mode is not None and saga_mode.upper() not in {"ORCHESTRATION", "CHOREOGRAPHY"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="X-Saga-Mode must be ORCHESTRATION or CHOREOGRAPHY",
        )

    try:
        record, replayed = transfer_repository.create_or_retrieve(request, key)
    except IdempotencyConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    response.headers["Idempotency-Key"] = record.idempotency_key
    if replayed:
        # CP-05: a retry returns the original transfer and starts no new saga,
        # so no balance is touched a second time.
        response.status_code = status.HTTP_200_OK
    else:
        background.add_task(dispatch, record, saga_mode)
    return record.response(replayed=replayed)


@router.get("", response_model=TransferListResponse)
def list_transfers() -> TransferListResponse:
    return TransferListResponse(transfers=[record.response() for record in transfer_repository.list()])


@router.get("/{transfer_id}", response_model=TransferResponse)
def get_transfer(transfer_id: UUID) -> TransferResponse:
    record = transfer_repository.get(str(transfer_id))
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found")
    return record.response()
