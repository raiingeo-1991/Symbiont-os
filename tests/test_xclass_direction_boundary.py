import tempfile
import unittest
from pathlib import Path

import symbiont_core
from core.body import XLink
from experiments.x_class.x_class_node import XClassNode


class XClassDirectionBoundaryTests(unittest.TestCase):

    def test_xclass_receives_no_core_reference(self):
        root = Path(tempfile.mkdtemp(prefix="xclass-direction-"))
        core = symbiont_core.Symbiont(root=root)

        xlink = XLink(core)
        node = XClassNode(xlink)

        # X-Class receives only XLink.
        self.assertIs(node.xlink, xlink)

        # The X-Class node itself must not expose Core.
        forbidden = (
            "core",
            "memory",
            "memory_v2",
            "identity",
            "state",
            "journal",
            "mind",
            "context",
            "economy",
            "permissions",
        )

        for name in forbidden:
            self.assertFalse(
                hasattr(node, name),
                f"X-Class directly exposes forbidden field: {name}",
            )

    def test_event_is_the_only_current_xlink_to_core_operation(self):
        root = Path(tempfile.mkdtemp(prefix="xclass-direction-event-"))
        core = symbiont_core.Symbiont(root=root)

        xlink = XLink(core)
        node = XClassNode(xlink)

        self.assertTrue(
            node.connect("x-class-direction-001")
        )

        before = len(core.memory.all_memories())

        self.assertTrue(
            node.emit(
                "xclass.direction.test",
                {"source": "X-Class"},
            )
        )

        after = len(core.memory.all_memories())

        # Current XLink contract records an external event in Core memory.
        self.assertEqual(after, before + 1)

        memories = core.memory.all_memories()
        self.assertTrue(
            any(
                "xclass.direction.test" in getattr(memory, "text", "")
                for memory in memories
            )
        )

    def test_xclass_cannot_use_core_after_xlink_is_detached(self):
        root = Path(tempfile.mkdtemp(prefix="xclass-direction-detach-"))
        core = symbiont_core.Symbiont(root=root)

        xlink = XLink(core)
        node = XClassNode(xlink)

        self.assertTrue(
            node.connect("x-class-direction-002")
        )

        self.assertTrue(
            node.disconnect()
        )

        self.assertFalse(
            node.emit(
                "xclass.detached",
                {"must_not_pass": True},
            )
        )


if __name__ == "__main__":
    unittest.main()
