"""SCA-1 body identity and lifecycle."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Optional
import time
import uuid


class BodyStatus(str, Enum):
    DETACHED = "DETACHED"
    ATTACHED = "ATTACHED"
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


@dataclass
class BodyIdentity:
    body_id: str
    body_type: str
    bridge_version: str
    capabilities: Dict[str, Any] = field(default_factory=dict)
    public_key: Optional[str] = None
    first_seen: int = field(default_factory=lambda: int(time.time()))
    last_seen: int = field(default_factory=lambda: int(time.time()))
    status: BodyStatus = BodyStatus.DETACHED

    @classmethod
    def create(
        cls,
        body_type: str,
        bridge_version: str,
        capabilities: Optional[Dict[str, Any]] = None,
        public_key: Optional[str] = None,
        body_id: Optional[str] = None,
    ) -> "BodyIdentity":
        return cls(
            body_id=body_id or "BODY-" + uuid.uuid4().hex[:24],
            body_type=str(body_type),
            bridge_version=str(bridge_version),
            capabilities=dict(capabilities or {}),
            public_key=public_key,
        )

    def touch(self) -> None:
        self.last_seen = int(time.time())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "body_id": self.body_id,
            "body_type": self.body_type,
            "bridge_version": self.bridge_version,
            "capabilities": dict(self.capabilities),
            "public_key": self.public_key,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BodyIdentity":
        return cls(
            body_id=str(data["body_id"]),
            body_type=str(data["body_type"]),
            bridge_version=str(data["bridge_version"]),
            capabilities=dict(data.get("capabilities") or {}),
            public_key=data.get("public_key"),
            first_seen=int(data["first_seen"]),
            last_seen=int(data["last_seen"]),
            status=BodyStatus(data.get("status", BodyStatus.DETACHED.value)),
        )
