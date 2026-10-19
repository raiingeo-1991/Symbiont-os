import tempfile
import unittest
from pathlib import Path

from symbiont_core import EventJournal
from core.continuity.shadow import ContinuityShadow


class FakeIdentity:
    def id(self):
        return "SCA1-LOSS-TEST"

    def public_key(self):
        return "TEST-PUBLIC-KEY"


class TestSCA1MissedEventRecovery(unittest.TestCase):

    def test_restart_replays_core_event_missed_by_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = EventJournal(root / "events.log")
            shadow = ContinuityShadow(root, FakeIdentity())

            original_append = shadow.ledger.append

            def fail_append(*args, **kwargs):
                raise OSError("simulated Shadow storage failure")

            shadow.ledger.append = fail_append
            journal.add_listener(shadow.on_core_event)

            event = journal.append(
                "memory.created",
                {"memory_id": "LOSS-001", "text": "isolated test"},
            )

            self.assertTrue(journal.verify()[0])
            self.assertEqual(len(shadow.ledger.events()), 0)

            # Simulate a new process using the persisted Core journal.
            restarted_journal = EventJournal(root / "events.log")
            restarted_shadow = ContinuityShadow(root, FakeIdentity())

            # Expected recovery contract: atomically replay existing
            # Core events and subscribe to future events.
            restarted_journal.add_listener(
                restarted_shadow.on_core_event,
                replay_existing=True,
            )

            recovered_ids = {
                item.payload.get("core_event_id")
                for item in restarted_shadow.ledger.events()
            }

            self.assertIn(event["event_id"], recovered_ids)
            self.assertEqual(restarted_shadow.state.memory_version, 1)
            self.assertTrue(restarted_journal.verify()[0])

            # Replaying the same event must not create a duplicate.
            count = len(restarted_shadow.ledger.events())
            restarted_journal.add_listener(
                restarted_shadow.on_core_event,
                replay_existing=True,
            )
            self.assertEqual(len(restarted_shadow.ledger.events()), count)

    def test_restart_recovers_middle_event_in_core_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = EventJournal(root / "events.log")
            shadow = ContinuityShadow(root, FakeIdentity())
            journal.add_listener(shadow.on_core_event)

            first = journal.append("memory.created", {"id": "FIRST"})

            original_append = shadow.ledger.append
            failed = {"done": False}

            def fail_once(*args, **kwargs):
                if not failed["done"]:
                    failed["done"] = True
                    raise OSError("simulated middle-event failure")
                return original_append(*args, **kwargs)

            shadow.ledger.append = fail_once
            middle = journal.append("memory.created", {"id": "MIDDLE"})

            shadow.ledger.append = original_append
            last = journal.append("memory.created", {"id": "LAST"})

            restarted_journal = EventJournal(root / "events.log")
            restarted_shadow = ContinuityShadow(root, FakeIdentity())
            restarted_journal.add_listener(
                restarted_shadow.on_core_event,
                replay_existing=True,
            )

            core_ids = [
                event["event_id"]
                for event in restarted_journal.all_events()
            ]
            shadow_ids = [
                event.payload.get("core_event_id")
                for event in restarted_shadow.ledger.events()
                if event.payload.get("core_event_id")
            ]

            self.assertEqual(
                shadow_ids,
                [first["event_id"], middle["event_id"], last["event_id"]],
            )
            self.assertEqual(restarted_shadow.state.memory_version, 3)


if __name__ == "__main__":
    unittest.main()
