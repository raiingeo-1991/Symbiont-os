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
    # Explicit temporal markers. Temporal detection remains conservative:
    # without a temporal marker, lexical differences are not enough to
    # conclude that the underlying state has changed.
    TEMPORAL_MARKERS = (
        "теперь",
        "сейчас",
        "раньше",
        "прежде",
        "ранее",
    )

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

    def _temporal_trajectory_candidate(
        self,
        clean: list[str],
    ) -> ReflectionCandidate | None:
        """
        Detect a sequence of stable states and their transitions.

        Temporal markers are treated as temporal metadata rather than
        part of the underlying state. Consecutive identical normalized
        states are collapsed into one state.
        """
        if len(clean) < 4:
            return None

        state_groups: list[dict[str, Any]] = []
        current_signature: str | None = None

        for text in clean:
            tokens = self._tokens(text)
            tokens -= set(self.TEMPORAL_MARKERS)

            if not tokens:
                continue

            signature = " ".join(sorted(tokens))
            has_temporal_marker = any(
                marker in self._tokens(text)
                for marker in self.TEMPORAL_MARKERS
            )

            if not state_groups:
                state_groups.append({
                    "signature": signature,
                    "evidence": [text],
                })
                current_signature = signature
                continue

            # A trajectory state changes only when the observation
            # explicitly anchors the change in time. Plain paraphrases
            # are treated as additional evidence for the current state.
            if has_temporal_marker and signature != current_signature:
                state_groups.append({
                    "signature": signature,
                    "evidence": [text],
                })
                current_signature = signature
            else:
                # Repeated observation confirms the current state.
                # It is evidence, not a new state or transition.
                state_groups[-1]["evidence"].append(text)

        if len(state_groups) < 2:
            return None

        states = [group["signature"] for group in state_groups]
        transitions = []

        for previous, current in zip(states, states[1:]):
            transitions.append({
                "from": previous,
                "to": current,
                "similarity": self._similarity(previous, current),
            })

        return ReflectionCandidate(
            content=clean[-1],
            confidence=0.65,
            evidence=list(clean),
            source="reflection",
            status="candidate",
            metadata={
                "observations": len(clean),
                "method": "temporal_trajectory",
                "state_count": len(states),
                "transition_count": len(transitions),
                "states": states,
                "transitions": transitions,
            },
        )

    def _temporal_change_candidate(
        self,
        clean: list[str],
    ) -> ReflectionCandidate | None:
        """
        Detect a simple temporal state change.

        This is intentionally conservative: a previous state must
        have appeared at least twice before a different current state
        is treated as a temporal change.
        """
        if len(clean) < 3:
            return None

        current = clean[-1]
        previous = clean[-2]

        normalized_current = self._normalize(current)
        if not any(
            marker in normalized_current
            for marker in self.TEMPORAL_MARKERS
        ):
            return None

        current_signature = self._signature(current)
        previous_signature = self._signature(previous)

        if not current_signature or not previous_signature:
            return None

        if current_signature == previous_signature:
            return None

        previous_count = sum(
            1
            for text in clean[:-1]
            if self._signature(text) == previous_signature
        )

        if previous_count < 2:
            return None

        similarity = self._similarity(
            current_signature,
            previous_signature,
        )

        if similarity < 0.35:
            return None

        return ReflectionCandidate(
            content=current,
            confidence=0.65,
            evidence=[previous, current],
            source="reflection",
            status="candidate",
            metadata={
                "observations": len(clean),
                "method": "temporal_change",
                "previous": previous,
                "current": current,
                "similarity": similarity,
            },
        )

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

        temporal_trajectory = self._temporal_trajectory_candidate(clean)
        if temporal_trajectory is not None:
            candidates.append(temporal_trajectory)

        temporal_candidate = self._temporal_change_candidate(clean)
        if temporal_candidate is not None:
            candidates.append(temporal_candidate)

        if temporal_trajectory is not None or temporal_candidate is not None:
            groups = []

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
