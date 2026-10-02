import unittest

from core.body import XLink
from experiments.x_class.x_class_node import XClassNode


class XClassProfileCapabilityTests(unittest.TestCase):

    def test_medical_profile_is_descriptive_only(self):
        node = XClassNode(
            XLink(),
            specialization="medical",
            owner_type="organization",
        )

        self.assertEqual(node.specialization, "medical")
        self.assertEqual(node.owner_type, "organization")
        self.assertFalse(hasattr(node, "permissions"))
        self.assertFalse(hasattr(node, "security"))

    def test_police_profile_is_descriptive_only(self):
        node = XClassNode(
            XLink(),
            specialization="police",
            owner_type="organization",
        )

        self.assertEqual(node.specialization, "police")
        self.assertFalse(hasattr(node, "permissions"))
        self.assertFalse(hasattr(node, "security"))

    def test_enterprise_ownerless_profile_is_descriptive_only(self):
        node = XClassNode(
            XLink(),
            specialization="enterprise",
            owner_type="none",
        )

        self.assertEqual(node.specialization, "enterprise")
        self.assertEqual(node.owner_type, "none")
        self.assertFalse(hasattr(node, "permissions"))
        self.assertFalse(hasattr(node, "security"))

    def test_profile_never_creates_core_capability_surface(self):
        node = XClassNode(
            XLink(),
            specialization="medical",
            owner_type="organization",
        )

        forbidden = {
            "core",
            "memory",
            "memory_v2",
            "identity",
            "state",
            "journal",
            "economy",
            "permissions",
            "security",
            "mind",
            "context",
        }

        for name in forbidden:
            self.assertFalse(hasattr(node, name))


if __name__ == "__main__":
    unittest.main()
