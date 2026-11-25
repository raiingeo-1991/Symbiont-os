"""SCA-1 append-only continuity ledger."""

from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import json
import os
import threading

from .events import ContinuityEvent


class ContinuityVerificationError(Exception):
    pass


class ContinuityLedger:
    VERSION = "SCA-1"

    def __init__(
        self,
        path: Optional[str] = None,
        signer: Optional[Any] = None,
        max_event_age: Optional[int] = None,
    ):
        self.path = Path(path) if path else None
        self.signer = signer
        self.max_event_age = max_event_age
        self._events: List[ContinuityEvent] = []
        self._lock = threading.RLock()
        self._write_failed = False
        self._write_failure_reason: Optional[str] = None
        self.high_water_path = (
            self.path.with_suffix(self.path.suffix + ".highwater")
            if self.path else None
        )
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    def _load(self) -> None:
        if not self.path:
            return

        ledger_exists = self.path.exists()
        anchor_exists = bool(
            self.high_water_path and self.high_water_path.exists()
        )

        if not ledger_exists:
            if anchor_exists:
                raise ContinuityVerificationError(
                    "ledger missing while high-water anchor exists"
                )
            return

        try:
            raw_lines = self.path.read_text(encoding="utf-8").splitlines()
            events = [
                ContinuityEvent.from_dict(json.loads(line))
                for line in raw_lines
                if line.strip()
            ]
        except Exception as exc:
            raise ContinuityVerificationError(
                "ledger file is malformed or unreadable"
            ) from exc

        self._events = events
        self.verify()
        self._verify_high_water()

    def _fsync_parent(self, path: Path) -> None:
        """Persist directory-entry changes where the filesystem supports it."""
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        fd = os.open(str(path.parent), flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _write_high_water(self, event: ContinuityEvent) -> None:
        if not self.high_water_path:
            return

        data = {
            "schema": self.VERSION,
            "event_sequence": int(event.event_sequence),
            "event_hash": event.content_hash(),
            "event_id": event.event_id,
        }

        tmp = self.high_water_path.with_suffix(
            self.high_water_path.suffix + ".tmp"
        )
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps(
                    data, sort_keys=True, ensure_ascii=False, indent=2
                ))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.high_water_path)
            self._fsync_parent(self.high_water_path)
        finally:
            # Safe after replace (the temporary path no longer exists).
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def _verify_high_water(self) -> None:
        if not self.high_water_path:
            return

        if not self.high_water_path.exists():
            if self._events:
                raise ContinuityVerificationError(
                    "high-water anchor missing"
                )
            return

        if not self._events:
            raise ContinuityVerificationError(
                "ledger empty while high-water anchor exists"
            )

        try:
            anchor = json.loads(
                self.high_water_path.read_text(encoding="utf-8")
            )
            if not isinstance(anchor, dict):
                raise ValueError("anchor must be an object")
            if anchor.get("schema") != self.VERSION:
                raise ValueError("anchor schema mismatch")
            anchor_sequence = anchor.get("event_sequence")
            if (
                isinstance(anchor_sequence, bool)
                or not isinstance(anchor_sequence, int)
                or anchor_sequence < 1
            ):
                raise ValueError("invalid anchor sequence")
            anchor_hash = anchor.get("event_hash")
            anchor_event_id = anchor.get("event_id")
            if not isinstance(anchor_hash, str) or not anchor_hash:
                raise ValueError("invalid anchor hash")
            if not isinstance(anchor_event_id, str) or not anchor_event_id:
                raise ValueError("invalid anchor event id")
        except Exception as exc:
            raise ContinuityVerificationError(
                "invalid high-water anchor"
            ) from exc

        latest = self._events[-1]

        if latest.event_sequence < anchor_sequence:
            raise ContinuityVerificationError(
                "ledger rollback detected: sequence below high-water"
            )

        if latest.event_sequence > anchor_sequence:
            raise ContinuityVerificationError(
                "ledger ahead of high-water anchor"
            )

        if (
            anchor_hash != latest.content_hash()
            or anchor_event_id != latest.event_id
        ):
            raise ContinuityVerificationError(
                "ledger rollback detected: latest event differs from high-water"
            )

    def _append_disk(self, event: ContinuityEvent) -> None:
        if not self.path:
            return
        line = json.dumps(
            event.as_dict(), sort_keys=True, ensure_ascii=False
        ) + "\n"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        self._fsync_parent(self.path)

    def _sign(self, event: ContinuityEvent) -> None:
        if self.signer is not None:
            event.signature = self.signer.sign(event.signing_bytes())

    def _verify_signature(self, event: ContinuityEvent) -> bool:
        if self.signer is None:
            return True
        if not event.signature:
            return False
        return bool(self.signer.verify(event.signing_bytes(), event.signature))

    def append(
        self,
        event_type: str,
        state_version: int,
        payload: Optional[Dict[str, Any]] = None,
        body_id: Optional[str] = None,
        state_hash: Optional[str] = None,
    ) -> ContinuityEvent:
        with self._lock:
            if self._write_failed:
                raise ContinuityVerificationError(
                    "ledger writes disabled after persistence failure: "
                    + str(self._write_failure_reason or "unknown error")
                )

            previous = self._events[-1] if self._events else None
            sequence = previous.event_sequence + 1 if previous else 1
            event = ContinuityEvent(
                event_type=event_type,
                event_sequence=sequence,
                state_version=int(state_version),
                payload=dict(payload or {}),
                body_id=body_id,
                previous_event_hash=previous.content_hash() if previous else None,
                state_hash=state_hash,
            )
            event.signing_bytes()
            self._sign(event)
            if not self._verify_signature(event):
                raise ContinuityVerificationError("event signature verification failed")
            if previous and event.previous_event_hash != previous.content_hash():
                raise ContinuityVerificationError("event chain construction failed")

            self._events.append(event)
            try:
                self._append_disk(event)
                self._write_high_water(event)
            except Exception as exc:
                self._events.pop()
                self._write_failed = True
                self._write_failure_reason = (
                    f"{type(exc).__name__}: {exc}"
                )
                raise
            return event

    def events(self) -> List[ContinuityEvent]:
        with self._lock:
            return list(self._events)

    def latest(self) -> Optional[ContinuityEvent]:
        with self._lock:
            return self._events[-1] if self._events else None

    def verify(self) -> bool:
        with self._lock:
            previous = None
            expected_sequence = 1
            for event in self._events:
                if event.schema != self.VERSION:
                    raise ContinuityVerificationError("invalid event schema")
                if event.event_sequence != expected_sequence:
                    raise ContinuityVerificationError("event sequence mismatch")
                expected_previous = previous.content_hash() if previous else None
                if event.previous_event_hash != expected_previous:
                    raise ContinuityVerificationError("event hash chain mismatch")
                if not event.payload_hash:
                    raise ContinuityVerificationError("missing payload hash")
                expected_payload_hash = hashlib.sha256(
                    json.dumps(
                        event.payload, sort_keys=True,
                        separators=(",", ":"), ensure_ascii=False
                    ).encode("utf-8")
                ).hexdigest()
                if event.payload_hash != expected_payload_hash:
                    raise ContinuityVerificationError("payload hash mismatch")
                if not self._verify_signature(event):
                    raise ContinuityVerificationError("event signature mismatch")
                previous = event
                expected_sequence += 1
            return True

    def tamper_check(self) -> bool:
        try:
            self.verify()
            self._verify_high_water()
            return True
        except ContinuityVerificationError:
            return False

    def export(self) -> List[Dict[str, Any]]:
        return [e.as_dict() for e in self.events()]

