import unittest

from core.reflection_engine import ReflectionEngine


class ReflectionEngineTests(unittest.TestCase):

    def setUp(self):
        self.engine = ReflectionEngine()

    def test_empty_input(self):
        result = self.engine.reflect([])

        self.assertEqual(
            result.observations,
            0,
        )
        self.assertEqual(
            result.candidates,
            [],
        )

    def test_single_observation_is_not_enough(self):
        result = self.engine.reflect([
            "Мне обычно нравится работать ночью."
        ])

        self.assertEqual(
            result.observations,
            1,
        )
        self.assertEqual(
            result.candidates,
            [],
        )

    def test_repeated_pattern_creates_candidate(self):
        result = self.engine.reflect([
            "Мне обычно нравится работать ночью.",
            "Мне нравится работать ночью, когда тихо.",
        ])

        self.assertEqual(
            len(result.candidates),
            1,
        )

        candidate = result.candidates[0]

        self.assertGreaterEqual(
            candidate.confidence,
            0.65,
        )

        self.assertEqual(
            candidate.status,
            "candidate",
        )

        self.assertEqual(
            len(candidate.evidence),
            2,
        )

    def test_three_observations_increase_confidence(self):
        result = self.engine.reflect([
            "Мне нравится работать ночью.",
            "Обычно мне нравится работать ночью.",
            "Я предпочитаю работать ночью.",
        ])

        candidate = result.candidates[0]

        self.assertEqual(
            len(candidate.evidence),
            3,
        )

        self.assertGreater(
            candidate.confidence,
            0.70,
        )

    def test_paraphrase_is_not_temporal_change(self):
        result = self.engine.reflect([
            "Мне нравится работать ночью.",
            "Обычно мне нравится работать ночью.",
            "Я предпочитаю работать ночью.",
        ])

        temporal = [
            c for c in result.candidates
            if c.metadata.get("method") == "temporal_change"
        ]

        self.assertEqual(len(temporal), 0)

    def test_unrelated_observations_do_not_merge(self):
        result = self.engine.reflect([
            "Мне нравится работать ночью.",
            "Мне нравится гулять утром.",
        ])

        self.assertEqual(
            result.candidates,
            [],
        )

    def test_reflect_records(self):
        class Record:
            def __init__(self, text):
                self.text = text

        records = [
            Record("Мне нравится работать ночью."),
            Record("Я обычно предпочитаю работать ночью."),
        ]

        result = self.engine.reflect_records(records)

        self.assertEqual(
            len(result.candidates),
            1,
        )


    def test_temporal_change_is_detected(self):
        result = self.engine.reflect([
            "Мне нравится работать ночью.",
            "Мне нравится работать ночью.",
            "Теперь мне нравится работать утром.",
        ])

        temporal = [
            c for c in result.candidates
            if c.metadata.get("method") == "temporal_change"
        ]

        self.assertEqual(len(temporal), 1)

        candidate = temporal[0]

        self.assertEqual(
            candidate.metadata["previous"],
            "Мне нравится работать ночью.",
        )

        self.assertEqual(
            candidate.metadata["current"],
            "Теперь мне нравится работать утром.",
        )

        self.assertEqual(
            candidate.status,
            "candidate",
        )

    def test_does_not_write_memory(self):
        result = self.engine.reflect([
            "Мне нравится работать ночью.",
            "Обычно мне нравится работать ночью.",
        ])

        candidate = result.candidates[0]

        self.assertEqual(
            candidate.status,
            "candidate",
        )

        self.assertEqual(
            candidate.source,
            "reflection",
        )

    def test_status(self):
        status = self.engine.status()

        self.assertEqual(
            status["version"],
            "REFLECTION/1",
        )

        self.assertFalse(
            status["writes_memory"]
        )


    def test_temporal_trajectory_three_states(self):
        result = self.engine.reflect([
            "Мне нравится работать ночью.",
            "Мне нравится работать ночью.",
            "Теперь мне нравится работать утром.",
            "Мне нравится работать утром.",
            "Теперь мне нравится работать вечером.",
            "Мне нравится работать вечером.",
        ])

        trajectories = [
            c for c in result.candidates
            if c.metadata.get("method") == "temporal_trajectory"
        ]

        self.assertEqual(len(trajectories), 1)

        candidate = trajectories[0]

        self.assertEqual(candidate.metadata["state_count"], 3)
        self.assertEqual(candidate.metadata["transition_count"], 2)
        self.assertEqual(
            candidate.metadata["states"],
            [
                "ночью нравится работать",
                "нравится работать утром",
                "вечером нравится работать",
            ],
        )
        self.assertEqual(len(candidate.evidence), 6)

    def test_temporal_trajectory_detects_return(self):
        result = self.engine.reflect([
            "Мне нравится работать ночью.",
            "Мне нравится работать ночью.",
            "Теперь мне нравится работать утром.",
            "Мне нравится работать утром.",
            "Теперь мне нравится работать ночью.",
            "Мне нравится работать ночью.",
        ])

        trajectories = [
            c for c in result.candidates
            if c.metadata.get("method") == "temporal_trajectory"
        ]

        self.assertEqual(len(trajectories), 1)

        candidate = trajectories[0]

        self.assertEqual(candidate.metadata["state_count"], 3)
        self.assertEqual(candidate.metadata["transition_count"], 2)
        self.assertEqual(
            candidate.metadata["states"],
            [
                "ночью нравится работать",
                "нравится работать утром",
                "ночью нравится работать",
            ],
        )

    def test_temporal_trajectory_requires_state_change(self):
        result = self.engine.reflect([
            "Мне нравится работать ночью.",
            "Обычно мне нравится работать ночью.",
            "Я предпочитаю работать ночью.",
            "Мне удобнее работать ночью.",
        ])

        trajectories = [
            c for c in result.candidates
            if c.metadata.get("method") == "temporal_trajectory"
        ]

        self.assertEqual(len(trajectories), 0)


if __name__ == "__main__":
    unittest.main()
