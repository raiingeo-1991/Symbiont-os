import unittest

from core.body import XLink
from experiments.x_class.x_class_node import XClassNode
from experiments.x_class.skill_module import XClassSkillModule


class XClassSkillBindingTests(unittest.TestCase):

    def test_skill_binds_to_matching_specialization(self):
        node = XClassNode(
            XLink(),
            specialization="medical",
            owner_type="organization",
        )

        skill = XClassSkillModule(
            "diagnostics",
            "medical",
            capabilities=["sensor.read", "medical.diagnostics"],
        )

        self.assertEqual(skill.specialization, node.specialization)
        self.assertEqual(
            skill.info()["capabilities"],
            ["sensor.read", "medical.diagnostics"],
        )

    def test_skill_does_not_change_xclass_identity_boundary(self):
        node = XClassNode(
            XLink(),
            specialization="police",
            owner_type="organization",
        )

        skill = XClassSkillModule(
            "incident-analysis",
            "police",
            capabilities=["sensor.read"],
        )

        self.assertFalse(hasattr(skill, "core"))
        self.assertFalse(hasattr(skill, "memory"))
        self.assertFalse(hasattr(skill, "identity"))
        self.assertFalse(hasattr(skill, "journal"))
        self.assertFalse(hasattr(skill, "permissions"))
        self.assertFalse(hasattr(skill, "security"))

        self.assertEqual(node.specialization, "police")

    def test_skill_capabilities_do_not_authorize_themselves(self):
        skill = XClassSkillModule(
            "diagnostics",
            "medical",
            capabilities=["sensor.read", "medical.diagnostics"],
        )

        self.assertEqual(
            skill.info()["capabilities"],
            ["sensor.read", "medical.diagnostics"],
        )

        self.assertFalse(hasattr(skill, "authorize"))
        self.assertFalse(hasattr(skill, "grant"))
        self.assertFalse(hasattr(skill, "allow"))

if __name__ == "__main__":
    unittest.main()

    def test_skill_specialization_mismatch_is_rejected(self):
        node = XClassNode(
            XLink(),
            specialization="medical",
            owner_type="organization",
        )

        skill = XClassSkillModule(
            "incident-analysis",
            "police",
        )

        self.assertNotEqual(
            skill.specialization,
            node.specialization,
        )

if __name__ == "__main__":
    unittest.main()

    def test_non_skill_object_is_rejected(self):
        node = XClassNode(
            XLink(),
            specialization="medical",
            owner_type="organization",
        )

        self.assertFalse(
            node.add_skill_module(object())
        )

        self.assertEqual(
            node.skill_modules,
            [],
        )
