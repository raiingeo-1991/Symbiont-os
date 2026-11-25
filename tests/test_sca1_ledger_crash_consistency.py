import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.continuity.ledger import (
    ContinuityLedger,
    ContinuityVerificationError,
)


class TestSCA1LedgerCrashConsistency(unittest.TestCase):
    def _new_ledger_with_event(self, root):
        path = root / "continuity" / "ledger.jsonl"
        ledger = ContinuityLedger(path)
        ledger.append("TEST_EVENT", 1, {"value": 1})
        return path, ledger

    def test_missing_ledger_with_anchor_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = self._new_ledger_with_event(Path(tmp))
            path.unlink()
            with self.assertRaisesRegex(
                ContinuityVerificationError, "ledger missing"
            ):
                ContinuityLedger(path)

    def test_empty_ledger_with_anchor_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = self._new_ledger_with_event(Path(tmp))
            path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(
                ContinuityVerificationError, "ledger empty"
            ):
                ContinuityLedger(path)

    def test_high_water_failure_disables_further_writes_and_restart_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "continuity" / "ledger.jsonl"
            ledger = ContinuityLedger(path)
            ledger.append("INITIAL_EVENT", 1, {"value": 0})

            with patch.object(
                ledger, "_write_high_water", side_effect=OSError("anchor I/O")
            ):
                with self.assertRaisesRegex(OSError, "anchor I/O"):
                    ledger.append("TEST_EVENT", 2, {"value": 1})

            with self.assertRaisesRegex(
                ContinuityVerificationError, "writes disabled"
            ):
                ledger.append("SECOND_EVENT", 2, {"value": 2})

            with self.assertRaisesRegex(
                ContinuityVerificationError, "ahead of high-water"
            ):
                ContinuityLedger(path)

    def test_partial_ledger_write_disables_instance_and_restart_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "continuity" / "ledger.jsonl"
            ledger = ContinuityLedger(path)

            def partial_then_fail(event):
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write('{"partial":')
                    fh.flush()
                raise OSError("simulated partial write")

            with patch.object(ledger, "_append_disk", side_effect=partial_then_fail):
                with self.assertRaisesRegex(OSError, "partial write"):
                    ledger.append("TEST_EVENT", 1, {"value": 1})

            with self.assertRaisesRegex(
                ContinuityVerificationError, "writes disabled"
            ):
                ledger.append("SECOND_EVENT", 2, {"value": 2})

            with self.assertRaisesRegex(
                ContinuityVerificationError, "malformed or unreadable"
            ):
                ContinuityLedger(path)


if __name__ == "__main__":
    unittest.main()
