from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math


@dataclass
class DecayResult:
    item_id: str
    previous_activation: float
    activation: float
    priority: float
    age_seconds: float


class MemoryDecay:
    """
    Safe first-stage memory decay.

    It changes relevance/activation scores only.
    It NEVER deletes memory records.
    """

    VERSION = "DECAY/1"

    def __init__(
        self,
        half_life_seconds: float = 86400.0,
        minimum_priority: float = 0.0,
    ):
        self.half_life_seconds = max(
            1.0,
            float(half_life_seconds),
        )
        self.minimum_priority = max(
            0.0,
            min(float(minimum_priority), 1.0),
        )

    def score(
        self,
        *,
        importance: float = 0.5,
        activation: float = 1.0,
        age_seconds: float = 0.0,
        recall_count: int = 0,
    ) -> float:
        importance = max(
            0.0,
            min(float(importance), 1.0),
        )

        activation = max(
            0.0,
            min(float(activation), 1.0),
        )

        age_seconds = max(
            0.0,
            float(age_seconds),
        )

        recall_count = max(
            0,
            int(recall_count),
        )

        decay = math.exp(
            -math.log(2)
            * age_seconds
            / self.half_life_seconds
        )

        recall_bonus = min(
            0.20,
            recall_count * 0.02,
        )

        priority = (
            0.45 * importance
            + 0.35 * activation
            + 0.20 * decay
            + recall_bonus
        )

        return max(
            self.minimum_priority,
            min(priority, 1.0),
        )

    def apply(
        self,
        item_id: str,
        *,
        activation: float = 1.0,
        importance: float = 0.5,
        age_seconds: float = 0.0,
        recall_count: int = 0,
    ) -> DecayResult:
        previous = max(
            0.0,
            min(float(activation), 1.0),
        )

        decay_factor = math.exp(
            -math.log(2)
            * max(0.0, float(age_seconds))
            / self.half_life_seconds
        )

        new_activation = previous * decay_factor

        priority = self.score(
            importance=importance,
            activation=new_activation,
            age_seconds=age_seconds,
            recall_count=recall_count,
        )

        return DecayResult(
            item_id=str(item_id),
            previous_activation=previous,
            activation=new_activation,
            priority=priority,
            age_seconds=max(
                0.0,
                float(age_seconds),
            ),
        )

    def rank(
        self,
        items: list[dict[str, Any]],
    ) -> list[DecayResult]:
        results = []

        for item in items:
            results.append(
                self.apply(
                    str(item.get("item_id", "")),
                    activation=item.get(
                        "activation",
                        1.0,
                    ),
                    importance=item.get(
                        "importance",
                        0.5,
                    ),
                    age_seconds=item.get(
                        "age_seconds",
                        0.0,
                    ),
                    recall_count=item.get(
                        "recall_count",
                        0,
                    ),
                )
            )

        results.sort(
            key=lambda result: (
                -result.priority,
                result.item_id,
            )
        )

        return results

    def status(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "half_life_seconds": (
                self.half_life_seconds
            ),
            "minimum_priority": (
                self.minimum_priority
            ),
            "deletes_memory": False,
        }
