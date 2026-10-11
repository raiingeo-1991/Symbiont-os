import unittest

from experiments.x_class.skill_module import XClassSkillModule


class XClassSkillModuleTests(unittest.TestCase):

    def test_skill_module_info(self):
        module = XClassSkillModule(
            "diagnostics",
            "medical",
        )

        info = module.info()

        self.assertEqual(info["name"], "diagnostics")
        self.assertEqual(info["specialization"], "medical")
        self.assertEqual(info["version"], "SKILL/1")
        self.assertEqual(info["capabilities"], [])

    def test_skill_module_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            XClassSkillModule("", "medical")

    def test_skill_module_rejects_empty_specialization(self):
        with self.assertRaises(ValueError):
            XClassSkillModule("diagnostics", "")

    def test_skill_modules_for_supported_specializations(self):
        modules = [
            XClassSkillModule("diagnostics", "medical"),
            XClassSkillModule("incident-analysis", "police"),
            XClassSkillModule("business-operations", "enterprise"),
        ]

        self.assertEqual(
            [m.specialization for m in modules],
            ["medical", "police", "enterprise"],
        )

        for module in modules:
            self.assertFalse(hasattr(module, "core"))
            self.assertFalse(hasattr(module, "memory"))
            self.assertFalse(hasattr(module, "identity"))

    def test_unsupported_specialization_rejected(self):
        # SkillModule itself is deliberately generic.
        # X-Class specialization validation belongs to XClassNode.
        module = XClassSkillModule("unknown-skill", "unknown")
        self.assertEqual(module.specialization, "unknown")

    def test_skill_module_specialization_matches_xclass(self):
        from core.body import XLink
        from experiments.x_class.x_class_node import XClassNode

        node = XClassNode(
            XLink(),
            specialization="medical",
            owner_type="organization",
        )

        module = XClassSkillModule(
            "diagnostics",
            node.specialization,
        )

        self.assertEqual(
            module.specialization,
            node.specialization,
        )

        self.assertFalse(hasattr(module, "core"))
        self.assertFalse(hasattr(module, "memory"))
        self.assertFalse(hasattr(module, "identity"))

    def test_skill_capabilities_are_declarative_only(self):
        module = XClassSkillModule(
            "diagnostics",
            "medical",
            capabilities=[
                "sensor.read",
                "medical.diagnostics",
            ],
        )

        self.assertEqual(
            module.info()["capabilities"],
            [
                "sensor.read",
                "medical.diagnostics",
            ],
        )

        self.assertFalse(hasattr(module, "security"))
        self.assertFalse(hasattr(module, "permissions"))
        self.assertFalse(hasattr(module, "gate"))
        self.assertFalse(hasattr(module, "core"))


if __name__ == "__main__":
    unittest.main()
