import unittest

from core.body import XLink
from experiments.x_class.x_class_node import XClassNode
from experiments.x_class.skill_module import XClassSkillModule


class XClassSkillIntegrationTests(unittest.TestCase):

    def test_specialized_node_accepts_matching_skill_module(self):
        node = XClassNode(
            XLink(),
            specialization="medical",
            owner_type="organization",
        )

        module = XClassSkillModule(
            "diagnostics",
            "medical",
            capabilities=["sensor.read", "medical.diagnostics"],
        )

        self.assertEqual(
            node.specialization,
            module.specialization,
        )

        self.assertEqual(
            module.info()["capabilities"],
            ["sensor.read", "medical.diagnostics"],
        )

        self.assertFalse(hasattr(module, "core"))
        self.assertFalse(hasattr(module, "memory"))
        self.assertFalse(hasattr(module, "identity"))

    def test_mismatched_skill_module_is_rejected_by_contract(self):
        node = XClassNode(
            XLink(),
            specialization="police",
            owner_type="organization",
        )

        module = XClassSkillModule(
            "diagnostics",
            "medical",
        )

        self.assertNotEqual(
            node.specialization,
            module.specialization,
        )

    def test_skill_module_does_not_modify_xlink_state(self):
        xlink = XLink()

        node = XClassNode(
            xlink,
            specialization="enterprise",
            owner_type="none",
        )

        module = XClassSkillModule(
            "business-operations",
            "enterprise",
        )

        self.assertFalse(xlink.connected)
        self.assertIsNone(node.node_id)

        self.assertEqual(
            module.specialization,
            node.specialization,
        )

        self.assertFalse(xlink.connected)


if __name__ == "__main__":
    unittest.main()
