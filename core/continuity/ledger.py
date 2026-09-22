"""SCA-1 append-only continuity ledger."""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import json
import os
import tempfile
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
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(ContinuityEvent.from_dict(json.loads(line)))
        self._events = events
        if self._events:
            self.verify()

    def _append_disk(self, event: ContinuityEvent) -> None:
        if not self.path:
            return
        line = json.dumps(event.as_dict(), sort_keys=True, ensure_ascii=False) + "\n"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

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
            # Materialize deterministic payload hash before signing or persisting.
            event.signing_bytes()
            self._sign(event)
            if not self._verify_signature(event):
                raise ContinuityVerificationError("event signature verification failed")
            if previous and event.previous_event_hash != previous.content_hash():
                raise ContinuityVerificationError("event chain construction failed")
            self._events.append(event)
            try:
                self._append_disk(event)
            except Exception:
                self._events.pop()
                raise
            return event

    def events(self) -> List[ContinuityEvent]:
        with self._lock:
            return list(self._events)

    def latest(self) -> Optional[ContinuityEvent]:
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
                expected_payload_hash = __import__("hashlib").sha256(
                    __import__("json").dumps(
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
            return self.verify()
        except ContinuityVerificationError:
            return False

    def export(self) -> List[Dict[str, Any]]:
        return [e.as_dict() for e in self.events()]
