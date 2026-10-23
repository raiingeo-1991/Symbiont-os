"""SIS integrity adapter for SSS Immune Memory evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.sss.sis_anchor_ledger import AnchorLedger


class SISIntegrity:
    """Anchor Immune Memory evidence without duplicating sensitive details."""

    VERSION = "SIS-SSS-INTEGRITY/1"

    def __init__(self, root: str | Path):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)

        self.ledger = AnchorLedger(
            root / "anchors.sqlite3",
            root / "checkpoint.json",
            root / "anchor.key",
        )

    def anchor_evidence(self, evidence: dict[str, Any]) -> str:
        required = (
            "evidence_id",
            "source_event_id",
            "source_event_type",
            "source_event_hash",
            "evidence_kind",
            "incident_id",
            "record_hash",
        )
        missing = [key for key in required if not evidence.get(key)]
        if missing:
            raise ValueError(
                "Incomplete Immune Memory evidence: " + ", ".join(missing)
            )

        # Anchor provenance and the memory record hash, not raw details.
        manifest = {
            "version": self.VERSION,
            "evidence_id": str(evidence["evidence_id"]),
            "source_event_id": str(evidence["source_event_id"]),
            "source_event_type": str(evidence["source_event_type"]),
            "source_event_hash": str(evidence["source_event_hash"]),
            "evidence_kind": str(evidence["evidence_kind"]),
            "incident_id": str(evidence["incident_id"]),
            "memory_record_hash": str(evidence["record_hash"]),
        }
        summary = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        return self.ledger.append(str(evidence["evidence_id"]), summary)

    def status(self) -> dict[str, Any]:
        valid, count = self.ledger.verify()
        return {
            "enabled": True,
            "valid": valid,
            "anchored_records": count,
            "version": self.VERSION,
        }

    def close(self) -> None:
        self.ledger.close()
