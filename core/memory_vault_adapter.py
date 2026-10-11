from __future__ import annotations

from typing import Any

from .associative_memory import AssociativeMemory


class MemoryVaultAdapter:
    """
    Bridge between the existing Symbiont MemoryVault
    and the standalone AssociativeMemory layer.

    MemoryVault remains the persistent source of truth.
    AssociativeMemory is only an associative index.
    """

    VERSION = "ADAPTER/1"

    def __init__(
        self,
        memory_vault: Any,
        associative: AssociativeMemory | None = None,
    ):
        self.memory_vault = memory_vault
        self.associative = associative or AssociativeMemory()

    @staticmethod
    def _record_id(record: Any) -> str | None:
        value = getattr(
            record,
            "memory_id",
            None,
        )

        if value is None:
            value = getattr(
                record,
                "id",
                None,
            )

        return (
            str(value)
            if value is not None
            else None
        )

    @staticmethod
    def _record_text(record: Any) -> str:
        value = getattr(
            record,
            "text",
            None,
        )

        if value is None:
            value = getattr(
                record,
                "content",
                "",
            )

        return str(value or "")

    @classmethod
    def _metadata(cls, record: Any) -> dict[str, Any]:
        return {
            "memory_id": cls._record_id(record),
            "kind": getattr(record, "kind", None),
            "importance": getattr(
                record,
                "importance",
                None,
            ),
            "created_at": getattr(
                record,
                "created_at",
                None,
            ),
            "updated_at": getattr(
                record,
                "updated_at",
                None,
            ),
            "source": getattr(
                record,
                "source",
                None,
            ),
            "project": getattr(
                record,
                "project",
                None,
            ),
            "tags": getattr(
                record,
                "tags",
                None,
            ),
            "metadata": getattr(
                record,
                "metadata",
                None,
            ),
            "recall_count": getattr(
                record,
                "recall_count",
                0,
            ),
        }

    def index_record(self, record: Any) -> str:
        memory_id = self._record_id(record)

        if memory_id is None:
            raise ValueError(
                "MemoryVault record must have memory_id or id"
            )

        return self.associative.add(
            content=self._record_text(record),
            metadata=self._metadata(record),
            item_id=memory_id,
        )

    def _records(self, limit: int | None = None):
        if hasattr(self.memory_vault, "all_memories"):
            if limit is None:
                return self.memory_vault.all_memories(limit=None)

            return self.memory_vault.all_memories(
                limit=max(1, int(limit))
            )

        if hasattr(self.memory_vault, "all"):
            records = self.memory_vault.all()

            if limit is None:
                return records

            return records[:max(1, int(limit))]

        raise AttributeError(
            "MemoryVault must expose all_memories() or all()"
        )


    def index_all(
        self,
        limit: int | None = None,
    ) -> int:
        records = self._records(limit)

        count = 0

        for record in records:
            self.index_record(record)
            count += 1

        return count

    def _links_for(
        self,
        memory_id: str,
    ):
        if hasattr(
            self.memory_vault,
            "links_of",
        ):
            return self.memory_vault.links_of(
                memory_id
            )

        if hasattr(
            self.memory_vault,
            "links",
        ):
            return self.memory_vault.links(
                limit=None
            )

        return []

    def index_links(
        self,
        limit: int | None = None,
    ) -> int:
        """
        Import links from the real MemoryVault.

        The current MemoryVault exposes links_of(memory_id),
        so we walk indexed memories and deduplicate links.
        """
        records = self._records(limit)

        seen = set()
        count = 0

        for record in records:
            memory_id = self._record_id(record)

            if memory_id is None:
                continue

            for link in self._links_for(
                memory_id
            ):
                if isinstance(link, dict):
                    source = str(
                        link.get("from_id", "")
                    )
                    target = str(
                        link.get("to_id", "")
                    )
                    relation = str(
                        link.get(
                            "kind",
                            "related",
                        )
                    )
                    strength = float(
                        link.get(
                            "strength",
                            1.0,
                        )
                    )
                else:
                    source = str(
                        getattr(
                            link,
                            "from_id",
                            getattr(
                                link,
                                "source",
                                "",
                            ),
                        )
                    )
                    target = str(
                        getattr(
                            link,
                            "to_id",
                            getattr(
                                link,
                                "target",
                                "",
                            ),
                        )
                    )
                    relation = str(
                        getattr(
                            link,
                            "kind",
                            getattr(
                                link,
                                "relation",
                                "related",
                            ),
                        )
                    )
                    strength = float(
                        getattr(
                            link,
                            "strength",
                            1.0,
                        )
                    )

                key = (
                    source,
                    target,
                    relation,
                )

                if key in seen:
                    continue

                seen.add(key)

                if self.associative.relate(
                    source,
                    target,
                    relation,
                    strength,
                ):
                    count += 1

                if (
                    limit is not None
                    and count >= int(limit)
                ):
                    return count

        return count

    def refresh(
        self,
        limit: int | None = None,
    ) -> dict[str, int]:
        indexed = self.index_all(limit)
        links = self.index_links(limit)

        return {
            "indexed": indexed,
            "links": links,
        }

    def search(
        self,
        query: str,
        limit: int = 10,
    ):
        return self.associative.search(
            query,
            limit=limit,
        )

    def related(
        self,
        memory_id: str,
        relation: str | None = None,
        limit: int = 20,
    ):
        return self.associative.related(
            str(memory_id),
            relation=relation,
            limit=limit,
        )

    def activate(
        self,
        memory_ids,
        amount: float = 1.0,
    ) -> int:
        return self.associative.activate(
            [str(value) for value in memory_ids],
            amount,
        )

    def spread(
        self,
        memory_ids,
        depth: int = 2,
        initial: float = 1.0,
        threshold: float = 0.05,
    ):
        return self.associative.spread(
            [str(value) for value in memory_ids],
            depth=depth,
            initial=initial,
            threshold=threshold,
        )

    def status(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "source": type(
                self.memory_vault
            ).__name__,
            "persistent_source_of_truth": True,
            "associative": (
                self.associative.status()
            ),
        }
