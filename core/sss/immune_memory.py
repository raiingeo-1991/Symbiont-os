"""SSS v0.1: isolated, persistent immune evidence memory."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


EVIDENCE_KINDS = {"fact", "suspicion", "conclusion"}
SENSITIVE_KEY_PARTS = (
    "secret", "private", "password", "passwd", "token",
    "credential", "recovery", "seed", "api_key", "authorization",
)


class ImmuneMemoryIntegrityError(RuntimeError):
    """Raised when persisted immune evidence fails integrity verification."""


def _canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _safe(value: Any) -> Any:
    """Make JSON-safe evidence and redact obviously sensitive fields."""
    if isinstance(value, dict):
        return {
            str(k): _safe(v)
            for k, v in value.items()
            if not any(part in str(k).lower() for part in SENSITIVE_KEY_PARTS)
        }
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, str):
        value = re.sub(
            r"(?i)\bBearer\s+\S+",
            "Bearer [REDACTED]",
            value,
        )
        value = re.sub(
            r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
            "[REDACTED PRIVATE KEY]",
            value,
            flags=re.DOTALL,
        )
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return f"<unsupported:{type(value).__name__}>"


class ImmuneMemory:
    """Append-only evidence store. It observes evidence; it takes no actions."""

    VERSION = "SSS-IMMUNE-MEMORY/1"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS immune_evidence (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    evidence_id TEXT NOT NULL UNIQUE,
                    source_event_id TEXT NOT NULL,
                    source_event_type TEXT NOT NULL,
                    source_event_hash TEXT NOT NULL,
                    evidence_kind TEXT NOT NULL
                        CHECK (evidence_kind IN ('fact','suspicion','conclusion')),
                    incident_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL,
                    UNIQUE(source_event_id, evidence_kind)
                )
            """)
            self.db.commit()
            self.verify_or_raise()

    @staticmethod
    def _record_hash(record: dict[str, Any]) -> str:
        # SQLite sequence is an ordering index, not part of the evidence body.
        body = {
            k: v for k, v in record.items()
            if k not in {"record_hash", "sequence"}
        }
        return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()

    def verify(self) -> tuple[bool, int]:
        """Verify record hashes and ordering; return (valid, verified_count)."""
        with self.lock:
            previous = "0" * 64
            count = 0
            rows = self.db.execute(
                "SELECT * FROM immune_evidence ORDER BY sequence"
            ).fetchall()
            for row in rows:
                record = dict(row)
                saved_hash = record.pop("record_hash")
                if record["previous_hash"] != previous:
                    return False, count
                record["record_hash"] = saved_hash
                if self._record_hash(record) != saved_hash:
                    return False, count
                previous = saved_hash
                count += 1
            return True, count

    def verify_or_raise(self) -> int:
        valid, count = self.verify()
        if not valid:
            raise ImmuneMemoryIntegrityError(
                "Immune evidence chain failed integrity verification"
            )
        return count

    def record_evidence(
        self,
        *,
        source_event_id: str,
        source_event_type: str,
        source_event_hash: str,
        evidence_kind: str,
        summary: str,
        incident_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> str:
        """Persist one evidence item; repeated identical delivery is idempotent."""
        source_event_id = str(source_event_id).strip()
        source_event_type = str(source_event_type).strip()
        source_event_hash = str(source_event_hash).strip()
        evidence_kind = str(evidence_kind).strip().lower()

        if not source_event_id or not source_event_type:
            raise ValueError("Source event ID and type are required")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", source_event_hash):
            raise ValueError("Source event hash must be a 64-character hex digest")
        if evidence_kind not in EVIDENCE_KINDS:
            raise ValueError(f"Unsupported evidence kind: {evidence_kind}")
        if not str(summary).strip():
            raise ValueError("Evidence summary is required")

        safe_summary = str(_safe(str(summary)))[:1000]
        safe_details = _canonical(_safe(details or {}))
        incident_id = str(incident_id or source_event_id).strip()
        if not incident_id:
            raise ValueError("Incident ID cannot be empty")

        with self.lock:
            existing = self.db.execute(
                """SELECT * FROM immune_evidence
                   WHERE source_event_id = ? AND evidence_kind = ?""",
                (source_event_id, evidence_kind),
            ).fetchone()

            if existing is not None:
                old = dict(existing)
                same = (
                    old["source_event_type"] == source_event_type
                    and old["source_event_hash"] == source_event_hash
                    and old["incident_id"] == incident_id
                    and old["summary"] == safe_summary
                    and old["details_json"] == safe_details
                )
                if not same:
                    raise ValueError(
                        "Conflicting evidence for an already recorded source event"
                    )
                return str(old["evidence_id"])

            valid, _ = self.verify()
            if not valid:
                raise ImmuneMemoryIntegrityError(
                    "Cannot append to a corrupted evidence chain"
                )

            latest = self.db.execute(
                "SELECT record_hash FROM immune_evidence ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous = latest["record_hash"] if latest else "0" * 64

            record = {
                "evidence_id": uuid.uuid4().hex,
                "source_event_id": source_event_id,
                "source_event_type": source_event_type,
                "source_event_hash": source_event_hash.lower(),
                "evidence_kind": evidence_kind,
                "incident_id": incident_id,
                "summary": safe_summary,
                "details_json": safe_details,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "previous_hash": previous,
            }
            record["record_hash"] = self._record_hash(record)

            try:
                self.db.execute("BEGIN IMMEDIATE")
                self.db.execute(
                    """INSERT INTO immune_evidence (
                        evidence_id, source_event_id, source_event_type,
                        source_event_hash, evidence_kind, incident_id, summary,
                        details_json, observed_at, previous_hash, record_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record["evidence_id"], record["source_event_id"],
                        record["source_event_type"], record["source_event_hash"],
                        record["evidence_kind"], record["incident_id"],
                        record["summary"], record["details_json"],
                        record["observed_at"], record["previous_hash"],
                        record["record_hash"],
                    ),
                )
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

            return record["evidence_id"]

    def list_evidence(
        self, incident_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        with self.lock:
            if incident_id is None:
                rows = self.db.execute(
                    "SELECT * FROM immune_evidence ORDER BY sequence"
                ).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT * FROM immune_evidence WHERE incident_id = ? ORDER BY sequence",
                    (incident_id,),
                ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json"))
            result.append(item)
        return result

    def close(self) -> None:
        with self.lock:
            self.db.close()
