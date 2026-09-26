import unittest

from core.associative_memory import AssociativeMemory


class AssociativeMemoryTests(unittest.TestCase):

    def test_add_and_search(self):
        memory = AssociativeMemory()

        a = memory.add(
            "Владелец любит работать ночью",
            {"source": "owner"},
        )
        memory.add("Сегодня идёт дождь")

        results = memory.search("работать ночью")

        self.assertEqual(results[0].item_id, a)

    def test_relations(self):
        memory = AssociativeMemory()

        a = memory.add("работа")
        b = memory.add("ночь")

        self.assertTrue(
            memory.relate(a, b, "context", 0.8)
        )

        related = memory.related(a)

        self.assertEqual(len(related), 1)
        self.assertEqual(related[0][1].item_id, b)
        self.assertEqual(related[0][0].relation, "context")

    def test_activation(self):
        memory = AssociativeMemory()

        a = memory.add("важное знание")

        self.assertEqual(
            memory.activate([a], 0.7),
            1,
        )

        self.assertAlmostEqual(
            memory.get(a).activation,
            0.7,
        )

    def test_spreading_activation(self):
        memory = AssociativeMemory()

        a = memory.add("работа")
        b = memory.add("ночь")
        c = memory.add("тишина")

        memory.relate(a, b, "context", 0.8)
        memory.relate(b, c, "context", 0.5)

        result = memory.spread([a], depth=2)

        self.assertIn(a, result)
        self.assertIn(b, result)
        self.assertIn(c, result)

        self.assertGreater(result[b], result[c])

    def test_dedup(self):
        memory = AssociativeMemory()

        a = memory.add(
            "Владелец любит работать ночью"
        )
        b = memory.add(
            "Владелец любит работать ночью"
        )

        duplicates = memory.dedup()

        self.assertIn((a, b), duplicates)

    def test_decay(self):
        memory = AssociativeMemory()

        a = memory.add("test")
        memory.activate([a], 1.0)

        memory.decay(0.3)

        self.assertAlmostEqual(
            memory.get(a).activation,
            0.7,
        )

    def test_capacity(self):
        memory = AssociativeMemory(capacity=1)

        memory.add("one")

        with self.assertRaises(MemoryError):
            memory.add("two")


if __name__ == "__main__":
    unittest.main()
