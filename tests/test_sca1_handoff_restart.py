import tempfile
import unittest
from pathlib import Path

from core.continuity.body import BodyIdentity
from core.continuity.handoff import BodyHandoffManager
from core.continuity.ledger import ContinuityLedger


class TestSCA1HandoffRestart(unittest.TestCase):

    def test_handoff_survives_restart_in_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"

            # ---- PROCESS 1 ----
            ledger1 = ContinuityLedger(path)
            manager1 = BodyHandoffManager(ledger1)

            body_a = BodyIdentity.create(
                body_type="smartphone",
                bridge_version="Android-Bridge-1",
                capabilities={"screen": True},
                body_id="RESTART-BODY-A",
            )

            body_b = BodyIdentity.create(
                body_type="smart-glasses",
                bridge_version="Android-Bridge-1",
                capabilities={"camera": True},
                body_id="RESTART-BODY-B",
            )

            manager1.register(body_a)
            manager1.register(body_b)
            manager1.attach("RESTART-BODY-A", activate=True)
            manager1.handoff(
                "RESTART-BODY-A",
                "RESTART-BODY-B",
            )

            self.assertTrue(manager1.authorize("RESTART-BODY-B"))
            self.assertTrue(ledger1.verify())

            events_before = ledger1.events()

            handoffs_before = [
                e for e in events_before
                if e.event_type == "BODY_HANDOFF"
            ]

            self.assertEqual(len(handoffs_before), 1)

            # ---- PROCESS 2 / RESTART ----
            ledger2 = ContinuityLedger(path)

            self.assertTrue(ledger2.verify())

            events_after = ledger2.events()

            self.assertEqual(
                len(events_after),
                len(events_before),
            )

            handoffs_after = [
                e for e in events_after
                if e.event_type == "BODY_HANDOFF"
            ]

            self.assertEqual(len(handoffs_after), 1)

            last_handoff = handoffs_after[-1]

            self.assertEqual(
                last_handoff.payload["source_body_id"],
                "RESTART-BODY-A",
            )

            self.assertEqual(
                last_handoff.payload["target_body_id"],
                "RESTART-BODY-B",
            )

            print("HANDOFF PERSISTED: PASSED")
            print("TARGET BODY B RECORDED: PASSED")
            print("LEDGER RELOADED: PASSED")
            print("LEDGER VERIFICATION AFTER RESTART: PASSED")
            print("SCA-1 HANDOFF RESTART PERSISTENCE: PASSED")


if __name__ == "__main__":
    unittest.main()

