import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.continuity.ledger import ContinuityLedger, ContinuityVerificationError
from core.continuity.recovery import ContinuityRecovery
from core.continuity.shadow import ContinuityShadow
from core.continuity.state import ContinuityState
from symbiont_core import EventJournal


class FakeIdentity:
    def id(self):
        return "TEST-SYMBIONT"

    def public_key(self):
        return "TEST-PUBLIC-KEY"


class TestSCA1ShadowHealth(unittest.TestCase):
    def test_stale_state_recovers_from_latest_verified_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = ContinuityLedger(root / "continuity" / "ledger.jsonl")
            recovery = ContinuityRecovery(root / "continuity" / "state.json", ledger)

            first = ContinuityState().next(memory_version=1)
            ledger.append("FIRST", first.state_version,
                          {"state_snapshot": first.as_dict()},
                          state_hash=first.content_hash())
            recovery.save(first)

            second = first.next(memory_version=2)
            ledger.append("SECOND", second.state_version,
                          {"state_snapshot": second.as_dict()},
                          state_hash=second.content_hash())

            recovered = recovery.load_or_recover()
            self.assertEqual(recovered.content_hash(), second.content_hash())
            self.assertEqual(recovery.load().content_hash(), second.content_hash())

    def test_unrecognized_state_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = ContinuityLedger(root / "continuity" / "ledger.jsonl")
            recovery = ContinuityRecovery(root / "continuity" / "state.json", ledger)
            recorded = ContinuityState().next(memory_version=1)
            ledger.append("RECORDED", recorded.state_version,
                          {"state_snapshot": recorded.as_dict()},
                          state_hash=recorded.content_hash())
            recovery.save(ContinuityState().next(memory_version=99))

            with self.assertRaises(ContinuityVerificationError):
                recovery.load_or_recover()

    def test_shadow_stops_after_state_save_failure_and_restart_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shadow = ContinuityShadow(root, FakeIdentity())
            first = {"event_id": "e1", "type": "memory.created",
                     "previous": "0" * 64, "hash": "a" * 64,
                     "payload": {}}
            shadow.on_core_event(first)

            second = {"event_id": "e2", "type": "memory.created",
                      "previous": "a" * 64, "hash": "b" * 64,
                      "payload": {}}
            with patch.object(shadow.recovery, "save", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    shadow.on_core_event(second)

            status = shadow.status()
            self.assertEqual(status["health"], "degraded")
            self.assertEqual(status["error_count"], 1)
            self.assertEqual(status["last_error"]["error_type"], "OSError")

            with self.assertRaises(RuntimeError):
                shadow.on_core_event({
                    "event_id": "e3", "type": "memory.created",
                    "previous": "b" * 64, "hash": "c" * 64, "payload": {}
                })

            restarted = ContinuityShadow(root, FakeIdentity())
            self.assertEqual(restarted.state.memory_version, 2)
            self.assertEqual(restarted.state.state_version, 2)

    def test_event_journal_records_observer_failure_without_failing_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = EventJournal(Path(tmp) / "events.jsonl")

            def broken_observer(_event):
                raise RuntimeError("observer failed")

            journal.add_listener(broken_observer)
            event = journal.append("test.event", {"ok": True})

            self.assertTrue(event["event_id"])
            self.assertEqual(journal._listener_error_count, 1)
            self.assertEqual(
                journal._last_listener_error["message"],
                "observer failed",
            )


if __name__ == "__main__":
    unittest.main()
