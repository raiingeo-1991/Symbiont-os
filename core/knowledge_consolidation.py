from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import hashlib
import time


@dataclass
class KnowledgeCandidate:
    candidate_id: str
    content: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    source: str = "reflection"
    status: str = "pending"
    provenance: dict[str, Any] = field(default_factory=dict)
    version: str = "KNOWLEDGE/1"


@dataclass
class ConsolidationResult:
    accepted: list[KnowledgeCandidate]
    rejected: list[KnowledgeCandidate]
    version: str = "CONSOLIDATION/1"


class KnowledgeConsolidation:
    """
    Converts reflection candidates into validated knowledge candidates.

    This module does NOT write to MemoryVault.
    It preserves provenance and leaves final persistence to the
    existing Symbiont learning/consistency pipeline.
    """

    VERSION = "CONSOLIDATION/1"

    def __init__(
        self,
        minimum_confidence: float = 0.65,
        minimum_evidence: int = 2,
    ):
        self.minimum_confidence = max(
            0.0,
            min(float(minimum_confidence), 1.0),
        )
        self.minimum_evidence = max(
            1,
            int(minimum_evidence),
        )

    @staticmethod
    def _candidate_id(
        content: str,
        evidence: list[str],
    ) -> str:
        payload = (
            content.strip()
            + "\n"
            + "\n".join(
                sorted(
                    value.strip()
                    for value in evidence
                )
            )
        )

        digest = hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

        return f"knowledge-{digest[:16]}"

    def ingest(
        self,
        candidate: Any,
    ) -> KnowledgeCandidate:
        content = str(
            getattr(candidate, "content", "")
        ).strip()

        if not content:
            raise ValueError(
                "candidate content must not be empty"
            )

        confidence = float(
            getattr(candidate, "confidence", 0.0)
        )

        evidence = list(
            getattr(candidate, "evidence", [])
            or []
        )

        source = str(
            getattr(candidate, "source", "reflection")
        )

        candidate_id = self._candidate_id(
            content,
            evidence,
        )

        provenance = {
            "source": source,
            "evidence_count": len(evidence),
            "evidence": list(evidence),
            "created_at": time.time(),
            "engine_version": self.VERSION,
        }

        return KnowledgeCandidate(
            candidate_id=candidate_id,
            content=content,
            confidence=confidence,
            evidence=evidence,
            source=source,
            status="pending",
            provenance=provenance,
        )

    def validate(
        self,
        candidate: KnowledgeCandidate,
    ) -> bool:
        if not candidate.content.strip():
            return False

        if candidate.confidence < self.minimum_confidence:
            return False

        if len(candidate.evidence) < self.minimum_evidence:
            return False

        return True

    def consolidate(
        self,
        candidates: list[Any],
    ) -> ConsolidationResult:
        accepted = []
        rejected = []

        for candidate in candidates:
            knowledge = (
                candidate
                if isinstance(
                    candidate,
                    KnowledgeCandidate,
                )
                else self.ingest(candidate)
            )

            if self.validate(knowledge):
                knowledge.status = "validated"
                accepted.append(knowledge)
            else:
                knowledge.status = "rejected"
                rejected.append(knowledge)

        return ConsolidationResult(
            accepted=accepted,
            rejected=rejected,
            version=self.VERSION,
        )

    def status(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "minimum_confidence": (
                self.minimum_confidence
            ),
            "minimum_evidence": (
                self.minimum_evidence
            ),
            "writes_memory": False,
        }
