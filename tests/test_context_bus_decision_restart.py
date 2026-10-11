import tempfile
import unittest
from pathlib import Path

from symbiont_core import Symbiont


class ContextBusDecisionRestartTests(unittest.TestCase):

    def test_think_continues_restored_work_after_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            first = Symbiont(root)

            first.remember(
                "Продолжаем эксперимент восстановления контекста Symbiont после перезапуска.",
                kind="project",
                importance=10,
            )
            first.remember(
                "Нужно проверить восстановление рабочего смысла после restart.",
                kind="goal",
                importance=10,
            )
            first.remember(
                "Не добавлять новые архитектурные слои.",
                kind="principle",
                importance=10,
            )
            first.remember(
                "Проверить продолжение текущего эксперимента после перезапуска.",
                kind="open_loop",
                importance=10,
            )

            first.close()

            second = Symbiont(root)

            try:
                result = second.speak("дальше")

                context = second.context.snapshot()

                self.assertTrue(context["open_loops"])
                self.assertTrue(context["next_step"])
                self.assertEqual(
                    context["next_step"],
                    "Проверить продолжение текущего эксперимента после перезапуска.",
                )

                self.assertTrue(result["response"])


            finally:
                second.close()


if __name__ == "__main__":
    unittest.main()
