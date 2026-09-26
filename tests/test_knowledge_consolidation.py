import unittest

from core.knowledge_consolidation import (
    KnowledgeCandidate,
    KnowledgeConsolidation,
)
from core.reflection_engine import (
    ReflectionEngine,
)


class KnowledgeConsolidationTests(unittest.TestCase):

    def setUp(self):
        self.reflection = ReflectionEngine()
        self.consolidation = KnowledgeConsolidation()

    def test_ingest_reflection_candidate(self):
        result = self.reflection.reflect([
            "Мне нравится работать ночью.",
            "Обычно мне нравится работать ночью.",
        ])

        candidate = result.candidates[0]

        knowledge = self.consolidation.ingest(
            candidate
        )

        self.assertTrue(
            knowledge.candidate_id.startswith(
                "knowledge-"
            )
        )

        self.assertEqual(
            knowledge.content,
            candidate.content,
        )

        self.assertEqual(
            knowledge.source,
            "reflection",
        )

        self.assertEqual(
            knowledge.provenance["evidence_count"],
            2,
        )

    def test_validate_good_candidate(self):
        candidate = KnowledgeCandidate(
            candidate_id="k1",
            content="Владелец любит работать ночью.",
            confidence=0.80,
            evidence=[
                "Мне нравится работать ночью.",
                "Обычно мне нравится работать ночью.",
            ],
        )

        self.assertTrue(
            self.consolidation.validate(
                candidate
            )
        )

    def test_reject_low_confidence(self):
        candidate = KnowledgeCandidate(
            candidate_id="k2",
            content="Владелец любит работать ночью.",
            confidence=0.40,
            evidence=[
                "Мне нравится работать ночью.",
                "Обычно мне нравится работать ночью.",
            ],
        )

        self.assertFalse(
            self.consolidation.validate(
                candidate
            )
        )

    def test_reject_insufficient_evidence(self):
        candidate = KnowledgeCandidate(
            candidate_id="k3",
            content="Владелец любит работать ночью.",
            confidence=0.90,
            evidence=[
                "Мне нравится работать ночью.",
            ],
        )

        self.assertFalse(
            self.consolidation.validate(
                candidate
            )
        )

    def test_consolidate_accepts_valid_candidate(self):
        candidate = KnowledgeCandidate(
            candidate_id="k4",
            content="Владелец любит работать ночью.",
            confidence=0.80,
            evidence=[
                "Мне нравится работать ночью.",
                "Обычно мне нравится работать ночью.",
            ],
        )

        result = self.consolidation.consolidate([
            candidate
        ])

        self.assertEqual(
            len(result.accepted),
            1,
        )

        self.assertEqual(
            result.accepted[0].status,
            "validated",
        )

        self.assertEqual(
            len(result.rejected),
            0,
        )

    def test_consolidate_rejects_invalid_candidate(self):
        candidate = KnowledgeCandidate(
            candidate_id="k5",
            content="Владелец любит работать ночью.",
            confidence=0.40,
            evidence=[
                "Мне нравится работать ночью.",
            ],
        )

        result = self.consolidation.consolidate([
            candidate
        ])

        self.assertEqual(
            len(result.accepted),
            0,
        )

        self.assertEqual(
            len(result.rejected),
            1,
        )

        self.assertEqual(
            result.rejected[0].status,
            "rejected",
        )

    def test_candidate_id_is_deterministic(self):
        first = KnowledgeCandidate(
            candidate_id="ignored",
            content="Владелец любит работать ночью.",
            confidence=0.80,
            evidence=[
                "Мне нравится работать ночью.",
                "Обычно мне нравится работать ночью.",
            ],
        )

        second = KnowledgeCandidate(
            candidate_id="different",
            content="Владелец любит работать ночью.",
            confidence=0.80,
            evidence=[
                "Мне нравится работать ночью.",
                "Обычно мне нравится работать ночью.",
            ],
        )

        a = self.consolidation.ingest(first)
        b = self.consolidation.ingest(second)

        self.assertEqual(
            a.candidate_id,
            b.candidate_id,
        )

    def test_provenance_is_preserved(self):
        candidate = KnowledgeCandidate(
            candidate_id="k6",
            content="Владелец любит работать ночью.",
            confidence=0.80,
            evidence=[
                "Мне нравится работать ночью.",
                "Обычно мне нравится работать ночью.",
            ],
            source="reflection",
        )

        knowledge = self.consolidation.ingest(
            candidate
        )

        self.assertEqual(
            knowledge.provenance["source"],
            "reflection",
        )

        self.assertEqual(
            knowledge.provenance["evidence"],
            candidate.evidence,
        )

    def test_does_not_write_memory(self):
        status = self.consolidation.status()

        self.assertFalse(
            status["writes_memory"]
        )


if __name__ == "__main__":
    unittest.main()
