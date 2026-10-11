import unittest

from experiments.x_class.skill_module import XClassSkillModule


class XClassSkillIsolationTests(unittest.TestCase):

    def test_arbitrary_capabilities_do_not_create_core_access(self):
        module = XClassSkillModule(
            "advanced-medical",
            "medical",
            capabilities=[
                "sensor.read",
                "network.send",
                "task.execute",
                "external_ai.call",
            ],
        )

        self.assertEqual(
            module.info()["capabilities"],
            [
                "sensor.read",
                "network.send",
                "task.execute",
                "external_ai.call",
            ],
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
            "gate",
            "authorize",
            "grant",
            "allow",
        }

        for name in forbidden:
            self.assertFalse(
                hasattr(module, name),
                f"Skill Module exposes forbidden surface: {name}",
            )


if __name__ == "__main__":
    unittest.main()
