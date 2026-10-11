import importlib
import unittest
from unittest.mock import patch


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

    @patch("core.android_bridge.shutil.which", return_value="/data/data/com.termux/files/usr/bin/termux-tts-speak")
    def test_android_bridge_detects_termux_api(self, which):
        bridge = importlib.import_module("core.android_bridge")

        self.assertTrue(bridge.is_available())
        which.assert_called_once_with("termux-tts-speak")


if __name__ == "__main__":
    unittest.main()
