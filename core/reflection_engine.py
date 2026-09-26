from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re


@dataclass
class ReflectionCandidate:
    content: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    source: str = "reflection"
    status: str = "candidate"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReflectionResult:
    candidates: list[ReflectionCandidate]
    observations: int
    version: str = "REFLECTION/1"


class ReflectionEngine:
    """
    Standalone reflection layer.

    Analyzes supplied experiences and produces knowledge candidates.
    It does NOT write to MemoryVault and does NOT import symbiont_core.
    """

    VERSION = "REFLECTION/1"

    PATTERN_MARKERS = (
        "люблю",
        "нравится",
        "предпочитаю",
        "предпочитает",
        "удобнее",
        "обычно",
        "часто",
        "всегда",
        "никогда",
        "не люблю",
        "не нравится",
    )

    # Words carrying little information for pattern comparison.
    STOP_WORDS = {
        "я",
        "мне",
        "мой",
        "моя",
        "мои",
        "мое",
        "владелец",
        "это",
        "так",
        "очень",
        "обычно",
        "часто",
        "всегда",
        "никогда",
        "когда",
    }

    def __init__(
        self,
        minimum_observations: int = 2,
        minimum_confidence: float = 0.65,
    ):
        self.minimum_observations = max(
            1,
            int(minimum_observations),
        )
        self.minimum_confidence = max(
            0.0,
            min(float(minimum_confidence), 1.0),
        )

    @staticmethod
    def _normalize(text: str) -> str:
        text = (text or "").strip().lower()
        text = re.sub(r"\s+", " ", text)
        return text

    @classmethod
    def _is_pattern(cls, text: str) -> bool:
        normalized = cls._normalize(text)

        return any(
            marker in normalized
            for marker in cls.PATTERN_MARKERS
        )

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        normalized = cls._normalize(text)

        tokens = re.findall(
            r"[а-яёa-z0-9]+",
            normalized,
        )

        return {
            token
            for token in tokens
            if token not in cls.STOP_WORDS
            and len(token) > 1
        }

    @classmethod
    def _signature(cls, text: str) -> str:
        tokens = cls._tokens(text)

        return " ".join(sorted(tokens))

    @classmethod
    def _similarity(cls, a: str, b: str) -> float:
        a_tokens = set(a.split())
        b_tokens = set(b.split())

        if not a_tokens or not b_tokens:
            return 0.0

        union = a_tokens | b_tokens

        if not union:
            return 0.0

        return len(a_tokens & b_tokens) / len(union)

    def reflect(
        self,
        experiences: list[str],
    ) -> ReflectionResult:

        clean = [
            text.strip()
            for text in experiences
            if isinstance(text, str)
            and text.strip()
        ]

        if not clean:
            return ReflectionResult(
                candidates=[],
                observations=0,
                version=self.VERSION,
            )

        pattern_experiences = [
            text
            for text in clean
            if self._is_pattern(text)
        ]

        groups: list[list[str]] = []

        for text in pattern_experiences:
            signature = self._signature(text)

            placed = False

            for group in groups:
                group_signature = self._signature(
                    group[0]
                )

                similarity = self._similarity(
                    signature,
                    group_signature,
                )

                # Moderate threshold after proper token
                # normalization. This allows different wording
                # of the same underlying pattern.
                if similarity >= 0.35:
                    group.append(text)
                    placed = True
                    break

            if not placed:
                groups.append([text])

        candidates = []

        for group in groups:
            observations = len(group)

            if observations < self.minimum_observations:
                continue

            confidence = min(
                0.50 + 0.18 * (observations - 1),
                0.98,
            )

            if confidence < self.minimum_confidence:
                continue

            representative = group[-1]

            candidates.append(
                ReflectionCandidate(
                    content=representative,
                    confidence=confidence,
                    evidence=list(group),
                    source="reflection",
                    status="candidate",
                    metadata={
                        "observations": observations,
                        "method": "repeated_pattern",
                    },
                )
            )

        return ReflectionResult(
            candidates=candidates,
            observations=len(clean),
            version=self.VERSION,
        )

    def reflect_records(
        self,
        records: list[Any],
    ) -> ReflectionResult:

        texts = []

        for record in records:
            if isinstance(record, str):
                texts.append(record)
                continue

            text = getattr(record, "content", None)

            if text is None:
                text = getattr(record, "text", None)

            if text:
                texts.append(str(text))

        return self.reflect(texts)

    def status(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "minimum_observations": self.minimum_observations,
            "minimum_confidence": self.minimum_confidence,
            "writes_memory": False,
        }
