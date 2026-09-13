from fastapi import FastAPI

app = FastAPI(title="Saga Bancaria - Risk Service")


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"service": "risk-service", "status": "ok"}

