import unittest

from core.security import get_security
from core.body import XLink
from experiments.x_class.x_class_node import XClassNode


class XClassCapabilityVisibilityTests(unittest.TestCase):

    def test_security_snapshot_is_independent_copy(self):
        security = get_security()

        snapshot = security.capabilities.snapshot()

        self.assertIsInstance(snapshot, dict)

        snapshot["sensor.read"] = True

        self.assertFalse(
            security.capabilities.allowed("sensor.read")
        )

    def test_xclass_does_not_expose_security_snapshot_directly(self):
        node = XClassNode(XLink())

        self.assertFalse(hasattr(node, "security"))
        self.assertFalse(hasattr(node, "capabilities"))
        self.assertFalse(hasattr(node, "permissions"))

    def test_capability_state_can_be_described_without_core_access(self):
        security = get_security()

        security.capabilities.revoke("sensor.read")
        security.capabilities.grant("network.send")

        snapshot = security.capabilities.snapshot()

        self.assertFalse(snapshot["sensor.read"])
        self.assertTrue(snapshot["network.send"])

        node = XClassNode(XLink())

        self.assertFalse(hasattr(node, "core"))
        self.assertFalse(hasattr(node, "memory"))
        self.assertFalse(hasattr(node, "identity"))

    def test_unknown_capability_is_not_granted_by_default(self):
        security = get_security()

        self.assertFalse(
            security.capabilities.allowed("xclass.admin")
        )


if __name__ == "__main__":
    unittest.main()
