import unittest

from core.body import XLink
from core.security import SecurityError
from experiments.x_class.x_class_node import XClassNode


class XClassCapabilityBoundaryTests(unittest.TestCase):

    def test_capability_is_denied_by_default(self):
        security = __import__(
            "core.security",
            fromlist=["get_security"],
        ).get_security()

        self.assertFalse(
            security.capabilities.allowed("sensor.read")
        )

    def test_capability_can_be_granted_and_revoked(self):
        security = __import__(
            "core.security",
            fromlist=["get_security"],
        ).get_security()

        security.capabilities.grant("sensor.read")

        self.assertTrue(
            security.capabilities.allowed("sensor.read")
        )

        security.capabilities.revoke("sensor.read")

        self.assertFalse(
            security.capabilities.allowed("sensor.read")
        )

    def test_xclass_has_no_security_object(self):
        xlink = XLink()
        node = XClassNode(xlink)

        self.assertFalse(hasattr(node, "security"))
        self.assertFalse(hasattr(node, "permissions"))
        self.assertFalse(hasattr(node, "capabilities"))

    def test_xclass_does_not_receive_core_security_object(self):
        xlink = XLink()
        node = XClassNode(xlink)

        self.assertFalse(hasattr(node, "core"))
        self.assertFalse(hasattr(node, "memory"))
        self.assertFalse(hasattr(node, "identity"))
        self.assertFalse(hasattr(node, "state"))
        self.assertFalse(hasattr(node, "journal"))

    def test_capability_gate_rejects_unauthorized_operation(self):
        security = __import__(
            "core.security",
            fromlist=["get_security"],
        ).get_security()

        security.capabilities.revoke("sensor.read")

        with self.assertRaises(SecurityError):
            security.authorize("sensor.read")


if __name__ == "__main__":
    unittest.main()
