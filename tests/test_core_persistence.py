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


    def test_recovery_phrase_is_suppressed_when_requested(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                sym = Symbiont(
                    Path(temporary),
                    show_recovery_phrase=False,
                )
            try:
                self.assertIsNotNone(sym.identity.recovery_phrase)
                self.assertNotIn(
                    "ЗАПИШИ RECOVERY PHRASE",
                    output.getvalue(),
                )
                self.assertNotIn(
                    sym.identity.recovery_phrase,
                    output.getvalue(),
                )
            finally:
                sym.close()


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


def test_event_journal_refuses_append_after_truncated_tail(tmp_path):
    path = tmp_path / "events.log"
    journal = EventJournal(path)
    journal.append("first", {"ok": True})
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"event_id":"truncated"')

    restarted = EventJournal(path)
    assert restarted.verify() == (False, 0)
    with unittest.TestCase().assertRaises(ValueError):
        restarted.append("must.not.append", {})
    with unittest.TestCase().assertRaises(ValueError):
        restarted.all_events()


def test_event_journal_detects_same_size_tamper_with_restored_mtime(tmp_path):
    path = tmp_path / "same-size-events.log"
    journal = EventJournal(path)
    journal.append("test.event", {"value": "one"})
    original_stat = path.stat()
    event = json.loads(path.read_text(encoding="utf-8"))
    event["payload"]["value"] = "two"
    path.write_text(canonical_json(event) + "\n", encoding="utf-8")
    assert path.stat().st_size == original_stat.st_size
    import os
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    assert journal.verify() == (False, 0)


def test_event_journal_serializes_writers_from_separate_instances(tmp_path):
    import threading

    path = tmp_path / "multi-writer-events.log"
    journals = [EventJournal(path), EventJournal(path)]
    failures = []

    def write_many(journal, prefix):
        try:
            for index in range(20):
                journal.append("multi.writer", {"writer": prefix, "index": index})
        except Exception as exc:
            failures.append(exc)

    threads = [
        threading.Thread(target=write_many, args=(journals[0], "a")),
        threading.Thread(target=write_many, args=(journals[1], "b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not failures
    assert EventJournal(path).verify() == (True, 40)


def test_event_journal_serializes_writers_across_processes(tmp_path):
    import subprocess
    import sys

    path = tmp_path / "multi-process-events.log"
    worker = (
        "import sys; from symbiont_core import EventJournal; "
        "journal=EventJournal(sys.argv[1]); "
        "[journal.append('process.writer', {'writer': sys.argv[2], 'i': i}) "
        "for i in range(12)]"
    )
    processes = [
        subprocess.Popen([sys.executable, "-c", worker, str(path), label])
        for label in ("one", "two")
    ]
    return_codes = [process.wait(timeout=30) for process in processes]

    assert return_codes == [0, 0]
    assert EventJournal(path).verify() == (True, 24)


def test_event_journal_append_rejects_same_size_tamper_with_restored_mtime(tmp_path):
    import os

    path = tmp_path / "same-size-append-tamper.log"
    journal = EventJournal(path)
    journal.append("test.event", {"value": "one"})
    original_stat = path.stat()
    event = json.loads(path.read_text(encoding="utf-8"))
    event["payload"]["value"] = "two"
    path.write_text(canonical_json(event) + "\n", encoding="utf-8")
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    with unittest.TestCase().assertRaises(ValueError):
        journal.append("must.not.append", {})
    assert journal.verify() == (False, 0)


def test_event_journal_verify_uses_verified_stat_cache(tmp_path, monkeypatch):
    path = tmp_path / "verify-cache.log"
    journal = EventJournal(path)
    journal.append("test.event", {"value": 1})
    original_reader = journal._read_verified_events
    calls = []

    def counted_reader():
        calls.append(True)
        return original_reader()

    monkeypatch.setattr(journal, "_read_verified_events", counted_reader)
    assert journal.verify() == (True, 1)
    assert journal.verify() == (True, 1)
    assert calls == []
