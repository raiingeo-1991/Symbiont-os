"""SCA-1 recovery and rollback.

Rollback is append-only: the ledger is never rewritten. A rollback records
a new event pointing to the restored state, preserving the audit trail.
"""

from pathlib import Path
from typing import Optional
import json
import os
import tempfile

from .ledger import ContinuityLedger, ContinuityVerificationError
from .state import ContinuityState


class ContinuityRecovery:
    def __init__(self, state_path: str, ledger: ContinuityLedger):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger = ledger

    def save(self, state: ContinuityState) -> None:
        data = json.dumps(state.as_dict(), sort_keys=True, ensure_ascii=False, indent=2)
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, self.state_path)

    def load(self) -> Optional[ContinuityState]:
        if not self.state_path.exists():
            return None
        return ContinuityState.from_dict(
            json.loads(self.state_path.read_text(encoding="utf-8"))
        )

    def load_or_recover(self) -> Optional[ContinuityState]:
        state = self.load()
        if state is not None:
            return state

        latest = self.ledger.latest()

        if latest is None:
            return None

        snapshot = latest.payload.get("state_snapshot")

        if not isinstance(snapshot, dict):
            raise ContinuityVerificationError(
                "state.json is missing and latest Ledger event has no state snapshot"
            )

        recovered = ContinuityState.from_dict(snapshot)

        if latest.state_hash is None:
            raise ContinuityVerificationError(
                "latest Ledger event has no state hash"
            )

        if recovered.content_hash() != latest.state_hash:
            raise ContinuityVerificationError(
                "recovered state does not match latest Ledger state hash"
            )

        self.save(recovered)
        return recovered

    def rollback(
        self,
        current: ContinuityState,
        target: ContinuityState,
        reason: str = "manual rollback",
    ) -> ContinuityState:
        if target.state_version >= current.state_version:
            raise ValueError("rollback target must be older than current state")

        restored = ContinuityState(
            state_version=current.state_version + 1,
            memory_version=target.memory_version,
            knowledge_version=target.knowledge_version,
            economy_version=target.economy_version,
            quest_version=target.quest_version,
            p2p_version=target.p2p_version,
            active_body=target.active_body,
            previous_state_hash=current.content_hash(),
        )
        event = self.ledger.append(
            "STATE_ROLLBACK",
            restored.state_version,
            {
                "target_state_version": target.state_version,
                "target_state_hash": target.content_hash(),
                "reason": reason,
                "state_snapshot": restored.as_dict(),
            },
            body_id=restored.active_body,
            state_hash=restored.content_hash(),
        )
        self.save(restored)
        return restored

