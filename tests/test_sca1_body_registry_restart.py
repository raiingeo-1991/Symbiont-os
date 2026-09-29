import os
import tempfile
import unittest
from pathlib import Path

from symbiont_core import Symbiont
from core.continuity.body import BodyIdentity
from core.continuity.handoff import BodyHandoffManager


class TestSCA1BodyRegistryRestart(unittest.TestCase):

    def test_body_registry_and_authorization_survive_restart(self):
        old_env = os.environ.get("SYMBIONT_SCA1_SHADOW")
        os.environ["SYMBIONT_SCA1_SHADOW"] = "1"

        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)

                # T0
                sym = Symbiont(root)

                try:
                    shadow = sym.continuity_shadow

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

                    manager = BodyHandoffManager(
                        shadow.ledger,
                        state=shadow.state,
                    )

                    manager.register(body_a)
                    manager.register(body_b)
                    manager.attach(body_a.body_id)
                    manager.handoff(
                        body_a.body_id,
                        body_b.body_id,
                    )

                    shadow.recovery.save(manager.state)
                    shadow.state = manager.state

                    self.assertEqual(
                        manager.state.active_body,
                        body_b.body_id,
                    )
                    self.assertTrue(
                        manager.authorize(body_b.body_id)
                    )

                finally:
                    # T0 process ends normally here.
                    sym.close()

                # T1
                sym = Symbiont(root)

                try:
                    shadow = sym.continuity_shadow

                    manager = BodyHandoffManager(
                        shadow.ledger,
                        state=shadow.state,
                    )

                    self.assertEqual(
                        set(manager.bodies),
                        {
                            body_a.body_id,
                            body_b.body_id,
                        },
                    )

                    self.assertEqual(
                        manager.state.active_body,
                        body_b.body_id,
                    )

                    self.assertTrue(
                        manager.authorize(body_b.body_id)
                    )

                    self.assertTrue(
                        shadow.ledger.verify()
                    )

                finally:
                    sym.close()

        finally:
            if old_env is None:
                os.environ.pop(
                    "SYMBIONT_SCA1_SHADOW",
                    None,
                )
            else:
                os.environ[
                    "SYMBIONT_SCA1_SHADOW"
                ] = old_env


if __name__ == "__main__":
    unittest.main()
