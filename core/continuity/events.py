"""SCA-1 continuity events."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import hashlib
import json
import time
import uuid


def canonical_event(data: Dict[str, Any]) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


@dataclass
class ContinuityEvent:
    event_type: str
    event_sequence: int
    state_version: int
    payload: Dict[str, Any] = field(default_factory=dict)
    body_id: Optional[str] = None
    timestamp: int = field(default_factory=lambda: int(time.time()))
    event_id: str = field(default_factory=lambda: "SCAE-" + uuid.uuid4().hex)
    previous_event_hash: Optional[str] = None
    state_hash: Optional[str] = None
    payload_hash: Optional[str] = None
    signature: Optional[str] = None
    schema: str = "SCA-1"

    def unsigned_dict(self) -> Dict[str, Any]:
        payload_hash = self.payload_hash or hashlib.sha256(
            canonical_event(self.payload)
        ).hexdigest()
        self.payload_hash = payload_hash
        return {
            "schema": self.schema,
            "event_id": self.event_id,
            "event_type": str(self.event_type),
            "event_sequence": int(self.event_sequence),
            "state_version": int(self.state_version),
            "timestamp": int(self.timestamp),
            "body_id": self.body_id,
            "previous_event_hash": self.previous_event_hash,
            "state_hash": self.state_hash,
            "payload_hash": payload_hash,
            "payload": self.payload,
        }

    def signing_bytes(self) -> bytes:
        return canonical_event(self.unsigned_dict())

    def content_hash(self) -> str:
        return hashlib.sha256(self.signing_bytes()).hexdigest()

    def as_dict(self) -> Dict[str, Any]:
        data = self.unsigned_dict()
        data["signature"] = self.signature
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContinuityEvent":
        return cls(
            schema=data.get("schema", "SCA-1"),
            event_id=data["event_id"],
            event_type=data["event_type"],
            event_sequence=int(data["event_sequence"]),
            state_version=int(data["state_version"]),
            timestamp=int(data["timestamp"]),
            body_id=data.get("body_id"),
            previous_event_hash=data.get("previous_event_hash"),
            state_hash=data.get("state_hash"),
            payload_hash=data.get("payload_hash"),
            signature=data.get("signature"),
            payload=dict(data.get("payload") or {}),
        )

