import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from symbiont_core import Symbiont


class MemoryIntegritySymbiontTests(unittest.TestCase):

    def test_real_symbiont_restart_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            # Первый запуск Symbiont
            sym = Symbiont(root=root)

            memory_id = sym.memory.remember(
                "SCA Memory Integrity persistent test",
                kind="principle",
                importance=10,
                tags=["integrity", "sca"],
                metadata={"stage": "memory-integrity"},
            )

            manifest = sym.memory_integrity.save_snapshot()

            self.assertEqual(manifest["memory_count"], 1)
            self.assertTrue(
                (root / "memory.integrity.json").exists()
            )

            sym.memory.close()

            # Второй запуск — тот же Core state / та же SQLite
            sym2 = Symbiont(root=root)

            try:
                result = sym2.memory_integrity.verify()

                self.assertTrue(result["valid"])
                self.assertEqual(result["expected_count"], 1)
                self.assertEqual(result["current_count"], 1)
                self.assertEqual(result["changed"], [])
                self.assertEqual(result["added"], [])
                self.assertEqual(result["removed"], [])

                records = sym2.memory.all_memories(limit=None)

                self.assertEqual(len(records), 1)
                self.assertEqual(records[0].memory_id, memory_id)
                self.assertEqual(
                    records[0].text,
                    "SCA Memory Integrity persistent test",
                )
            finally:
                sym2.memory.close()


if __name__ == "__main__":
    unittest.main()
