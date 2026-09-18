"""HTTP access to the domain services, with timeouts and bounded retries."""

from dataclasses import dataclass
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.domain.errors import RETRYABLE_HTTP_STATUS, FailureKind, StepOutcome, classify


@dataclass(frozen=True)
class RawResponse:
    http_status: int
    body: dict[str, Any]
    attempts: int


class ServiceUnavailable(Exception):
    """The service could not be reached within the allowed attempts."""

    def __init__(self, detail: str, attempts: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.attempts = attempts


class ServiceClient:
    """One client per domain service.

    Retries are safe here precisely because every endpoint is idempotent by
    ``transfer_id``: a repeated debit returns the original result instead of
    moving money twice. That property is what turns an unreliable network into
    an eventually consistent saga.
    """

    def __init__(self, name: str, base_url: str, settings: Settings | None = None) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.settings = settings or get_settings()

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.settings.connect_timeout_seconds,
            read=self.settings.read_timeout_seconds,
            write=self.settings.connect_timeout_seconds,
            pool=self.settings.connect_timeout_seconds,
        )

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> RawResponse:
        url = f"{self.base_url}{path}"
        last_detail = ""
        for attempt in range(1, self.settings.max_attempts + 1):
            try:
                with httpx.Client(timeout=self._timeout()) as client:
                    response = client.request(method, url, json=payload)
                if response.status_code in RETRYABLE_HTTP_STATUS:
                    last_detail = f"HTTP {response.status_code} from {self.name}"
                else:
                    try:
                        body = response.json()
                    except ValueError:
                        body = {"success": False, "message": response.text[:500]}
                    if not isinstance(body, dict):
                        body = {"success": False, "message": str(body)[:500]}
                    return RawResponse(response.status_code, body, attempt)
            except httpx.HTTPError as error:
                last_detail = f"{type(error).__name__}: {error}"

            if attempt < self.settings.max_attempts:
                time.sleep(self.settings.backoff_base_seconds * (2 ** (attempt - 1)))

        raise ServiceUnavailable(last_detail, self.settings.max_attempts)

    def call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> StepOutcome:
        started = time.perf_counter()
        try:
            raw = self.request(method, path, payload)
        except ServiceUnavailable as error:
            return StepOutcome(
                ok=False,
                status="FAILED",
                error_code="SERVICE_UNAVAILABLE",
                message=f"{self.name} unreachable after {error.attempts} attempts: {error.detail}",
                response=None,
                attempts=error.attempts,
                duration_ms=int((time.perf_counter() - started) * 1000),
                failure_kind=FailureKind.TRANSIENT,
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        body = raw.body
        # Truth comes from the body, never from the status code alone.
        ok = bool(body.get("success", raw.http_status < 400))
        if ok:
            return StepOutcome(
                ok=True,
                status=str(body.get("status", "OK")),
                response=body,
                attempts=raw.attempts,
                duration_ms=duration_ms,
            )

        error_code = body.get("error_code")
        return StepOutcome(
            ok=False,
            status=str(body.get("status", "FAILED")),
            error_code=error_code,
            message=body.get("message"),
            response=body,
            attempts=raw.attempts,
            duration_ms=duration_ms,
            failure_kind=classify(raw.http_status, error_code),
        )
