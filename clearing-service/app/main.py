"""Clearing Service application."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routes.clearing import router as clearing_router
from app.services.clearing_service import ClearingServiceError, clearing_service

clearing_service.initialize()
app = FastAPI(title="Saga Bancaria - Clearing Service", version="1.0.0")


@app.exception_handler(ClearingServiceError)
async def clearing_error_handler(_: Request, error: ClearingServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=error.http_status,
        content={
            "success": False,
            "transfer_id": error.transfer_id,
            "status": error.status,
            "error_code": error.error_code,
            "message": error.message,
        },
    )


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"service": "clearing-service", "status": "ok"}


app.include_router(clearing_router)
