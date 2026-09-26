from __future__ import annotations

import os
from typing import Any

from .associative_memory import AssociativeMemory
from .memory_vault_adapter import MemoryVaultAdapter
from .experience_graph import ExperienceGraph
from .reflection_engine import ReflectionEngine
from .knowledge_consolidation import KnowledgeConsolidation
from .memory_decay import MemoryDecay


class MemoryV2Runtime:
    """
    Safe orchestration layer for the new memory architecture.

    It does not replace MemoryVault.
    It does not write back to MemoryVault in shadow mode.
    """

    VERSION = "MEMORY-V2/1"

    def __init__(
        self,
        memory_vault: Any,
        enabled: bool | None = None,
        shadow: bool = True,
    ):
        if enabled is None:
            enabled = (
                os.environ.get(
                    "SYMBIONT_MEMORY_V2",
                    "false",
                ).lower()
                in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
            )

        self.enabled = bool(enabled)
        self.shadow = bool(shadow)

        # MemoryVault remains the source of truth.
        # Memory V2 does not replace or delete Core memory.
        self.vault = memory_vault

        self.associative = AssociativeMemory()

        self.adapter = MemoryVaultAdapter(
            memory_vault,
            self.associative,
        )

        self.graph = ExperienceGraph()

        self.reflection = ReflectionEngine()

        self.consolidation = (
            KnowledgeConsolidation()
        )

        self.decay_engine = MemoryDecay()

        self.last_refresh = None
        self.last_reflection = None
        self.last_consolidation = None

    def refresh(self, limit: int | None = None):
        """
        Build the V2 shadow index from existing MemoryVault data.

        No writes are performed against MemoryVault.
        """
        if not self.enabled:
            return {
                "enabled": False,
                "indexed": 0,
                "links": 0,
            }

        result = self.adapter.refresh(
            limit=limit
        )

        self.last_refresh = result

        return {
            "enabled": True,
            "indexed": result["indexed"],
            "links": result["links"],
        }

    def spread(
        self,
        seeds,
        depth=2,
        initial=1.0,
        threshold=0.0,
    ):
        """Proxy spreading activation through AssociativeMemory."""

        associative = getattr(self, "associative", None)

        if associative is None:
            associative = getattr(
                self,
                "associative_memory",
                None,
            )

        if associative is None:
            raise RuntimeError(
                "AssociativeMemory layer is not initialized"
            )

        raw = associative.spread(
            seeds,
            depth=depth,
            initial=initial,
            threshold=threshold,
        )

        # AssociativeMemory may return stable item IDs.
        # Runtime exposes full AssociationItem objects.
        result = []

        for value in raw:
            if isinstance(value, str):
                item = associative.get(value)
                if item is not None:
                    result.append(item)
            else:
                result.append(value)

        return result

    def search(
        self,
        query: str,
        limit: int = 10,
    ):
        if not self.enabled:
            return []

        return self.adapter.search(
            query,
            limit=limit,
        )

    def build_experience_graph(
        self,
        limit: int = 100,
    ) -> int:
        if not self.enabled:
            return 0

        items = self.adapter.associative._items

        count = 0

        for item_id, item in list(
            items.items()
        )[:limit]:
            self.graph.add_node(
                content=item.content,
                node_type=item.metadata.get(
                    "kind",
                    "memory",
                )
                or "memory",
                metadata={
                    "memory_id": item_id,
                    "source": item.metadata.get(
                        "source"
                    ),
                },
                node_id=item_id,
            )

            count += 1

        for item_id in list(items)[:limit]:
            for relation, target in self.adapter.related(
                item_id,
                limit=50,
            ):
                self.graph.add_edge(
                    item_id,
                    target.item_id,
                    relation=relation.relation,
                    weight=relation.strength,
                )

        return count

    def reflect(
        self,
        experiences: list[str],
    ):
        if not self.enabled:
            return None

        result = self.reflection.reflect(
            experiences
        )

        self.last_reflection = result

        return result

    def consolidate(
        self,
        reflection_result,
    ):
        if not self.enabled:
            return None

        if reflection_result is None:
            return None

        result = self.consolidation.consolidate(
            reflection_result.candidates
        )

        self.last_consolidation = result

        return result

    def decay(self):
        """
        Run the decay layer in non-destructive mode.

        This calculates decay scores for the current MemoryVault
        records but does not delete or physically modify memories.
        """
        if not self.enabled:
            return None

        vault = getattr(self, "vault", None)
        if vault is None:
            return {
                "processed": 0,
                "changed": 0,
                "deleted": 0,
            }

        if not hasattr(vault, "all_memories"):
            return {
                "processed": 0,
                "changed": 0,
                "deleted": 0,
            }

        records = vault.all_memories()

        processed = 0
        scored = 0

        for record in records:
            importance = float(
                getattr(record, "importance", 0.0) or 0.0
            )
            activation = float(
                getattr(record, "activation", 0.0) or 0.0
            )
            recall_count = int(
                getattr(record, "recall_count", 0) or 0
            )

            age_seconds = 0.0

            created_at = getattr(record, "created_at", None)
            if created_at is not None:
                try:
                    from datetime import datetime, timezone

                    if isinstance(created_at, str):
                        created = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        )
                    else:
                        created = created_at

                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)

                    age_seconds = max(
                        0.0,
                        (
                            datetime.now(timezone.utc) - created
                        ).total_seconds(),
                    )
                except Exception:
                    age_seconds = 0.0

            self.decay_score(
                importance=importance,
                activation=activation,
                age_seconds=age_seconds,
                recall_count=recall_count,
            )

            processed += 1
            scored += 1

        return {
            "processed": processed,
            "scored": scored,
            "changed": 0,
            "deleted": 0,
            "destructive": False,
        }

    def decay_score(
        self,
        *,
        importance: float,
        activation: float,
        age_seconds: float,
        recall_count: int = 0,
    ):
        if not self.enabled:
            return None

        return self.decay_engine.apply(
            "runtime",
            importance=importance,
            activation=activation,
            age_seconds=age_seconds,
            recall_count=recall_count,
        )

    def status(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "enabled": self.enabled,
            "shadow": self.shadow,
            "writes_memory": False,
            "components": {
                "associative": True,
                "experience_graph": True,
                "reflection": True,
                "consolidation": True,
                "decay": True,
            },
            "last_refresh": self.last_refresh,
            "last_reflection_candidates": (
                len(
                    self.last_reflection.candidates
                )
                if self.last_reflection
                else 0
            ),
            "last_consolidated": (
                len(
                    self.last_consolidation.accepted
                )
                if self.last_consolidation
                else 0
            ),
        }
