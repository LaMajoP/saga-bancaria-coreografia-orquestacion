from fastapi import FastAPI

app = FastAPI(title="Saga Bancaria - Clearing Service")


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"service": "clearing-service", "status": "ok"}
