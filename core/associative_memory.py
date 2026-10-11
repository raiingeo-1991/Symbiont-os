from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any
import math
import re


@dataclass
class AssociationItem:
    item_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    activation: float = 0.0


@dataclass
class Association:
    source: str
    target: str
    relation: str
    strength: float = 1.0


class AssociativeMemory:
    """
    Standalone associative-memory layer.

    This module does NOT own persistent storage and does NOT import
    symbiont_core. A persistent backend can be connected later through
    an adapter.
    """

    VERSION = "ASSOC/1"

    def __init__(self, capacity: int | None = None):
        self.capacity = capacity
        self._items: dict[str, AssociationItem] = {}
        self._relations: dict[tuple[str, str, str], Association] = {}
        self._lock = RLock()
        self._counter = 0

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9_]+", text or "")
            if len(token) > 1
        }

    def _new_id(self) -> str:
        self._counter += 1
        return f"assoc-{self._counter}"

    def add(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        item_id: str | None = None,
    ) -> str:
        with self._lock:
            if not content or not content.strip():
                raise ValueError("content must not be empty")

            item_id = item_id or self._new_id()

            if item_id in self._items:
                existing = self._items[item_id]
                existing.content = content
                if metadata:
                    existing.metadata.update(metadata)
                return item_id

            if self.capacity is not None and len(self._items) >= self.capacity:
                raise MemoryError("AssociativeMemory capacity reached")

            self._items[item_id] = AssociationItem(
                item_id=item_id,
                content=content.strip(),
                metadata=dict(metadata or {}),
            )
            return item_id

    def get(self, item_id: str) -> AssociationItem | None:
        with self._lock:
            return self._items.get(item_id)

    def search(self, query: str, limit: int = 10) -> list[AssociationItem]:
        if not query or limit <= 0:
            return []

        query_tokens = self._tokens(query)

        with self._lock:
            scored = []

            for item in self._items.values():
                text_tokens = self._tokens(item.content)

                if not text_tokens:
                    continue

                intersection = query_tokens & text_tokens
                union = query_tokens | text_tokens

                similarity = (
                    len(intersection) / len(union)
                    if union
                    else 0.0
                )

                substring_bonus = (
                    0.15
                    if query.lower() in item.content.lower()
                    else 0.0
                )

                score = similarity + substring_bonus
                score += min(max(item.activation, 0.0), 1.0) * 0.10

                if score > 0:
                    scored.append((score, item))

            scored.sort(
                key=lambda pair: (-pair[0], pair[1].item_id)
            )

            return [item for _, item in scored[:limit]]

    def relate(
        self,
        source: str,
        target: str,
        relation: str = "related",
        strength: float = 1.0,
    ) -> bool:
        with self._lock:
            if source not in self._items or target not in self._items:
                return False

            strength = max(0.0, min(float(strength), 1.0))

            key = (source, target, relation)
            existing = self._relations.get(key)

            if existing:
                existing.strength = max(existing.strength, strength)
            else:
                self._relations[key] = Association(
                    source=source,
                    target=target,
                    relation=relation,
                    strength=strength,
                )

            return True

    def related(
        self,
        item_id: str,
        relation: str | None = None,
        limit: int = 20,
    ) -> list[tuple[Association, AssociationItem]]:
        with self._lock:
            results = []

            for association in self._relations.values():
                if association.source != item_id:
                    continue

                if relation is not None and association.relation != relation:
                    continue

                target = self._items.get(association.target)
                if target is not None:
                    results.append((association, target))

            results.sort(
                key=lambda pair: (
                    -pair[0].strength,
                    pair[1].item_id,
                )
            )

            return results[:limit]

    def activate(
        self,
        item_ids: list[str] | tuple[str, ...] | set[str],
        amount: float = 1.0,
    ) -> int:
        amount = max(0.0, float(amount))
        count = 0

        with self._lock:
            for item_id in item_ids:
                item = self._items.get(item_id)

                if item is None:
                    continue

                item.activation += amount
                count += 1

        return count

    def decay(self, amount: float = 0.1) -> int:
        amount = max(0.0, float(amount))
        count = 0

        with self._lock:
            for item in self._items.values():
                old = item.activation
                item.activation = max(0.0, item.activation - amount)

                if item.activation != old:
                    count += 1

        return count

    def spread(
        self,
        seeds: list[str] | tuple[str, ...] | set[str],
        depth: int = 2,
        initial: float = 1.0,
        threshold: float = 0.05,
    ) -> dict[str, float]:
        depth = max(0, int(depth))
        initial = max(0.0, float(initial))
        threshold = max(0.0, float(threshold))

        with self._lock:
            activation: dict[str, float] = {}

            frontier = {
                item_id: initial
                for item_id in seeds
                if item_id in self._items
            }

            for item_id, value in frontier.items():
                activation[item_id] = max(
                    activation.get(item_id, 0.0),
                    value,
                )

            for _ in range(depth):
                next_frontier: dict[str, float] = {}

                for source, value in frontier.items():
                    for association in self._relations.values():
                        if association.source != source:
                            continue

                        propagated = value * association.strength

                        if propagated < threshold:
                            continue

                        target = association.target

                        if propagated > activation.get(target, 0.0):
                            activation[target] = propagated

                        if propagated > next_frontier.get(target, 0.0):
                            next_frontier[target] = propagated

                frontier = next_frontier

                if not frontier:
                    break

            for item_id, value in activation.items():
                item = self._items.get(item_id)
                if item:
                    item.activation = max(item.activation, value)

            return dict(
                sorted(
                    activation.items(),
                    key=lambda pair: (-pair[1], pair[0]),
                )
            )

    def dedup(self, similarity_threshold: float = 0.85) -> list[tuple[str, str]]:
        similarity_threshold = max(
            0.0,
            min(float(similarity_threshold), 1.0),
        )

        with self._lock:
            items = list(self._items.values())
            duplicates = []

            for index, first in enumerate(items):
                first_tokens = self._tokens(first.content)

                for second in items[index + 1:]:
                    second_tokens = self._tokens(second.content)

                    union = first_tokens | second_tokens

                    if not union:
                        continue

                    similarity = len(
                        first_tokens & second_tokens
                    ) / len(union)

                    if similarity >= similarity_threshold:
                        duplicates.append(
                            (first.item_id, second.item_id)
                        )

            return duplicates

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "version": self.VERSION,
                "items": len(self._items),
                "relations": len(self._relations),
                "capacity": self.capacity,
            }
