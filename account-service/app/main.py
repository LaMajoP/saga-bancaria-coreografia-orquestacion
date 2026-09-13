from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routes.accounts import router as accounts_router
from app.routes.health import router as health_router
from app.services.account_service import AccountServiceError, account_service


account_service.initialize()
app = FastAPI(title="NovaBank Account & Ledger Service", version="1.0.0")


@app.exception_handler(AccountServiceError)
async def account_error_handler(_: Request, error: AccountServiceError) -> JSONResponse:
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


app.include_router(health_router)
app.include_router(accounts_router)
