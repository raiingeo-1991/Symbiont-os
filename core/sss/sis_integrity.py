"""SIS integrity adapter for SSS Immune Memory evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.sss.sis_anchor_ledger import AnchorLedger
from core.sss.sis_witness import Anchor, PersistentWitness, WitnessError


class SISIntegrity:
    """Anchor Immune Memory evidence and optionally cross-check a Witness."""

    VERSION = "SIS-SSS-INTEGRITY/1"

    def __init__(
        self,
        root: str | Path,
        witness: PersistentWitness | None = None,
    ):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)

        self.ledger = AnchorLedger(
            root / "anchors.sqlite3",
            root / "checkpoint.json",
            root / "anchor.key",
        )
        self.witness = witness

    def _check_witness(self, *, recover_pending: bool = False) -> str:
        if self.witness is None:
            return "DISABLED"

        local = self.ledger.head_anchor()
        current = self.witness.current
        pending = self.witness.pending

        if pending is not None:
            expected, candidate = pending
            if current != expected:
                raise WitnessError("Pending operation has stale expected state")
            if local == candidate:
                if recover_pending:
                    self.witness.commit(candidate)
                    return "RECOVERED_COMMIT"
                return "RECOVERY_REQUIRED"
            if local == expected:
                raise WitnessError(
                    "Pending Witness operation is not reflected in the Ledger; "
                    "refusing further evidence writes"
                )
            raise WitnessError(
                "Pending Witness operation does not match the verified Ledger head"
            )

        result = self.witness.compare_local(local)
        if result != "MATCH":
            raise WitnessError(f"Witness/Ledger mismatch: {result}")
        return result

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

        if self.witness is None:
            return self.ledger.append(str(evidence["evidence_id"]), summary)

        self._check_witness(recover_pending=True)
        previous = self.ledger.head_anchor()
        record_hash = self.ledger.append(str(evidence["evidence_id"]), summary)
        candidate = self.ledger.head_anchor()

        # Duplicate delivery does not advance the Ledger. Verify its existing
        # anchor rather than asking Witness to prepare a nonexistent transition.
        if candidate == previous:
            self._check_witness(recover_pending=True)
            return record_hash

        if candidate.sequence != previous.sequence + 1:
            raise WitnessError("Ledger sequence did not advance by exactly one")

        self.witness.prepare(previous, candidate)
        self.witness.commit(candidate)
        self._check_witness()
        return record_hash

    def status(self) -> dict[str, Any]:
        valid, count = self.ledger.verify()
        result: dict[str, Any] = {
            "enabled": True,
            "valid": valid,
            "anchored_records": count,
            "version": self.VERSION,
            "witness_enabled": self.witness is not None,
        }
        if self.witness is not None:
            try:
                state = self._check_witness(recover_pending=False)
                result["witness_state"] = state
                result["witness_valid"] = state == "MATCH"
                if state != "MATCH":
                    result["valid"] = False
                    result["witness_error"] = (
                        "Witness synchronization is not complete"
                    )
            except (WitnessError, OSError, ValueError) as exc:
                result["witness_state"] = "ERROR"
                result["witness_valid"] = False
                result["witness_error"] = f"{type(exc).__name__}: {exc}"
                result["valid"] = False
        return result

    def close(self) -> None:
        self.ledger.close()
