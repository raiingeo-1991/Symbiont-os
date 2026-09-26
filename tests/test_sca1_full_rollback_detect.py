import tempfile
import unittest
from pathlib import Path

from core.continuity.state import ContinuityState
from core.continuity.ledger import (
    ContinuityLedger,
    ContinuityVerificationError,
)
from core.continuity.recovery import ContinuityRecovery
from core.continuity.shadow import ContinuityShadow


class FakeIdentity:
    def id(self):
        return "TEST-SYMBIONT"

    def public_key(self):
        return "TEST-PUBLIC-KEY"


class TestSCA1FullRollback(unittest.TestCase):

    def test_full_rollback_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            path = root / "continuity" / "ledger.jsonl"

            ledger = ContinuityLedger(path)

            recovery = ContinuityRecovery(
                root / "continuity" / "state.json",
                ledger,
            )

            states = []
            previous = ContinuityState()

            for version in range(1, 4):
                state = previous.next(memory_version=version)
                states.append(state)

                ledger.append(
                    "MEMORY_CREATED",
                    state.state_version,
                    {
                        "version": version,
                        "state_snapshot": state.as_dict(),
                    },
                    state_hash=state.content_hash(),
                )

                recovery.save(state)
                previous = state

            latest_before = ledger.latest().state_version

            # Simulate malicious rollback of BOTH files
            rollback_state = states[1]

            lines = path.read_text(
                encoding="utf-8"
            ).splitlines()

            path.write_text(
                "\n".join(lines[:2]) + "\n",
                encoding="utf-8",
            )

            recovery.save(rollback_state)

            print("latest before rollback:", latest_before)

            with self.assertRaises(ContinuityVerificationError):
                ContinuityShadow(root, FakeIdentity())

            print("full rollback: DETECTED")


if __name__ == "__main__":
    unittest.main()
