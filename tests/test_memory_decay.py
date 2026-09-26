import unittest

from core.memory_decay import MemoryDecay


class MemoryDecayTests(unittest.TestCase):

    def setUp(self):
        self.decay = MemoryDecay(
            half_life_seconds=100.0
        )

    def test_current_memory_keeps_activation(self):
        result = self.decay.apply(
            "1",
            activation=1.0,
            importance=0.5,
            age_seconds=0,
        )

        self.assertAlmostEqual(
            result.activation,
            1.0,
        )

    def test_old_memory_loses_activation(self):
        result = self.decay.apply(
            "1",
            activation=1.0,
            importance=0.5,
            age_seconds=100,
        )

        self.assertAlmostEqual(
            result.activation,
            0.5,
            places=5,
        )

    def test_older_memory_decays_more(self):
        young = self.decay.apply(
            "young",
            activation=1.0,
            importance=0.5,
            age_seconds=50,
        )

        old = self.decay.apply(
            "old",
            activation=1.0,
            importance=0.5,
            age_seconds=300,
        )

        self.assertGreater(
            young.activation,
            old.activation,
        )

    def test_importance_affects_priority(self):
        low = self.decay.score(
            importance=0.2,
            activation=0.5,
            age_seconds=100,
        )

        high = self.decay.score(
            importance=0.9,
            activation=0.5,
            age_seconds=100,
        )

        self.assertGreater(
            high,
            low,
        )

    def test_recall_count_adds_bonus(self):
        without_recall = self.decay.score(
            importance=0.5,
            activation=0.5,
            age_seconds=100,
            recall_count=0,
        )

        with_recall = self.decay.score(
            importance=0.5,
            activation=0.5,
            age_seconds=100,
            recall_count=5,
        )

        self.assertGreater(
            with_recall,
            without_recall,
        )

    def test_rank_orders_by_priority(self):
        results = self.decay.rank([
            {
                "item_id": "old",
                "importance": 0.2,
                "activation": 0.2,
                "age_seconds": 500,
            },
            {
                "item_id": "important",
                "importance": 1.0,
                "activation": 1.0,
                "age_seconds": 0,
            },
        ])

        self.assertEqual(
            results[0].item_id,
            "important",
        )

    def test_decay_never_goes_negative(self):
        result = self.decay.apply(
            "1",
            activation=1.0,
            age_seconds=999999999,
        )

        self.assertGreaterEqual(
            result.activation,
            0.0,
        )

    def test_does_not_delete_memory(self):
        status = self.decay.status()

        self.assertFalse(
            status["deletes_memory"]
        )

    def test_deterministic(self):
        first = self.decay.apply(
            "x",
            activation=0.8,
            importance=0.7,
            age_seconds=250,
            recall_count=3,
        )

        second = self.decay.apply(
            "x",
            activation=0.8,
            importance=0.7,
            age_seconds=250,
            recall_count=3,
        )

        self.assertAlmostEqual(
            first.activation,
            second.activation,
        )

        self.assertAlmostEqual(
            first.priority,
            second.priority,
        )


if __name__ == "__main__":
    unittest.main()
