import unittest
from dataclasses import dataclass, field

from core.associative_memory import AssociativeMemory
from core.memory_vault_adapter import MemoryVaultAdapter


@dataclass
class FakeRecord:
    id: str
    text: str
    kind: str = "general"
    importance: int = 5
    created_at: str = "2026-01-01"
    updated_at: str = "2026-01-01"
    source: str = "owner"
    project: str = "test"
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class FakeLink:
    from_id: str
    to_id: str
    kind: str = "related"
    strength: float = 1.0


class FakeVault:

    def __init__(self):
        self.records = [
            FakeRecord(
                id="1",
                text="Владелец любит работать ночью",
                importance=9,
            ),
            FakeRecord(
                id="2",
                text="Ночная работа требует тишины",
                importance=7,
            ),
            FakeRecord(
                id="3",
                text="Сегодня идёт дождь",
                importance=2,
            ),
        ]

        self._links = [
            FakeLink(
                from_id="1",
                to_id="2",
                kind="context",
                strength=0.8,
            )
        ]

    def all(self, limit=None):
        if limit is None:
            return list(self.records)
        return list(self.records[:limit])

    def links(self, limit=None):
        if limit is None:
            return list(self._links)
        return list(self._links[:limit])


class MemoryVaultAdapterTests(unittest.TestCase):

    def setUp(self):
        self.vault = FakeVault()
        self.associative = AssociativeMemory()
        self.adapter = MemoryVaultAdapter(
            self.vault,
            self.associative,
        )

    def test_refresh_indexes_records(self):
        result = self.adapter.refresh()

        self.assertEqual(result["indexed"], 3)
        self.assertEqual(result["links"], 1)
        self.assertEqual(
            self.associative.status()["items"],
            3,
        )

    def test_preserves_ids_and_metadata(self):
        self.adapter.refresh()

        item = self.associative.get("1")

        self.assertIsNotNone(item)
        self.assertEqual(
            item.metadata["memory_id"],
            "1",
        )
        self.assertEqual(
            item.metadata["importance"],
            9,
        )
        self.assertEqual(
            item.metadata["source"],
            "owner",
        )

    def test_imports_existing_links(self):
        self.adapter.refresh()

        related = self.adapter.related("1")

        self.assertEqual(len(related), 1)
        self.assertEqual(
            related[0][1].item_id,
            "2",
        )
        self.assertEqual(
            related[0][0].relation,
            "context",
        )

    def test_search(self):
        self.adapter.refresh()

        results = self.adapter.search(
            "работать ночью"
        )

        self.assertTrue(results)
        self.assertEqual(
            results[0].item_id,
            "1",
        )

    def test_source_vault_is_not_modified(self):
        before = len(self.vault.records)

        self.adapter.refresh()

        self.assertEqual(
            len(self.vault.records),
            before,
        )

    def test_spread(self):
        self.adapter.refresh()

        result = self.adapter.spread(
            ["1"],
            depth=1,
        )

        self.assertIn("1", result)
        self.assertIn("2", result)

    def test_status(self):
        self.adapter.refresh()

        status = self.adapter.status()

        self.assertTrue(
            status["persistent_source_of_truth"]
        )
        self.assertEqual(
            status["associative"]["items"],
            3,
        )


if __name__ == "__main__":
    unittest.main()
