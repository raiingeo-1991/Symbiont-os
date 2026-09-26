import tempfile
import unittest
from pathlib import Path

from core.continuity.body import BodyIdentity, BodyStatus
from core.continuity.handoff import BodyHandoffManager
from core.continuity.ledger import ContinuityLedger


class TestContinuityHandoff(unittest.TestCase):

    def test_body_handoff_a_to_b_and_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"

            ledger = ContinuityLedger(path)

            manager = BodyHandoffManager(ledger)

            body_a = BodyIdentity.create(
                body_type="smartphone",
                bridge_version="Android-Bridge-1",
                capabilities={"screen": True, "microphone": True},
                body_id="BODY-A",
            )

            body_b = BodyIdentity.create(
                body_type="smart-glasses",
                bridge_version="Android-Bridge-1",
                capabilities={"camera": True, "microphone": True},
                body_id="BODY-B",
            )

            # Register both bodies
            manager.register(body_a)
            manager.register(body_b)

            self.assertEqual(body_a.status, BodyStatus.DETACHED)
            self.assertEqual(body_b.status, BodyStatus.DETACHED)

            # Activate A
            manager.attach("BODY-A", activate=True)

            self.assertTrue(manager.authorize("BODY-A"))
            self.assertFalse(manager.authorize("BODY-B"))
            self.assertEqual(manager.state.active_body, "BODY-A")

            # Handoff A -> B
            handoff_ab = manager.handoff("BODY-A", "BODY-B")

            self.assertEqual(handoff_ab.source_body_id, "BODY-A")
            self.assertEqual(handoff_ab.target_body_id, "BODY-B")

            self.assertEqual(body_a.status, BodyStatus.DETACHED)
            self.assertEqual(body_b.status, BodyStatus.ACTIVE)

            self.assertFalse(manager.authorize("BODY-A"))
            self.assertTrue(manager.authorize("BODY-B"))
            self.assertEqual(manager.state.active_body, "BODY-B")

            # Handoff B -> A
            handoff_ba = manager.handoff("BODY-B", "BODY-A")

            self.assertEqual(handoff_ba.source_body_id, "BODY-B")
            self.assertEqual(handoff_ba.target_body_id, "BODY-A")

            self.assertEqual(body_b.status, BodyStatus.DETACHED)
            self.assertEqual(body_a.status, BodyStatus.ACTIVE)

            self.assertFalse(manager.authorize("BODY-B"))
            self.assertTrue(manager.authorize("BODY-A"))
            self.assertEqual(manager.state.active_body, "BODY-A")

            # Ledger must remain valid
            self.assertTrue(ledger.verify())

            # Handoff events must exist
            events = ledger.events()
            event_types = [event.event_type for event in events]

            self.assertIn("BODY_REGISTERED", event_types)
            self.assertIn("BODY_ATTACHED", event_types)
            self.assertIn("BODY_HANDOFF", event_types)

            print("BODY HANDOFF A -> B: PASSED")
            print("BODY HANDOFF B -> A: PASSED")
            print("ACTIVE BODY AUTHORIZATION: PASSED")
            print("LEDGER VERIFICATION: PASSED")
            print("SCA-1 BODY HANDOFF: PASSED")


if __name__ == "__main__":
    unittest.main()

