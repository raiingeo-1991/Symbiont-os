"""SCA-1 Continuity State."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import hashlib
import json
import time


def _canonical(data: Dict[str, Any]) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


@dataclass
class ContinuityState:
    state_version: int = 0
    memory_version: int = 0
    knowledge_version: int = 0
    economy_version: int = 0
    quest_version: int = 0
    p2p_version: int = 0
    active_body: Optional[str] = None
    previous_state_hash: Optional[str] = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    schema: str = "SCA-1"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "state_version": int(self.state_version),
            "memory_version": int(self.memory_version),
            "knowledge_version": int(self.knowledge_version),
            "economy_version": int(self.economy_version),
            "quest_version": int(self.quest_version),
            "p2p_version": int(self.p2p_version),
            "active_body": self.active_body,
            "previous_state_hash": self.previous_state_hash,
            "created_at": int(self.created_at),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical(self.as_dict())

    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def next(self, **changes: Any) -> "ContinuityState":
        data = self.as_dict()
        data.update(changes)
        data["state_version"] = int(self.state_version) + 1
        data["previous_state_hash"] = self.content_hash()
        data["created_at"] = int(time.time())
        return ContinuityState(**data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContinuityState":
        allowed = {
            "schema", "state_version", "memory_version", "knowledge_version",
            "economy_version", "quest_version", "p2p_version", "active_body",
            "previous_state_hash", "created_at"
        }
        return cls(**{k: data[k] for k in allowed if k in data})

    def verify_link(self, previous: Optional["ContinuityState"]) -> bool:
        if previous is None:
            return self.previous_state_hash is None
        return self.previous_state_hash == previous.content_hash()
