import unittest

from core.body import XLink
from experiments.x_class.x_class_node import XClassNode


class XClassSpecializationTests(unittest.TestCase):

    def test_medical_node(self):
        node = XClassNode(
            XLink(),
            specialization="medical",
            owner_type="organization",
        )

        self.assertEqual(node.specialization, "medical")
        self.assertEqual(node.owner_type, "organization")

    def test_police_node(self):
        node = XClassNode(
            XLink(),
            specialization="police",
            owner_type="organization",
        )

        self.assertEqual(node.specialization, "police")
        self.assertEqual(node.owner_type, "organization")

    def test_ownerless_enterprise_node(self):
        node = XClassNode(
            XLink(),
            specialization="enterprise",
            owner_type="none",
        )

        self.assertEqual(node.specialization, "enterprise")
        self.assertEqual(node.owner_type, "none")

    def test_specialization_does_not_grant_core_access(self):
        node = XClassNode(
            XLink(),
            specialization="medical",
            owner_type="organization",
        )

        forbidden = {
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
            self.assertFalse(hasattr(node, name))


if __name__ == "__main__":
    unittest.main()

    def test_profile_contract_contains_supported_specializations(self):
        self.assertEqual(
            XClassNode.SPECIALIZATIONS,
            {"general", "medical", "police", "enterprise"},
        )

    def test_profile_contract_contains_supported_owner_types(self):
        self.assertEqual(
            XClassNode.OWNER_TYPES,
            {"personal", "organization", "none"},
        )
