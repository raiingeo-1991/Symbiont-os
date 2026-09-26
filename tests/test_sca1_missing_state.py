import tempfile
import unittest
from pathlib import Path

from core.continuity.state import ContinuityState
from core.continuity.ledger import ContinuityLedger
from core.continuity.recovery import ContinuityRecovery
from core.continuity.shadow import ContinuityShadow


class FakeIdentity:
    def id(self):
        return "TEST-SYMBIONT"

    def public_key(self):
        return "TEST-PUBLIC-KEY"


class TestSCA1MissingState(unittest.TestCase):

    def test_missing_state_is_recovered_from_ledger_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            ledger = ContinuityLedger(
                root / "continuity" / "ledger.jsonl"
            )

            recovery = ContinuityRecovery(
                root / "continuity" / "state.json",
                ledger,
            )

            state = ContinuityState().next(memory_version=1)

            ledger.append(
                "MEMORY_CREATED",
                state.state_version,
                {
                    "test": "missing-state",
                    "state_snapshot": state.as_dict(),
                },
                state_hash=state.content_hash(),
            )

            state_file = root / "continuity" / "state.json"
            self.assertFalse(state_file.exists())

            shadow = ContinuityShadow(root, FakeIdentity())

            print("recovered state version:", shadow.state.state_version)
            print("ledger state version:", shadow.ledger.latest().state_version)
            print("state file restored:", state_file.exists())

            self.assertEqual(
                shadow.state.state_version,
                state.state_version,
            )
            self.assertEqual(
                shadow.state.memory_version,
                state.memory_version,
            )
            self.assertEqual(
                shadow.state.content_hash(),
                state.content_hash(),
            )
            self.assertTrue(state_file.exists())


if __name__ == "__main__":
    unittest.main()
