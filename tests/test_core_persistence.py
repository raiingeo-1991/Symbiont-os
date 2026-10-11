import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from symbiont_core import EventJournal, Identity, Symbiont, canonical_json


class IdentityTests(unittest.TestCase):
    def test_recovery_phrase_restores_same_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = Identity(root / "original" / "identity.json")
            phrase = original.recovery_phrase

            restored = Identity(root / "restored" / "identity.json")
            self.assertTrue(restored.restore_from_phrase(phrase))

            self.assertEqual(restored.id(), original.id())
            self.assertEqual(restored.public_key(), original.public_key())
            self.assertEqual(restored.secret_key(), original.secret_key())


class PersistenceTests(unittest.TestCase):
    def test_memory_and_identity_survive_restart_without_llm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                first = Symbiont(root)
            identity = first.identity.id()
            memory_id = first.remember(
                "Проверка долговременной памяти",
                kind="principle",
                importance=10,
                tags=["test"],
            )
            self.assertFalse(first.llm_status()["enabled"])
            first.close()

            with contextlib.redirect_stdout(output):
                second = Symbiont(root)
            try:
                self.assertEqual(second.identity.id(), identity)
                self.assertIsNone(second.identity.recovery_phrase)
                matches = second.memory.search("долговременной памяти")
                self.assertEqual(matches[0].memory_id, memory_id)
                self.assertTrue(second.speak("Проверка без LLM")["response"])
            finally:
                second.close()

    def test_event_journal_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.log"
            journal = EventJournal(path)
            journal.append("test.event", {"value": 1})
            self.assertEqual(journal.verify(), (True, 1))

            event = json.loads(path.read_text(encoding="utf-8"))
            event["payload"]["value"] = 2
            path.write_text(canonical_json(event) + "\n", encoding="utf-8")

            valid, checked = journal.verify()
            self.assertFalse(valid)
            self.assertEqual(checked, 0)


if __name__ == "__main__":
    unittest.main()
