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
