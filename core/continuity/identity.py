"""SCA-1 continuity identity.

Continuity identity is the identity of the Symbiont, not of a body.
It reuses the existing NodeIdentity Ed25519 implementation when supplied.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional
import hashlib
import time


@dataclass(frozen=True)
class ContinuityIdentity:
    symbiont_id: str
    public_key: str
    algorithm: str = "Ed25519"
    version: str = "SCA-1"

    @classmethod
    def from_node_identity(cls, node_identity: Any) -> "ContinuityIdentity":
        data = node_identity.identity()
        return cls(
            symbiont_id=str(data["node_id"]),
            public_key=str(data["public_key"]),
            algorithm=str(data.get("algorithm", "Ed25519")),
            version="SCA-1",
        )

    def as_dict(self) -> Dict[str, str]:
        return {
            "symbiont_id": self.symbiont_id,
            "public_key": self.public_key,
            "algorithm": self.algorithm,
            "version": self.version,
        }

    def fingerprint(self) -> str:
        return hashlib.sha256(self.public_key.encode("ascii")).hexdigest()

    def validate(self) -> bool:
        return bool(self.symbiont_id and self.public_key and self.algorithm)

