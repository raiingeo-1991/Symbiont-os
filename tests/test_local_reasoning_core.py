import unittest
from types import SimpleNamespace

from symbiont_core import CognitiveEngine


RULE = (
    "когда заряд аккумулятора Альфы опускается ниже 10 процентов, "
    "устройство Альфа отключается."
)


class FakeJournal:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload):
        self.events.append((event_type, payload))


def memory(text, kind, created_at):
    return SimpleNamespace(text=text, kind=kind, created_at=created_at)


class LocalReasoningCoreTests(unittest.TestCase):
    def run_reasoning(self, states):
        engine = CognitiveEngine.__new__(CognitiveEngine)
        engine.journal = FakeJournal()
        records = [memory(RULE, "principle", "2026-10-01T00:00:00")]
        records.extend(states)
        answer = engine._local_reasoning("проверь правило", records)
        return answer, engine.journal.events

    def test_latest_false_target_state_blocks_older_true_state(self):
        answer, events = self.run_reasoning([
            memory("заряд аккумулятора Альфы составляет 7 процентов.",
                   "general", "2026-10-17T10:00:00"),
            memory("заряд аккумулятора Альфы составляет 15 процентов.",
                   "general", "2026-10-18T10:00:00"),
        ])
        self.assertIsNone(answer)
        self.assertEqual(events, [])

    def test_newer_foreign_device_does_not_block_target(self):
        answer, events = self.run_reasoning([
            memory("заряд аккумулятора Альфы составляет 7 процентов.",
                   "general", "2026-10-17T10:00:00"),
            memory("заряд аккумулятора Беты составляет 5 процентов.",
                   "general", "2026-10-18T10:00:00"),
        ])
        self.assertIsNotNone(answer)
        self.assertEqual(len(events), 1)

    def test_missing_subject_alone_does_not_trigger_target_rule(self):
        answer, events = self.run_reasoning([
            memory("заряд аккумулятора составляет 5 процентов.",
                   "general", "2026-10-18T10:00:00"),
        ])
        self.assertIsNone(answer)
        self.assertEqual(events, [])

    def test_latest_true_target_state_triggers_rule(self):
        answer, events = self.run_reasoning([
            memory("заряд аккумулятора Альфы составляет 7 процентов.",
                   "general", "2026-10-18T10:00:00"),
        ])
        self.assertIsNotNone(answer)
        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
