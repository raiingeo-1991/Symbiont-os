import os
import tempfile
import unittest
from pathlib import Path

from core.memory_v2_runtime import (
    MemoryV2Runtime,
)
from symbiont_core import (
    EventJournal,
    MemoryVault,
)


class MemoryV2RuntimeTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

        root = Path(
            self.tmp.name
        )

        self.vault = MemoryVault(
            root / "memory.sqlite3",
            EventJournal(
                root / "events.log"
            ),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_disabled_runtime_does_nothing(self):
        runtime = MemoryV2Runtime(
            self.vault,
            enabled=False,
        )

        self.vault.remember(
            "Владелец любит работать ночью",
            source="owner",
        )

        result = runtime.refresh()

        self.assertFalse(
            result["enabled"]
        )

        self.assertEqual(
            result["indexed"],
            0,
        )

        self.assertEqual(
            runtime.status()["writes_memory"],
            False,
        )

    def test_shadow_refresh_reads_real_vault(self):
        self.vault.remember(
            "Владелец любит работать ночью",
            source="owner",
        )

        self.vault.remember(
            "Ночная работа требует тишины",
            source="owner",
        )

        runtime = MemoryV2Runtime(
            self.vault,
            enabled=True,
            shadow=True,
        )

        result = runtime.refresh()

        self.assertTrue(
            result["enabled"]
        )

        self.assertEqual(
            result["indexed"],
            2,
        )

        self.assertTrue(
            runtime.status()["shadow"]
        )

    def test_shadow_search_does_not_modify_vault(self):
        memory_id = self.vault.remember(
            "Владелец предпочитает работать ночью",
            source="owner",
        )

        before = len(
            self.vault.all_memories(
                limit=100
            )
        )

        runtime = MemoryV2Runtime(
            self.vault,
            enabled=True,
            shadow=True,
        )

        runtime.refresh()

        results = runtime.search(
            "работать ночью"
        )

        after = len(
            self.vault.all_memories(
                limit=100
            )
        )

        self.assertEqual(
            before,
            after,
        )

        self.assertTrue(
            any(
                item.item_id == memory_id
                for item in results
            )
        )

    def test_reflection_stays_candidate_only(self):
        runtime = MemoryV2Runtime(
            self.vault,
            enabled=True,
            shadow=True,
        )

        result = runtime.reflect([
            "Мне нравится работать ночью.",
            "Обычно мне нравится работать ночью.",
        ])

        self.assertIsNotNone(
            result
        )

        self.assertEqual(
            len(result.candidates),
            1,
        )

        consolidated = runtime.consolidate(
            result
        )

        self.assertEqual(
            len(consolidated.accepted),
            1,
        )

        self.assertEqual(
            consolidated.accepted[0].status,
            "validated",
        )

        # Still no write to MemoryVault.
        self.assertEqual(
            len(
                self.vault.all_memories(
                    limit=100
                )
            ),
            0,
        )

    def test_graph_can_be_built_from_shadow_index(self):
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

        runtime = MemoryV2Runtime(
            self.vault,
            enabled=True,
            shadow=True,
        )

        runtime.refresh()

        count = (
            runtime.build_experience_graph()
        )

        self.assertEqual(
            count,
            2,
        )

        related = runtime.graph.related(
            first
        )

        self.assertEqual(
            len(related),
            1,
        )

    def test_environment_flag_false(self):
        old = os.environ.pop(
            "SYMBIONT_MEMORY_V2",
            None,
        )

        try:
            runtime = MemoryV2Runtime(
                self.vault
            )

            self.assertFalse(
                runtime.enabled
            )
        finally:
            if old is not None:
                os.environ[
                    "SYMBIONT_MEMORY_V2"
                ] = old

    def test_environment_flag_true(self):
        old = os.environ.get(
            "SYMBIONT_MEMORY_V2"
        )

        try:
            os.environ[
                "SYMBIONT_MEMORY_V2"
            ] = "true"

            runtime = MemoryV2Runtime(
                self.vault
            )

            self.assertTrue(
                runtime.enabled
            )
        finally:
            if old is None:
                os.environ.pop(
                    "SYMBIONT_MEMORY_V2",
                    None,
                )
            else:
                os.environ[
                    "SYMBIONT_MEMORY_V2"
                ] = old

    def test_decay_is_read_only(self):
        runtime = MemoryV2Runtime(
            self.vault,
            enabled=True,
            shadow=True,
        )

        result = runtime.decay_score(
            importance=0.8,
            activation=1.0,
            age_seconds=86400,
        )

        self.assertIsNotNone(
            result
        )

        self.assertGreaterEqual(
            result.activation,
            0.0,
        )

        self.assertFalse(
            runtime.status()[
                "writes_memory"
            ]
        )


if __name__ == "__main__":
    unittest.main()
