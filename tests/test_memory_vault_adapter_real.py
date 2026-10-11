import tempfile
import unittest
from pathlib import Path

from core.associative_memory import AssociativeMemory
from core.memory_vault_adapter import MemoryVaultAdapter
from symbiont_core import EventJournal, MemoryVault


class RealMemoryVaultAdapterTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)

        self.journal = EventJournal(
            root / "events.log"
        )

        self.vault = MemoryVault(
            root / "memory.sqlite3",
            self.journal,
        )

        self.associative = AssociativeMemory()

        self.adapter = MemoryVaultAdapter(
            self.vault,
            self.associative,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_memoryvault_records_are_indexed(self):
        first = self.vault.remember(
            "Владелец любит работать ночью",
            kind="preference",
            importance=9,
            source="owner",
        )

        second = self.vault.remember(
            "Ночная работа требует тишины",
            kind="general",
            importance=7,
            source="owner",
        )

        result = self.adapter.refresh()

        self.assertEqual(
            result["indexed"],
            2,
        )

        self.assertIsNotNone(
            self.associative.get(first)
        )

        self.assertIsNotNone(
            self.associative.get(second)
        )

    def test_real_metadata_is_preserved(self):
        memory_id = self.vault.remember(
            "Владелец любит работать ночью",
            kind="preference",
            importance=9,
            source="owner",
            tags=["work", "night"],
            metadata={
                "learning_source": "owner",
            },
        )

        self.adapter.refresh()

        item = self.associative.get(
            memory_id
        )

        self.assertEqual(
            item.metadata["memory_id"],
            memory_id,
        )

        self.assertEqual(
            item.metadata["kind"],
            "preference",
        )

        self.assertEqual(
            item.metadata["importance"],
            9,
        )

        self.assertEqual(
            item.metadata["source"],
            "owner",
        )

        self.assertEqual(
            item.metadata["tags"],
            ["work", "night"],
        )

    def test_real_links_are_imported(self):
        first = self.vault.remember(
            "Работа ночью",
            source="owner",
        )

        second = self.vault.remember(
            "Тишина",
            source="owner",
        )

        self.vault.link(
            first,
            second,
            "context",
            0.8,
        )

        result = self.adapter.refresh()

        self.assertEqual(
            result["links"],
            1,
        )

        related = self.adapter.related(
            first
        )

        self.assertEqual(
            len(related),
            1,
        )

        self.assertEqual(
            related[0][1].item_id,
            second,
        )

        self.assertEqual(
            related[0][0].relation,
            "context",
        )

    def test_real_search(self):
        memory_id = self.vault.remember(
            "Владелец предпочитает работать ночью",
            source="owner",
        )

        self.adapter.refresh()

        results = self.adapter.search(
            "работать ночью"
        )

        ids = {
            item.item_id
            for item in results
        }

        self.assertIn(
            memory_id,
            ids,
        )

    def test_real_vault_is_not_modified_by_refresh(self):
        self.vault.remember(
            "Первое знание",
            source="owner",
        )

        self.vault.remember(
            "Второе знание",
            source="owner",
        )

        before = len(
            self.vault.all_memories(
                limit=100
            )
        )

        self.adapter.refresh()

        after = len(
            self.vault.all_memories(
                limit=100
            )
        )

        self.assertEqual(
            before,
            after,
        )


if __name__ == "__main__":
    unittest.main()
