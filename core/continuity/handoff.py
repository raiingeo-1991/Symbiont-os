"""SCA-1 body handoff state machine."""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .body import BodyIdentity, BodyStatus
from .ledger import ContinuityLedger
from .state import ContinuityState


class BodyHandoffError(Exception):
    pass


@dataclass(frozen=True)
class BodyHandoff:
    source_body_id: Optional[str]
    target_body_id: str
    state_version: int
    source_state_hash: str
    event_sequence: int

    def as_dict(self):
        return {
            "source_body_id": self.source_body_id,
            "target_body_id": self.target_body_id,
            "state_version": self.state_version,
            "source_state_hash": self.source_state_hash,
            "event_sequence": self.event_sequence,
        }


class BodyHandoffManager:
    """Coordinates body lifecycle without touching Core business data."""

    def __init__(self, ledger: ContinuityLedger, state: Optional[ContinuityState] = None):
        self.ledger = ledger
        self.state = state or ContinuityState()
        self.bodies: Dict[str, BodyIdentity] = {}

    def register(self, body: BodyIdentity) -> BodyIdentity:
        if body.body_id in self.bodies:
            raise BodyHandoffError("body already registered")
        self.bodies[body.body_id] = body
        self.ledger.append(
            "BODY_REGISTERED",
            self.state.state_version,
            {"body": body.as_dict()},
            body_id=body.body_id,
            state_hash=self.state.content_hash(),
        )
        return body

    def attach(self, body_id: str, activate: bool = True) -> BodyHandoff:
        body = self._body(body_id)
        if body.status == BodyStatus.REVOKED:
            raise BodyHandoffError("revoked body cannot be attached")
        current = self.state.active_body
        if current and current != body_id and activate:
            self.detach(current)
        body.touch()
        body.status = BodyStatus.ACTIVE if activate else BodyStatus.ATTACHED
        next_state = self.state.next(active_body=body_id if activate else self.state.active_body)
        event = self.ledger.append(
            "BODY_ATTACHED",
            next_state.state_version,
            {"source_body_id": current, "target_body_id": body_id},
            body_id=body_id,
            state_hash=next_state.content_hash(),
        )
        self.state = next_state
        return BodyHandoff(current, body_id, self.state.state_version,
                           self.state.content_hash(), event.event_sequence)

    def detach(self, body_id: str) -> None:
        body = self._body(body_id)
        body.touch()
        was_active = self.state.active_body == body_id
        body.status = BodyStatus.DETACHED
        next_state = self.state.next(active_body=None if was_active else self.state.active_body)
        self.ledger.append(
            "BODY_DETACHED",
            next_state.state_version,
            {"body_id": body_id},
            body_id=body_id,
            state_hash=next_state.content_hash(),
        )
        self.state = next_state

    def handoff(self, source_body_id: str, target_body_id: str) -> BodyHandoff:
        if self.state.active_body != source_body_id:
            raise BodyHandoffError("source body is not active")
        source = self._body(source_body_id)
        target = self._body(target_body_id)
        if target.status == BodyStatus.REVOKED:
            raise BodyHandoffError("target body is revoked")
        source.touch()
        target.touch()

        # The target must be registered before it can become active.
        next_state = self.state.next(active_body=target_body_id)
        event = self.ledger.append(
            "BODY_HANDOFF",
            next_state.state_version,
            {
                "source_body_id": source_body_id,
                "target_body_id": target_body_id,
                "source_state_hash": self.state.content_hash(),
            },
            body_id=target_body_id,
            state_hash=next_state.content_hash(),
        )
        source.status = BodyStatus.DETACHED
        target.status = BodyStatus.ACTIVE
        self.state = next_state
        return BodyHandoff(
            source_body_id,
            target_body_id,
            self.state.state_version,
            self.state.content_hash(),
            event.event_sequence,
        )

    def revoke(self, body_id: str) -> None:
        body = self._body(body_id)
        if self.state.active_body == body_id:
            raise BodyHandoffError("active body must be handed off before revocation")
        body.status = BodyStatus.REVOKED
        body.touch()
        self.ledger.append(
            "BODY_REVOKED",
            self.state.state_version,
            {"body_id": body_id},
            body_id=body_id,
            state_hash=self.state.content_hash(),
        )

    def authorize(self, body_id: str) -> bool:
        body = self._body(body_id)
        return (
            body.status == BodyStatus.ACTIVE
            and self.state.active_body == body_id
            and body.status != BodyStatus.REVOKED
        )

    def _body(self, body_id: str) -> BodyIdentity:
        try:
            return self.bodies[str(body_id)]
        except KeyError:
            raise BodyHandoffError("unknown body")
