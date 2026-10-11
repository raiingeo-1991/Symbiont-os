import tempfile
import unittest
from pathlib import Path

from symbiont_core import Symbiont


class ContextContinuityE2ETests(unittest.TestCase):

    def test_working_line_survives_restart_and_is_used(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            first = Symbiont(root)

            next_step = "Проверить сквозное восстановление рабочего смысла после restart."

            first.remember(
                "Эксперимент проверяет непрерывность рабочего контекста Symbiont.",
                kind="project",
                importance=10,
            )
            first.remember(
                "Нужно доказать, что Core продолжает работу после смены процесса.",
                kind="goal",
                importance=10,
            )
            first.remember(
                "Не добавлять новые архитектурные слои.",
                kind="principle",
                importance=10,
            )
            first.remember(
                next_step,
                kind="open_loop",
                importance=10,
            )

            first.close()

            second = Symbiont(root)

            try:
                context = second.context.snapshot()

                # 1. Смысл восстановлен.
                self.assertEqual(context["next_step"], next_step)
                self.assertIn(next_step, context["open_loops"])

                # 2. Новый процесс действительно использует
                # восстановленный смысл.
                result = second.speak("дальше")

                self.assertTrue(result["response"])
                self.assertIn(next_step, result["response"])

                # 3. Ответ получен без LLM.
                self.assertEqual(result["source"], "local")

            finally:
                second.close()


if __name__ == "__main__":
    unittest.main()
