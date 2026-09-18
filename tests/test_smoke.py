import importlib
import unittest


class CoreImportTests(unittest.TestCase):
    def test_core_loads_body(self):
        core = importlib.import_module("symbiont_core")

        self.assertIsNotNone(core.BODY)
        self.assertIsNotNone(core.OpenAIProvider)
        self.assertTrue(core.BODY.is_available())
        self.assertIn(core.BODY.name, {"null", "android"})

    def test_body_module_is_importable(self):
        body = importlib.import_module("core.body")

        selected = body.get_body(force="null")
        self.assertEqual(selected.name, "null")
        self.assertTrue(selected.is_available())

        android = body.get_body(force="android")
        self.assertIsNotNone(android._bridge)


if __name__ == "__main__":
    unittest.main()
