import os
import tempfile
import unittest
from pathlib import Path

from symbiont_core import Symbiont
from core.continuity.body import BodyIdentity, BodyStatus
from core.continuity.handoff import BodyHandoffManager
from core.continuity.ledger import ContinuityLedger


class TestSCA1CoreHandoff(unittest.TestCase):

    def test_core_shadow_and_body_handoff(self):
        old_env = os.environ.get("SYMBIONT_SCA1_SHADOW")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            os.environ["SYMBIONT_SCA1_SHADOW"] = "1"

            sym = Symbiont(root)

            try:
                # Core activity
                sym.memory.remember(
                    "SCA-1 integration test memory",
                    source="test"
                )

                sym.economy.credit(100, "SCA-1 integration test")

                sym.quests.create(
                    "SCA-1 Integration Quest",
                    "Verify Core + Shadow + Body Handoff",
                    10,
                    "sca1-test",
                )

                status = sym.status()

                # Shadow must be active and independent
                self.assertTrue(status["continuity"]["enabled"])
                self.assertEqual(status["continuity"]["mode"], "shadow")
                self.assertTrue(status["continuity"]["ledger_valid"])
                self.assertFalse(status["continuity"]["core_mutation"])

                self.assertGreaterEqual(
                    status["continuity"]["memory_version"], 1
                )
                self.assertGreaterEqual(
                    status["continuity"]["economy_version"], 1
                )
                self.assertGreaterEqual(
                    status["continuity"]["quest_version"], 1
                )

                # Use the same SCA-1 continuity ledger for Body lifecycle
                ledger_path = root / "continuity" / "ledger.jsonl"
                ledger = ContinuityLedger(ledger_path)

                manager = BodyHandoffManager(ledger)

                body_a = BodyIdentity.create(
                    body_type="smartphone",
                    bridge_version="Android-Bridge-1",
                    capabilities={"screen": True},
                    body_id="CORE-BODY-A",
                )

                body_b = BodyIdentity.create(
                    body_type="smart-glasses",
                    bridge_version="Android-Bridge-1",
                    capabilities={"camera": True},
                    body_id="CORE-BODY-B",
                )

                manager.register(body_a)
                manager.register(body_b)

                manager.attach("CORE-BODY-A", activate=True)

                self.assertTrue(manager.authorize("CORE-BODY-A"))

                manager.handoff(
                    "CORE-BODY-A",
                    "CORE-BODY-B"
                )

                self.assertEqual(
                    body_a.status,
                    BodyStatus.DETACHED
                )
                self.assertEqual(
                    body_b.status,
                    BodyStatus.ACTIVE
                )

                self.assertFalse(
                    manager.authorize("CORE-BODY-A")
                )
                self.assertTrue(
                    manager.authorize("CORE-BODY-B")
                )

                # SCA-1 ledger must remain valid after Core + Body operations
                self.assertTrue(ledger.verify())

                final_status = sym.status()

                self.assertTrue(
                    final_status["continuity"]["ledger_valid"]
                )
                self.assertFalse(
                    final_status["continuity"]["core_mutation"]
                )

                print("CORE ACTIVITY: PASSED")
                print("SCA-1 SHADOW: PASSED")
                print("BODY HANDOFF A -> B: PASSED")
                print("ACTIVE BODY AUTHORIZATION: PASSED")
                print("CORE MUTATION: NONE")
                print("FINAL LEDGER: VALID")
                print("SCA-1 CORE + SHADOW + HANDOFF: PASSED")

            finally:
                close = getattr(sym, "close", None)
                if callable(close):
                    close()

        if old_env is None:
            os.environ.pop("SYMBIONT_SCA1_SHADOW", None)
        else:
            os.environ["SYMBIONT_SCA1_SHADOW"] = old_env


if __name__ == "__main__":
    unittest.main()

