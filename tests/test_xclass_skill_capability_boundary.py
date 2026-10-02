import unittest

from core.body import XLink
from experiments.x_class.x_class_node import XClassNode
from experiments.x_class.skill_module import XClassSkillModule


class XClassSkillCapabilityBoundaryTests(unittest.TestCase):

    def test_skill_declares_capability_without_security_access(self):
        module = XClassSkillModule(
            "diagnostics",
            "medical",
            capabilities=["sensor.read"],
        )

        self.assertEqual(
            module.info()["capabilities"],
            ["sensor.read"],
        )

        self.assertFalse(hasattr(module, "security"))
        self.assertFalse(hasattr(module, "permissions"))
        self.assertFalse(hasattr(module, "gate"))

    def test_skill_module_does_not_receive_xclass_core_access(self):
        node = XClassNode(
            XLink(),
            specialization="medical",
            owner_type="organization",
        )

        module = XClassSkillModule(
            "diagnostics",
            node.specialization,
            capabilities=["sensor.read"],
        )

        self.assertEqual(
            module.specialization,
            node.specialization,
        )

        self.assertFalse(hasattr(module, "core"))
        self.assertFalse(hasattr(module, "memory"))
        self.assertFalse(hasattr(module, "identity"))
        self.assertFalse(hasattr(module, "state"))
        self.assertFalse(hasattr(module, "journal"))

    def test_skill_capability_is_not_permission(self):
        module = XClassSkillModule(
            "diagnostics",
            "medical",
            capabilities=["sensor.read"],
        )

        self.assertTrue(
            "sensor.read" in module.info()["capabilities"]
        )

        self.assertFalse(
            hasattr(module, "allow")
        )
        self.assertFalse(
            hasattr(module, "grant")
        )
        self.assertFalse(
            hasattr(module, "authorize")
        )


if __name__ == "__main__":
    unittest.main()
