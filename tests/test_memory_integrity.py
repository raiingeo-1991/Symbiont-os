import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from symbiont_core import EventJournal, MemoryVault
from core.memory_integrity import MemoryIntegrity, MemoryIntegrityError


class MemoryIntegrityTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

        self.journal = EventJournal(self.root / "events.jsonl")
        self.db_path = self.root / "memory.sqlite3"

        self.vault = MemoryVault(
            self.db_path,
            self.journal,
        )

        self.integrity = MemoryIntegrity(
            self.vault,
            self.root / "memory.integrity.json",
        )

    def tearDown(self):
        try:
            self.vault.close()
        finally:
            self.tmp.cleanup()

    def test_write_verify_ok(self):
        self.vault.remember(
            "Memory integrity test",
            kind="general",
            importance=8,
            metadata={"test": True},
            tags=["integrity"],
        )

        manifest = self.integrity.save_snapshot()

        self.assertEqual(manifest["memory_count"], 1)

        result = self.integrity.verify()

        self.assertTrue(result["valid"])
        self.assertEqual(result["expected_count"], 1)
        self.assertEqual(result["current_count"], 1)
        self.assertEqual(result["changed"], [])
        self.assertEqual(result["added"], [])
        self.assertEqual(result["removed"], [])

    def test_restart_verify_ok(self):
        memory_id = self.vault.remember(
            "Persistent integrity record",
            kind="principle",
            importance=9,
        )

        self.integrity.save_snapshot()
        self.vault.close()

        journal = EventJournal(self.root / "events.jsonl")
        vault = MemoryVault(
            self.db_path,
            journal,
        )

        try:
            integrity = MemoryIntegrity(
                vault,
                self.root / "memory.integrity.json",
            )

            result = integrity.verify()

            self.assertTrue(result["valid"])
            self.assertEqual(result["current_count"], 1)
            self.assertEqual(result["changed"], [])
            self.assertIn(
                memory_id,
                integrity.load_snapshot()["records"],
            )
        finally:
            vault.close()

    def test_tamper_one_record_detected(self):
        memory_id = self.vault.remember(
            "Original memory text",
            kind="general",
            importance=7,
        )

        self.integrity.save_snapshot()

        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "UPDATE memories SET text = ? WHERE memory_id = ?",
                ("TAMPERED MEMORY TEXT", memory_id),
            )
            db.commit()

        result = self.integrity.verify()

        self.assertFalse(result["valid"])
        self.assertEqual(result["changed"], [memory_id])

    def test_tamper_metadata_detected(self):
        memory_id = self.vault.remember(
            "Metadata integrity test",
            metadata={"owner": "original"},
        )

        self.integrity.save_snapshot()

        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "UPDATE memories SET metadata = ? WHERE memory_id = ?",
                (json.dumps({"owner": "tampered"}), memory_id),
            )
            db.commit()

        result = self.integrity.verify()

        self.assertFalse(result["valid"])
        self.assertEqual(result["changed"], [memory_id])

    def test_added_record_detected(self):
        self.vault.remember("Original record")
        self.integrity.save_snapshot()

        self.vault.remember("Unexpected record")

        result = self.integrity.verify()

        self.assertFalse(result["valid"])
        self.assertEqual(len(result["added"]), 1)

    def test_removed_record_detected(self):
        memory_id = self.vault.remember("Record to remove")
        self.integrity.save_snapshot()

        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "DELETE FROM memories WHERE memory_id = ?",
                (memory_id,),
            )
            db.commit()

        result = self.integrity.verify()

        self.assertFalse(result["valid"])
        self.assertEqual(result["removed"], [memory_id])

    def test_assert_valid_raises_after_tamper(self):
        memory_id = self.vault.remember("Protected record")
        self.integrity.save_snapshot()

        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "UPDATE memories SET importance = ? WHERE memory_id = ?",
                (1, memory_id),
            )
            db.commit()

        with self.assertRaises(MemoryIntegrityError):
            self.integrity.assert_valid()


if __name__ == "__main__":
    unittest.main()


def test_memory_journal_outbox_recovers_after_journal_failure(tmp_path):
    journal_path = tmp_path / "events.log"
    journal = EventJournal(journal_path)
    vault = MemoryVault(tmp_path / "memory.sqlite3", journal)

    original_append = journal.append
    calls = {"count": 0}

    def fail_once(event_type, payload):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("simulated journal disk failure")
        return original_append(event_type, payload)

    journal.append = fail_once
    memory_id = vault.remember("Outbox recovery record", kind="principle")
    assert vault.journal_outbox_status()["pending"] == 1
    assert vault.db.execute(
        "SELECT 1 FROM memories WHERE memory_id = ?", (memory_id,)
    ).fetchone() is not None
    vault.close()

    restarted = MemoryVault(tmp_path / "memory.sqlite3", EventJournal(journal_path))
    try:
        assert restarted.journal_outbox_status()["pending"] == 0
        events = EventJournal(journal_path).all_events()
        matching = [
            event for event in events
            if event.get("type") == "memory.created"
            and event.get("payload", {}).get("memory_id") == memory_id
        ]
        assert len(matching) == 1
    finally:
        restarted.close()


def test_memory_journal_outbox_does_not_duplicate_after_append_before_ack(tmp_path):
    journal_path = tmp_path / "events.log"
    journal = EventJournal(journal_path)
    vault = MemoryVault(tmp_path / "memory.sqlite3", journal)

    original_append = journal.append
    def append_then_fail_ack(event_type, payload):
        original_append(event_type, payload)
        raise OSError("simulated crash after journal append")
    journal.append = append_then_fail_ack

    memory_id = vault.remember("Outbox duplicate protection", kind="general")
    assert vault.journal_outbox_status()["pending"] == 1
    vault.close()

    restarted = MemoryVault(tmp_path / "memory.sqlite3", EventJournal(journal_path))
    try:
        events = EventJournal(journal_path).all_events()
        matching = [
            event for event in events
            if event.get("type") == "memory.created"
            and event.get("payload", {}).get("memory_id") == memory_id
        ]
        assert len(matching) == 1
        assert restarted.journal_outbox_status()["pending"] == 0
    finally:
        restarted.close()
