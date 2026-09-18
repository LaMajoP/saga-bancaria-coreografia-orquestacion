"""Saga service: orchestration coordinator and choreography participants."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import configure_logging
from app.persistence.repository import SagaRepository
from app.routes.health import router as health_router
from app.routes.sagas import router as sagas_router

configure_logging()
SagaRepository().initialize()

app = FastAPI(
    title="NovaBank Saga Service",
    version="1.0.0",
    description=(
        "Coordinacion de transacciones distribuidas mediante el patron Saga, "
        "en sus dos modalidades: orquestacion y coreografia."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"service": "saga-service", "docs": "/docs"}


app.include_router(health_router)
app.include_router(sagas_router)
