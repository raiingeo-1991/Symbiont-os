import tempfile
import unittest
from pathlib import Path

from symbiont_core import Symbiont


class ContextBusRestartTests(unittest.TestCase):

    def test_semantic_context_survives_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            first = Symbiont(root)

            first.remember(
                "Symbiont — текущий проект непрерывности и восстановления контекста.",
                kind="project",
                importance=10,
            )
            first.remember(
                "Продолжить эксперимент восстановления контекста после перезапуска.",
                kind="goal",
                importance=10,
            )
            first.remember(
                "Проверить восстановление ContextBus после перезапуска.",
                kind="open_loop",
                importance=10,
            )
            first.remember(
                "Не добавлять новые архитектурные слои.",
                kind="principle",
                importance=10,
            )

            first.speak("Продолжить текущий эксперимент.")

            snapshot1 = first.mind._build_semantic_context(
                request="Продолжить текущий эксперимент."
            )

            first.close()

            second = Symbiont(root)

            snapshot2 = second.mind._build_semantic_context(
                request="Продолжить текущий эксперимент."
            )

            try:
                self.assertTrue(snapshot2["identity"])
                self.assertTrue(snapshot2["project"])
                self.assertTrue(snapshot2["goal"])
                self.assertTrue(snapshot2["principles"])
                self.assertTrue(snapshot2["constraints"])
                self.assertTrue(snapshot2["next_step"])

                self.assertEqual(snapshot1["project"], snapshot2["project"])
                self.assertEqual(snapshot1["goal"], snapshot2["goal"])
                self.assertEqual(snapshot1["principles"], snapshot2["principles"])
                self.assertEqual(snapshot1["constraints"], snapshot2["constraints"])
                self.assertEqual(snapshot1["next_step"], snapshot2["next_step"])

                self.assertTrue(second.context.summary()["complete"])

            finally:
                second.close()


if __name__ == "__main__":
    unittest.main()
