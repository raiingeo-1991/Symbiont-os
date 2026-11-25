import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from symbiont_core import Symbiont
from core.continuity.body import BodyIdentity


class TestSCA1BodyRegistryRestart(unittest.TestCase):


    def test_shadow_initialization_failure_does_not_abort_core(self):
        old_env = os.environ.get("SYMBIONT_SCA1_SHADOW")
        os.environ["SYMBIONT_SCA1_SHADOW"] = "1"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with patch(
                    "symbiont_core.ContinuityShadow",
                    side_effect=RuntimeError("simulated replay failure"),
                ):
                    sym = Symbiont(Path(tmp))
                try:
                    self.assertIsNone(sym.continuity_shadow)
                    self.assertIn(
                        "simulated replay failure",
                        sym.continuity_shadow_error,
                    )
                    self.assertIsNotNone(sym.memory)
                finally:
                    sym.close()
        finally:
            if old_env is None:
                os.environ.pop("SYMBIONT_SCA1_SHADOW", None)
            else:
                os.environ["SYMBIONT_SCA1_SHADOW"] = old_env

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
                    self.assertIsNotNone(shadow)
                    self.assertEqual(shadow.identity.algorithm, "Ed25519")
                    self.assertEqual(
                        shadow.identity.symbiont_id,
                        sym.scp_identity.identity()["node_id"],
                    )

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

                    manager = shadow.body_manager

                    manager.register(body_a)
                    manager.register(body_b)
                    manager.attach(body_a.body_id)
                    manager.handoff(
                        body_a.body_id,
                        body_b.body_id,
                    )

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

                # Simulate loss of the derived state file: the latest
                # BODY_* Ledger snapshot must be sufficient for recovery.
                (root / "continuity" / "state.json").unlink()

                # T1
                sym = Symbiont(root)

                try:
                    shadow = sym.continuity_shadow

                    manager = shadow.body_manager

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
