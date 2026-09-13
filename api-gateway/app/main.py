from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routes.dependencies import router as dependencies_router
from app.routes.health import router as health_router
from app.routes.transfers import router as transfers_router
from app.services.transfer_repository import transfer_repository

settings = get_settings()
transfer_repository.initialize()

app = FastAPI(
    title="NovaBank API Gateway",
    version="1.0.0",
    description="Punto de entrada para transferencias bancarias distribuidas.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"service": "api-gateway", "docs": "/docs"}


app.include_router(health_router)
app.include_router(dependencies_router)
app.include_router(transfers_router)
