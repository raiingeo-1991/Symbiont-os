"""SCA-1 continuity verification."""

from typing import Optional

from .ledger import ContinuityLedger, ContinuityVerificationError
from .state import ContinuityState


class ContinuityVerifier:
    VERSION = "SCA-1"

    def __init__(self, ledger: ContinuityLedger):
        self.ledger = ledger

    def verify_ledger(self) -> bool:
        return self.ledger.verify()

    def verify_state(self, state: ContinuityState, previous: Optional[ContinuityState] = None) -> bool:
        if state.schema != self.VERSION:
            return False
        return state.verify_link(previous)

    def verify_active_body(self, state: ContinuityState, body_id: Optional[str]) -> bool:
        return state.active_body == body_id if body_id is not None else state.active_body is None

    def verify_all(self, state: ContinuityState, previous: Optional[ContinuityState] = None) -> bool:
        if not self.verify_state(state, previous):
            return False
        return self.verify_ledger()
