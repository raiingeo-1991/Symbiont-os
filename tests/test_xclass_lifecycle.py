import tempfile
import unittest
from pathlib import Path

import symbiont_core
from core.body import XLink
from experiments.x_class.x_class_node import XClassNode


class XClassLifecycleTests(unittest.TestCase):

    def test_xclass_disconnect_does_not_destroy_core(self):
        root = Path(tempfile.mkdtemp(prefix="xclass-lifecycle-"))
        core = symbiont_core.Symbiont(root=root)

        xlink = XLink(core)
        node = XClassNode(xlink)

        self.assertTrue(node.connect("x-class-lifecycle-001"))

        self.assertTrue(
            node.emit(
                "xclass.lifecycle.started",
                {"test": True},
            )
        )

        self.assertTrue(node.disconnect())

        self.assertFalse(xlink.connected)
        self.assertIsNone(node.node_id)

        # Core must remain alive after X-Class disconnect.
        self.assertIsNotNone(core.identity)
        self.assertIsNotNone(core.memory)
        self.assertIsNotNone(core.state)
        self.assertIsNotNone(core.journal)

    def test_disconnected_xclass_cannot_reach_core(self):
        root = Path(tempfile.mkdtemp(prefix="xclass-isolation-"))
        core = symbiont_core.Symbiont(root=root)

        xlink = XLink(core)
        node = XClassNode(xlink)

        self.assertTrue(node.connect("x-class-isolation-001"))
        self.assertTrue(node.disconnect())

        self.assertFalse(
            node.emit(
                "xclass.after_disconnect",
                {"must_not_pass": True},
            )
        )

    def test_xclass_can_reconnect_without_recreating_core(self):
        root = Path(tempfile.mkdtemp(prefix="xclass-reconnect-"))
        core = symbiont_core.Symbiont(root=root)

        original_identity = core.identity
        original_memory = core.memory

        xlink = XLink(core)
        node = XClassNode(xlink)

        self.assertTrue(node.connect("x-class-reconnect-001"))
        self.assertTrue(node.disconnect())
        self.assertTrue(node.connect("x-class-reconnect-002"))

        self.assertIs(core.identity, original_identity)
        self.assertIs(core.memory, original_memory)

        self.assertTrue(xlink.connected)
        self.assertEqual(
            xlink.node_id,
            "x-class-reconnect-002",
        )


if __name__ == "__main__":
    unittest.main()
