import unittest

from core.body import XLink
from experiments.x_class.x_class_node import XClassNode


class FakeCore:
    def __init__(self):
        self.events = []

    def remember(self, text, kind="general", importance=5, project=None):
        self.events.append({
            "text": text,
            "kind": kind,
            "importance": importance,
            "project": project,
        })


class XClassNodeTests(unittest.TestCase):

    def test_node_starts_disconnected(self):
        node = XClassNode(XLink())

        self.assertIsNone(node.node_id)
        self.assertFalse(node.xlink.connected)

    def test_node_connects_through_xlink(self):
        node = XClassNode(XLink())

        self.assertTrue(
            node.connect("x-class-001")
        )

        self.assertEqual(
            node.node_id,
            "x-class-001",
        )

        self.assertTrue(
            node.xlink.connected
        )

    def test_node_emits_through_xlink(self):
        core = FakeCore()
        node = XClassNode(XLink(core))

        node.connect("x-class-001")

        self.assertTrue(
            node.emit(
                "xclass.started",
                {"version": "1"},
            )
        )

        self.assertEqual(
            len(core.events),
            1,
        )

        self.assertEqual(
            core.events[0]["kind"],
            "external",
        )

    def test_node_cannot_emit_before_connect(self):
        core = FakeCore()
        node = XClassNode(XLink(core))

        self.assertFalse(
            node.emit(
                "xclass.started",
            )
        )

        self.assertEqual(
            core.events,
            [],
        )

    def test_disconnect_removes_node_connection(self):
        node = XClassNode(XLink())

        node.connect("x-class-001")

        self.assertTrue(
            node.disconnect()
        )

        self.assertIsNone(node.node_id)
        self.assertFalse(node.xlink.connected)

    def test_node_has_no_core_state(self):
        node = XClassNode(XLink())

        forbidden = {
            "core",
            "memory",
            "memory_v2",
            "identity",
            "state",
            "journal",
            "economy",
            "permissions",
            "mind",
            "context",
        }

        for name in forbidden:
            self.assertFalse(
                hasattr(node, name),
                f"X-Class exposes forbidden field: {name}",
            )

    def test_status_is_external_node_status(self):
        node = XClassNode(XLink())

        node.connect("x-class-001")

        status = node.status()

        self.assertEqual(
            status["class"],
            "X-Class",
        )

        self.assertEqual(
            status["version"],
            "XCLASS/1",
        )

        self.assertEqual(
            status["node_id"],
            "x-class-001",
        )


if __name__ == "__main__":
    unittest.main()
