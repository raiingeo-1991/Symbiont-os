import unittest

from core.body import XLink


class SymbiontX:
    """
    Experimental X-Class node.

    X-Class does not own or receive direct access to Symbiont Core.
    It communicates through XLink only.
    """

    CLASS = "X-Class"

    def __init__(self, xlink):
        self.xlink = xlink
        self.node_id = None

    def connect(self, node_id):
        self.node_id = str(node_id)
        return self.xlink.connect(self.node_id)

    def disconnect(self):
        return self.xlink.disconnect()

    def status(self):
        return {
            "class": self.CLASS,
            "node_id": self.node_id,
            "xlink": self.xlink.status(),
        }

    def emit_event(self, event, data=None):
        return self.xlink.send_event(event, data)


class SymbiontXBoundaryTests(unittest.TestCase):

    def test_xclass_uses_xlink_only(self):
        xlink = XLink()
        node = SymbiontX(xlink)

        self.assertIs(node.xlink, xlink)

        self.assertFalse(hasattr(node, "memory"))
        self.assertFalse(hasattr(node, "memory_v2"))
        self.assertFalse(hasattr(node, "identity"))
        self.assertFalse(hasattr(node, "state"))
        self.assertFalse(hasattr(node, "journal"))

    def test_xclass_can_connect_through_xlink(self):
        xlink = XLink()
        node = SymbiontX(xlink)

        self.assertTrue(node.connect("x-node-001"))

        status = node.status()

        self.assertEqual(status["class"], "X-Class")
        self.assertEqual(status["node_id"], "x-node-001")
        self.assertTrue(status["xlink"]["connected"])

    def test_xclass_can_disconnect_through_xlink(self):
        xlink = XLink()
        node = SymbiontX(xlink)

        node.connect("x-node-001")

        self.assertTrue(node.disconnect())
        self.assertFalse(xlink.connected)

    def test_unconnected_xclass_cannot_send_event(self):
        xlink = XLink()
        node = SymbiontX(xlink)

        self.assertFalse(
            node.emit_event(
                "test.event",
                {"value": 1},
            )
        )


if __name__ == "__main__":
    unittest.main()


class FakeCore:
    """Минимальный Core-контракт, доступный через XLink."""

    def __init__(self):
        self.events = []

    def remember(self, text, kind="general", importance=5, project=None):
        self.events.append({
            "text": text,
            "kind": kind,
            "importance": importance,
            "project": project,
        })


class SymbiontXCoreBoundaryTests(unittest.TestCase):

    def test_xlink_forwards_event_without_exposing_core(self):
        core = FakeCore()
        xlink = XLink(core)
        node = SymbiontX(xlink)

        node.connect("x-node-002")

        self.assertTrue(
            node.emit_event(
                "sensor.update",
                {"temperature": 21},
            )
        )

        self.assertEqual(len(core.events), 1)
        self.assertEqual(
            core.events[0]["kind"],
            "external",
        )
        self.assertIn(
            "sensor.update",
            core.events[0]["text"],
        )

        self.assertFalse(hasattr(node, "core"))
        self.assertFalse(hasattr(node, "memory"))
        self.assertFalse(hasattr(node, "memory_v2"))
        self.assertFalse(hasattr(node, "identity"))
        self.assertFalse(hasattr(node, "state"))
        self.assertFalse(hasattr(node, "journal"))

    def test_xclass_does_not_receive_core_object(self):
        core = FakeCore()
        xlink = XLink(core)
        node = SymbiontX(xlink)

        self.assertIsNot(node.xlink, core)
        self.assertFalse(hasattr(node, "core"))

    def test_xlink_is_the_only_connection_point(self):
        core = FakeCore()
        xlink = XLink(core)
        node = SymbiontX(xlink)

        self.assertTrue(node.connect("x-node-003"))

        public_node_fields = vars(node)

        self.assertEqual(
            set(public_node_fields.keys()),
            {"xlink", "node_id"},
        )

        self.assertNotIn("core", public_node_fields)
        self.assertNotIn("memory", public_node_fields)
        self.assertNotIn("memory_v2", public_node_fields)
        self.assertNotIn("identity", public_node_fields)
        self.assertNotIn("state", public_node_fields)
        self.assertNotIn("journal", public_node_fields)


if __name__ == "__main__":
    unittest.main()


class SymbiontXCapabilityContractTests(unittest.TestCase):

    ALLOWED_XLINK_OPERATIONS = {
        "connect",
        "disconnect",
        "status",
        "send_event",
    }

    FORBIDDEN_CORE_SURFACES = {
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

    def test_xclass_capability_surface_is_narrow(self):
        xlink = XLink()
        node = SymbiontX(xlink)

        public_methods = {
            name
            for name in dir(xlink)
            if not name.startswith("_")
            and callable(getattr(xlink, name))
        }

        self.assertTrue(
            self.ALLOWED_XLINK_OPERATIONS
            .issubset(public_methods)
        )

        for forbidden in self.FORBIDDEN_CORE_SURFACES:
            self.assertFalse(
                hasattr(node, forbidden),
                f"X-Class exposes forbidden surface: {forbidden}",
            )

    def test_xclass_cannot_access_core_from_node(self):
        core = FakeCore()
        xlink = XLink(core)
        node = SymbiontX(xlink)

        self.assertFalse(hasattr(node, "core"))

        for forbidden in self.FORBIDDEN_CORE_SURFACES:
            self.assertFalse(hasattr(node, forbidden))

    def test_event_is_one_way_boundary(self):
        core = FakeCore()
        xlink = XLink(core)
        node = SymbiontX(xlink)

        node.connect("x-node-capability")

        result = node.emit_event(
            "capability.test",
            {"allowed": True},
        )

        self.assertTrue(result)
        self.assertEqual(len(core.events), 1)

        event = core.events[0]

        self.assertEqual(event["kind"], "external")
        self.assertIn("capability.test", event["text"])

        # X-Class gets no Core object back.
        self.assertIsNone(
            getattr(node, "core", None)
        )


if __name__ == "__main__":
    unittest.main()
