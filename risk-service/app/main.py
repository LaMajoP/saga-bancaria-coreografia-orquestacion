"""Risk Service application."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routes.risk import router as risk_router
from app.services.risk_service import RiskServiceError, risk_service

risk_service.initialize()
app = FastAPI(title="Saga Bancaria - Risk Service", version="1.0.0")


@app.exception_handler(RiskServiceError)
async def risk_error_handler(_: Request, error: RiskServiceError) -> JSONResponse:
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
    return {"service": "risk-service", "status": "ok"}


app.include_router(risk_router)
