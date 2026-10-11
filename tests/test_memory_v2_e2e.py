import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from symbiont_core import MemoryVault, EventJournal
from core.memory_v2_runtime import MemoryV2Runtime


class MemoryV2E2ETests(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)

        self.vault = MemoryVault(
            root / "memory.sqlite3",
            EventJournal(root / "events.log"),
        )

        self.a = self.vault.remember(
            "Владелец предпочитает работать ночью",
            kind="general",
            importance=9,
            source="owner",
        )

        self.b = self.vault.remember(
            "Ночная работа требует тишины",
            kind="general",
            importance=8,
            source="owner",
        )

        self.c = self.vault.remember(
            "Проект развивается через модульную архитектуру",
            kind="project",
            importance=9,
            source="owner",
        )

        self.vault.link(
            self.a,
            self.b,
            "context",
            0.8,
        )

        self.runtime = MemoryV2Runtime(
            self.vault,
            enabled=True,
            shadow=True,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_shadow_pipeline(self):
        before = len(self.vault.all_memories(limit=100))

        # 1. Existing MemoryVault -> associative shadow index
        refresh = self.runtime.refresh()

        self.assertEqual(refresh["indexed"], 3)
        self.assertGreaterEqual(refresh["links"], 1)

        # 2. Associative search
        search = self.runtime.search(
            "работать ночью",
            limit=5,
        )

        self.assertTrue(search)
        self.assertTrue(
            any(
                "ночью" in item.content
                for item in search
            )
        )

        # 3. Experience graph
        graph_nodes = self.runtime.build_experience_graph()

        self.assertGreaterEqual(graph_nodes, 3)

        related = self.runtime.graph.related(str(self.a))

        self.assertTrue(related)

        # 4. Spreading activation
        spread = self.runtime.spread(
            [str(self.a)],
            depth=2,
        )

        self.assertTrue(spread)
        self.assertTrue(
            any(item.item_id == str(self.b) for item in spread)
        )

        # 5. Reflection
        reflection = self.runtime.reflect([
            "Мне нравится работать ночью.",
            "Обычно мне нравится работать ночью.",
            "Ночная работа требует тишины.",
        ])

        self.assertIsNotNone(reflection)
        self.assertTrue(reflection.candidates)

        # 6. Consolidation
        consolidated = self.runtime.consolidate(reflection)

        self.assertIsNotNone(consolidated)
        self.assertTrue(consolidated.accepted)

        # 7. Shadow mode must NOT modify MemoryVault
        after = len(self.vault.all_memories(limit=100))

        self.assertEqual(
            before,
            after,
            "Shadow Mode изменил количество записей MemoryVault",
        )

        # 8. Verify source memories still exist
        ids = {
            str(record.memory_id)
            for record in self.vault.all_memories(limit=100)
        }

        self.assertIn(str(self.a), ids)
        self.assertIn(str(self.b), ids)
        self.assertIn(str(self.c), ids)

    def test_shadow_pipeline_does_not_write_new_memory(self):
        before = list(
            self.vault.all_memories(limit=100)
        )

        reflection = self.runtime.reflect([
            "Мне обычно нравится работать ночью.",
            "Я предпочитаю работать ночью.",
            "Ночная работа требует тишины.",
        ])

        self.runtime.consolidate(reflection)

        after = list(
            self.vault.all_memories(limit=100)
        )

        self.assertEqual(
            len(before),
            len(after),
        )

        before_ids = {
            str(x.memory_id)
            for x in before
        }

        after_ids = {
            str(x.memory_id)
            for x in after
        }

        self.assertEqual(
            before_ids,
            after_ids,
        )


if __name__ == "__main__":
    unittest.main()
