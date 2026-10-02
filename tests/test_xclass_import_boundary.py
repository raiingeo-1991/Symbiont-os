import unittest
from pathlib import Path


class XClassImportBoundaryTests(unittest.TestCase):

    def test_xclass_runtime_modules_do_not_import_core(self):
        root = Path("experiments/x_class")

        runtime_files = [
            root / "x_class_node.py",
            root / "skill_module.py",
        ]

        forbidden = (
            "import symbiont_core",
            "from symbiont_core",
        )

        for path in runtime_files:
            text = path.read_text(encoding="utf-8")

            for token in forbidden:
                self.assertNotIn(
                    token,
                    text,
                    f"Forbidden Core import in {path}: {token}",
                )

    def test_xclass_runtime_modules_do_not_reference_core_components(self):
        root = Path("experiments/x_class")

        runtime_files = [
            root / "x_class_node.py",
            root / "skill_module.py",
        ]

        forbidden = (
            "MemoryVault",
            "EventJournal",
            "CognitiveState",
            "PermissionGate",
            "CognitiveEngine",
            "ContextBus",
            "Economy",
        )

        for path in runtime_files:
            text = path.read_text(encoding="utf-8")

            for token in forbidden:
                self.assertNotIn(
                    token,
                    text,
                    f"Forbidden Core component in {path}: {token}",
                )


if __name__ == "__main__":
    unittest.main()
