import tempfile
import unittest
from pathlib import Path

from core.continuity.state import ContinuityState
from core.continuity.ledger import (
    ContinuityLedger,
    ContinuityVerificationError,
)


class TestSCA1MiddleDeletion(unittest.TestCase):

    def test_middle_event_deletion_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "continuity" / "ledger.jsonl"

            ledger = ContinuityLedger(path)

            states = []
            previous = ContinuityState()

            for version in range(1, 4):
                state = previous.next(memory_version=version)
                states.append(state)

                ledger.append(
                    "MEMORY_CREATED",
                    state.state_version,
                    {"version": version},
                    state_hash=state.content_hash(),
                )

                previous = state

            self.assertEqual(len(ledger.events()), 3)

            # Удаляем событие №2 — середину цепочки.
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text(
                "\n".join([lines[0], lines[2]]) + "\n",
                encoding="utf-8",
            )

            # Новый процесс должен обнаружить разрыв hash-chain.
            with self.assertRaises(ContinuityVerificationError):
                ContinuityLedger(path)

            print("middle event deletion: DETECTED")


if __name__ == "__main__":
    unittest.main()
