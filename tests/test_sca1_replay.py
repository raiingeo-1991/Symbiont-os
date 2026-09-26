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


class TestSCA1Replay(unittest.TestCase):

    def test_replayed_core_event_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            shadow = ContinuityShadow(root, FakeIdentity())

            event = {
                "event_id": "EVENT-001",
                "event_type": "memory.created",
                "payload": {
                    "memory_id": "MEM-001",
                    "text": "test",
                },
            }

            shadow.on_core_event(event)

            events_before = len(shadow.ledger.events())
            state_before = shadow.state.content_hash()

            # Повторно отправляем тот же Core event.
            shadow.on_core_event(event)

            events_after = len(shadow.ledger.events())
            state_after = shadow.state.content_hash()

            print("events before:", events_before)
            print("events after:", events_after)
            print("state unchanged:", state_before == state_after)

            self.assertEqual(events_before, events_after)
            self.assertEqual(state_before, state_after)


if __name__ == "__main__":
    unittest.main()
