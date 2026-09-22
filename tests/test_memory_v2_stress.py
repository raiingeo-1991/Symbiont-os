import time
import tracemalloc
import random
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from symbiont_core import MemoryVault, EventJournal
from core.memory_v2_runtime import MemoryV2Runtime


class MemoryV2StressTests(unittest.TestCase):

    def test_30k_memory_stress(self):
        random.seed(7319)

        with TemporaryDirectory() as td:
            root = Path(td)

            vault = MemoryVault(
                root / "memory.sqlite3",
                EventJournal(root / "events.log"),
            )

            print("\n=== MEMORY V2 STRESS ===")
            print("Создаём 30 000 воспоминаний...")

            tracemalloc.start()
            start = time.perf_counter()

            ids = []

            for i in range(30_000):
                topics = [
                    "работа ночью",
                    "проект Symbiont",
                    "модульная архитектура",
                    "память агента",
                    "безопасность сети",
                    "Android Bridge",
                    "P2P сеть",
                    "экономика",
                    "исследования",
                    "автоматизация",
                ]

                topic = topics[i % len(topics)]

                mem_id = vault.remember(
                    f"Тестовая память {i}: {topic}",
                    kind="stress",
                    importance=(i % 10) + 1,
                    source="stress_test",
                    project="Symbiont",
                )

                ids.append(str(mem_id))

            create_time = time.perf_counter() - start

            runtime = MemoryV2Runtime(
                vault,
                enabled=True,
                shadow=True,
            )

            print("Создание:", round(create_time, 3), "сек.")

            # Индексация в associative layer
            start = time.perf_counter()
            refresh = runtime.refresh()
            refresh_time = time.perf_counter() - start

            print("Indexed:", refresh["indexed"])
            print("Links:", refresh["links"])
            print("Индексация:", round(refresh_time, 3), "сек.")

            self.assertEqual(refresh["indexed"], 30_000)

            # Поиск
            start = time.perf_counter()

            queries = [
                "работа ночью",
                "проект Symbiont",
                "память агента",
                "безопасность",
                "архитектура",
                "Android",
                "экономика",
                "P2P",
            ]

            total_results = 0

            for _ in range(100):
                query = random.choice(queries)
                result = runtime.search(query, limit=10)
                total_results += len(result)

            search_time = time.perf_counter() - start

            print("100 поисков:", round(search_time, 3), "сек.")
            print("Результатов:", total_results)

            self.assertGreater(total_results, 0)

            # Spread activation
            seed_ids = ids[:5]

            start = time.perf_counter()

            spread = runtime.spread(
                seed_ids,
                depth=2,
            )

            spread_time = time.perf_counter() - start

            print("Spread:", round(spread_time, 3), "сек.")
            print("Spread results:", len(spread))

            self.assertTrue(spread)

            # Проверяем decay.
            # Он не должен удалять записи из MemoryVault.
            before = len(vault.all_memories(limit=40_000))

            start = time.perf_counter()

            decay_result = runtime.decay()

            decay_time = time.perf_counter() - start

            after = len(vault.all_memories(limit=40_000))

            print("Decay:", round(decay_time, 3), "сек.")
            print("Decay result:", decay_result)
            print("MemoryVault BEFORE:", before)
            print("MemoryVault AFTER :", after)

            self.assertEqual(before, after)

            # Проверка памяти процесса
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            print(
                "Python memory current:",
                round(current / 1024 / 1024, 2),
                "MB"
            )
            print(
                "Python memory peak:",
                round(peak / 1024 / 1024, 2),
                "MB"
            )

            print("\n=== STRESS TEST PASSED ===")


if __name__ == "__main__":
    unittest.main(verbosity=2)
