import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import symbiont_core as core


class FakeBody:
    def __init__(self):
        self.calls = []

    def battery(self):
        self.calls.append("battery")
        return 73.0

    def speak(self, text):
        self.calls.append("speak")
        return True

    def listen(self):
        self.calls.append("listen")
        return "test"

    def notify(self, title, content):
        self.calls.append("notify")
        return True

    def sensor(self, name):
        self.calls.append("sensor")
        return {}

    def location(self):
        self.calls.append("location")
        return {}

    def vibrate(self, duration):
        self.calls.append("vibrate")
        return True


class TestCoreBodyPermissions(unittest.TestCase):

    def test_battery_denied_does_not_call_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            bodies = core.Bodies(Path(tmp) / "bodies.json")
            fake = FakeBody()
            bodies.set_permission_checker(lambda cap: False)

            with patch.object(core, "BODY", fake):
                self.assertIsNone(bodies.battery())

            self.assertEqual(fake.calls, [])

    def test_battery_allowed_calls_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            bodies = core.Bodies(Path(tmp) / "bodies.json")
            fake = FakeBody()
            bodies.set_permission_checker(lambda cap: cap == "sensor_read")

            with patch.object(core, "BODY", fake):
                self.assertEqual(bodies.battery(), 73.0)

            self.assertEqual(fake.calls, ["battery"])

    def test_shell_device_commands_are_denied_before_body_call(self):
        permissions = core.PermissionGate()
        fake = FakeBody()
        shell = core.Shell(SimpleNamespace(permissions=permissions))

        commands = (
            "speak hello",
            "услышь",
            "notify hello",
            "sensor",
            "location",
            "vibrate",
        )

        with patch.object(core, "BODY", fake):
            for command in commands:
                with self.subTest(command=command):
                    self.assertTrue(shell.execute(command))

        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
