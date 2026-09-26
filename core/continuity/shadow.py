"""SCA-1 Shadow Mode integration.

Observes Core EventJournal and mirrors selected events into an
independent SCA-1 ledger/state store. Core data is never modified.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .identity import ContinuityIdentity
from .ledger import ContinuityLedger, ContinuityVerificationError
from .recovery import ContinuityRecovery
from .state import ContinuityState


class ContinuityShadow:
    VERSION = "SCA-1-SHADOW/1"

    @staticmethod
    def enabled_from_env() -> bool:
        return os.getenv("SYMBIONT_SCA1_SHADOW", "0").strip().lower() in {
            "1", "true", "yes", "on"
        }

    def __init__(self, root: Path, core_identity: Any):
        self.root = Path(root)
        self.path = self.root / "continuity"
        self.path.mkdir(parents=True, exist_ok=True)

        self.identity = ContinuityIdentity(
            symbiont_id=str(core_identity.id()),
            public_key=str(core_identity.public_key()),
            algorithm="Ed25519",
            version="SCA-1",
        )

        self.ledger = ContinuityLedger(self.path / "ledger.jsonl")
        self.recovery = ContinuityRecovery(
            self.path / "state.json",
            self.ledger,
        )

        loaded_state = self.recovery.load_or_recover()
        latest_event = self.ledger.latest()

        if loaded_state is None:
            self.state = ContinuityState()
        else:
            if (
                latest_event is not None
                and loaded_state.content_hash() != latest_event.state_hash
            ):
                raise ContinuityVerificationError(
                    "state.json does not match latest Ledger state"
                )

            self.state = loaded_state

        self._events_seen = {
            event.payload.get("core_event_id")
            for event in self.ledger.events()
        }
        self._events_seen.discard(None)

    @staticmethod
    def _category(event_type: str) -> Optional[str]:
        if event_type.startswith("memory."):
            return "memory_version"
        if event_type.startswith("learning."):
            return "knowledge_version"
        if event_type.startswith("economy."):
            return "economy_version"
        if event_type.startswith("quest."):
            return "quest_version"
        if event_type == "sync.merge" or event_type.startswith("p2p."):
            return "p2p_version"
        return None

    @staticmethod
    def _sca_event_type(event_type: str) -> str:
        mapping = {
            "memory.created": "MEMORY_CREATED",
            "learning.confirmed": "KNOWLEDGE_UPDATED",
            "learning.conflict_resolved": "KNOWLEDGE_UPDATED",

            "economy.escrow_reserved": "ECONOMY_RESERVED",
            "economy.escrow_released": "ECONOMY_RELEASED",
            "economy.escrow_refunded": "ECONOMY_REFUNDED",
            "economy.escrow_frozen": "ECONOMY_FROZEN",

            "quest.created": "QUEST_CREATED",
            "quest.delegated.done": "QUEST_COMPLETED",
            "quest.incoming.done": "QUEST_COMPLETED",

            "sync.merge": "P2P_SYNC",
        }

        return mapping.get(
            event_type,
            "CORE_" + event_type.upper().replace(".", "_")
        )

    @staticmethod
    def _safe_payload(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            try:
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                return dict(payload)
            except Exception:
                return {"repr": repr(payload)}

        return {"value": repr(payload)}

    def on_core_event(self, event: Dict[str, Any]) -> None:
        core_event_id = str(event.get("event_id", ""))

        if not core_event_id or core_event_id in self._events_seen:
            return

        event_type = str(event.get("type", "core.event"))

        category = self._category(event_type)
        changes: Dict[str, Any] = {}

        if category:
            changes[category] = int(
                getattr(self.state, category)
            ) + 1

        next_state = self.state.next(**changes)

        payload = self._safe_payload(
            event.get("payload", {})
        )

        payload["core_event_id"] = core_event_id
        payload["core_event_type"] = event_type
        payload["core_event_hash"] = event.get("hash")
        payload["state_snapshot"] = next_state.as_dict()

        self.ledger.append(
            self._sca_event_type(event_type),
            next_state.state_version,
            payload=payload,
            body_id=next_state.active_body,
            state_hash=next_state.content_hash(),
        )

        self.recovery.save(next_state)
        self.state = next_state
        self._events_seen.add(core_event_id)

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "mode": "shadow",
            "version": self.VERSION,
            "symbiont_id": self.identity.symbiont_id,
            "state_version": self.state.state_version,
            "memory_version": self.state.memory_version,
            "knowledge_version": self.state.knowledge_version,
            "economy_version": self.state.economy_version,
            "quest_version": self.state.quest_version,
            "p2p_version": self.state.p2p_version,
            "ledger_events": len(self.ledger.events()),
            "ledger_valid": self.ledger.tamper_check(),
            "core_mutation": False,
        }

