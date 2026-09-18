"""Structured logging in the format agreed in the contract (section 20)."""

import logging
import os
import sys

logger = logging.getLogger("saga")


def configure_logging() -> None:
    level = os.getenv("SAGA_LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def log_step(
    *,
    transfer_id: str,
    service: str,
    operation: str,
    status: str,
    error: str | None = None,
    **extra: object,
) -> None:
    """Emit one line per operation so a transfer can be reconstructed from logs."""
    parts = [
        f"transfer_id={transfer_id}",
        f"service={service}",
        f"operation={operation}",
        f"status={status}",
    ]
    if error:
        parts.append(f"error={error}")
    parts.extend(f"{key}={value}" for key, value in extra.items())
    logger.info(" ".join(parts))
