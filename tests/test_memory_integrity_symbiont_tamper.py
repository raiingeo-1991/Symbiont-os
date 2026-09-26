import sqlite3
import tempfile
import unittest
from pathlib import Path

from symbiont_core import Symbiont


class MemoryIntegritySymbiontTamperTests(unittest.TestCase):

    def test_real_symbiont_detects_sqlite_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            sym = Symbiont(root=root)

            memory_id = sym.memory.remember(
                "Protected Symbiont memory",
                kind="principle",
                importance=10,
                tags=["integrity"],
                metadata={"protected": True},
            )

            sym.memory_integrity.save_snapshot()
            sym.memory.close()

            # Намеренно повреждаем SQLite напрямую.
            with sqlite3.connect(root / "memory.sqlite3") as db:
                db.execute(
                    "UPDATE memories SET text = ? WHERE memory_id = ?",
                    ("TAMPERED BY TEST", memory_id),
                )
                db.commit()

            # Загружаем тот же Symbiont заново.
            sym2 = Symbiont(root=root)

            try:
                result = sym2.memory_integrity.verify()

                self.assertFalse(result["valid"])
                self.assertEqual(result["changed"], [memory_id])
                self.assertEqual(result["added"], [])
                self.assertEqual(result["removed"], [])

            finally:
                sym2.memory.close()


if __name__ == "__main__":
    unittest.main()
