import tempfile
import unittest
from pathlib import Path

from core.continuity.state import ContinuityState
from core.continuity.ledger import (
    ContinuityLedger,
    ContinuityVerificationError,
)


class TestSCA1TailTruncation(unittest.TestCase):

    def test_tail_truncation_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "continuity" / "ledger.jsonl"

            ledger = ContinuityLedger(path)

            s1 = ContinuityState().next(memory_version=1)
            ledger.append(
                "MEMORY_CREATED",
                s1.state_version,
                {"n": 1},
                state_hash=s1.content_hash(),
            )

            s2 = s1.next(memory_version=2)
            ledger.append(
                "MEMORY_CREATED",
                s2.state_version,
                {"n": 2},
                state_hash=s2.content_hash(),
            )

            s3 = s2.next(memory_version=3)
            ledger.append(
                "MEMORY_CREATED",
                s3.state_version,
                {"n": 3},
                state_hash=s3.content_hash(),
            )

            before = len(ledger.events())

            lines = path.read_text(
                encoding="utf-8"
            ).splitlines()

            path.write_text(
                "\n".join(lines[:-1]) + "\n",
                encoding="utf-8",
            )

            print("events before:", before)

            with self.assertRaises(ContinuityVerificationError):
                ContinuityLedger(path)

            print("tail truncation: DETECTED")


if __name__ == "__main__":
    unittest.main()
