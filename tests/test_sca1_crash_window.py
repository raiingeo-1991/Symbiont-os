import tempfile
import unittest
from pathlib import Path

from core.continuity.state import ContinuityState
from core.continuity.ledger import ContinuityLedger
from core.continuity.recovery import ContinuityRecovery
from core.continuity.shadow import ContinuityShadow
from core.continuity.ledger import ContinuityVerificationError


class FakeIdentity:
    def id(self):
        return "TEST-SYMBIONT"

    def public_key(self):
        return "TEST-PUBLIC-KEY"


class TestSCA1CrashWindow(unittest.TestCase):

    def test_restart_detects_ledger_ahead_of_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            ledger = ContinuityLedger(
                root / "continuity" / "ledger.jsonl"
            )

            recovery = ContinuityRecovery(
                root / "continuity" / "state.json",
                ledger,
            )

            # State version 1 — сохранён нормально
            state1 = ContinuityState().next(memory_version=1)

            ledger.append(
                "MEMORY_CREATED",
                state1.state_version,
                {"test": "state-1"},
                state_hash=state1.content_hash(),
            )

            recovery.save(state1)

            # Следующее состояние попало в Ledger...
            state2 = state1.next(memory_version=2)

            ledger.append(
                "MEMORY_CREATED",
                state2.state_version,
                {"test": "state-2"},
                state_hash=state2.content_hash(),
            )

            # ...но recovery.save(state2) НЕ вызываем.
            # Это имитация crash между Ledger и state.json.

            # После restart расхождение должно быть обнаружено.
            with self.assertRaises(ContinuityVerificationError):
                ContinuityShadow(root, FakeIdentity())


if __name__ == "__main__":
    unittest.main()
