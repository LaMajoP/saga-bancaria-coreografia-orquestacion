"""Domain events of the choreographed saga (contract sections 11 and 12)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any
from uuid import uuid4


class EventType(str, Enum):
    # --- Events listed in the contract ---
    TRANSFER_REQUESTED = "TransferRequested"
    BALANCE_DEBITED = "BalanceDebited"
    RISK_APPROVED = "RiskApproved"
    RISK_REJECTED = "RiskRejected"
    CLEARING_REQUESTED = "ClearingRequested"
    TRANSFER_COMPLETED = "TransferCompleted"
    TRANSFER_FAILED = "TransferFailed"
    DEBIT_COMPENSATION_REQUESTED = "DebitCompensationRequested"
    RISK_COMPENSATION_REQUESTED = "RiskCompensationRequested"
    DEBIT_COMPENSATED = "DebitCompensated"
    RISK_COMPENSATED = "RiskCompensated"

    # --- Additions agreed under contract section 24 ---
    # The contract's list jumps from ClearingRequested to TransferCompleted and
    # leaves no event able to trigger the credit, nor to undo a clearing that
    # already happened. These four close those gaps.
    CLEARING_COMPLETED = "ClearingCompleted"
    CLEARING_COMPENSATION_REQUESTED = "ClearingCompensationRequested"
    CLEARING_COMPENSATED = "ClearingCompensated"
    TRANSFER_COMPENSATED = "TransferCompensated"


@dataclass(frozen=True)
class DomainEvent:
    """Envelope fixed by contract section 12."""

    event_type: EventType
    transfer_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json(self) -> bytes:
        return json.dumps(
            {
                "event_id": self.event_id,
                "event_type": self.event_type.value,
                "transfer_id": self.transfer_id,
                "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
                "payload": self.payload,
            },
            separators=(",", ":"),
        ).encode()

    @classmethod
    def from_json(cls, raw: bytes) -> "DomainEvent":
        data = json.loads(raw)
        return cls(
            event_type=EventType(data["event_type"]),
            transfer_id=str(data["transfer_id"]),
            payload=data.get("payload") or {},
            event_id=str(data["event_id"]),
            timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")),
        )


#: Queue -> routing keys. One durable queue per participant; the projector and
#: the audit log bind to everything.
TOPOLOGY: dict[str, tuple[str, ...]] = {
    "saga.account": (
        EventType.TRANSFER_REQUESTED.value,
        EventType.RISK_REJECTED.value,
        EventType.CLEARING_COMPLETED.value,
        EventType.DEBIT_COMPENSATION_REQUESTED.value,
        EventType.RISK_COMPENSATED.value,
    ),
    "saga.risk": (
        EventType.BALANCE_DEBITED.value,
        EventType.RISK_COMPENSATION_REQUESTED.value,
    ),
    "saga.clearing": (
        EventType.RISK_APPROVED.value,
        EventType.CLEARING_COMPENSATION_REQUESTED.value,
    ),
    "saga.projector": ("#",),
    "saga.audit": ("#",),
}
