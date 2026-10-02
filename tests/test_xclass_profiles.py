import unittest

from core.body import XLink
from experiments.x_class.x_class_node import XClassNode


class XClassProfileTests(unittest.TestCase):

    def test_personal_profile(self):
        node = XClassNode(
            XLink(),
            specialization="general",
            owner_type="personal",
        )

        status = node.status()

        self.assertEqual(status["class"], "X-Class")
        self.assertEqual(status["specialization"], "general")
        self.assertEqual(status["owner_type"], "personal")

    def test_specialized_profile(self):
        node = XClassNode(
            XLink(),
            specialization="medical",
            owner_type="organization",
        )

        status = node.status()

        self.assertEqual(status["specialization"], "medical")
        self.assertEqual(status["owner_type"], "organization")

    def test_ownerless_enterprise_node(self):
        node = XClassNode(
            XLink(),
            specialization="enterprise",
            owner_type="none",
        )

        status = node.status()

        self.assertEqual(status["specialization"], "enterprise")
        self.assertEqual(status["owner_type"], "none")

    def test_profile_does_not_create_core_access(self):
        node = XClassNode(
            XLink(),
            specialization="police",
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
            "mind",
            "context",
        }

        for name in forbidden:
            self.assertFalse(hasattr(node, name))


if __name__ == "__main__":
    unittest.main()
