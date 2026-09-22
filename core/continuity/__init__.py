"""SCA-1: Symbiont Continuity Architecture.

Standalone continuity layer. It does not modify Symbiont Core state.
"""

from .identity import ContinuityIdentity
from .state import ContinuityState
from .events import ContinuityEvent
from .ledger import ContinuityLedger, ContinuityVerificationError
from .body import BodyIdentity, BodyStatus
from .handoff import BodyHandoff, BodyHandoffError, BodyHandoffManager
from .verifier import ContinuityVerifier
from .recovery import ContinuityRecovery

__all__ = [
    "ContinuityIdentity",
    "ContinuityState",
    "ContinuityEvent",
    "ContinuityLedger",
    "ContinuityVerificationError",
    "BodyIdentity",
    "BodyStatus",
    "BodyHandoff",
    "BodyHandoffError",
    "BodyHandoffManager",
    "ContinuityVerifier",
    "ContinuityRecovery",
]
