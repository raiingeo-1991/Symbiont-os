from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any


@dataclass
class ExperienceNode:
    node_id: str
    node_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperienceEdge:
    source: str
    target: str
    relation: str
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ExperienceGraph:
    """
    Standalone graph of experiences, entities and contexts.

    This module does not replace MemoryVault and does not import
    symbiont_core. It stores only the graph representation.
    """

    VERSION = "EXPERIENCE-GRAPH/1"

    def __init__(self, capacity: int | None = None):
        self.capacity = capacity
        self._nodes: dict[str, ExperienceNode] = {}
        self._edges: dict[tuple[str, str, str], ExperienceEdge] = {}
        self._counter = 0
        self._lock = RLock()

    def _new_id(self) -> str:
        self._counter += 1
        return f"experience-{self._counter}"

    def add_node(
        self,
        content: str,
        node_type: str = "experience",
        metadata: dict[str, Any] | None = None,
        node_id: str | None = None,
    ) -> str:
        if not content or not content.strip():
            raise ValueError("content must not be empty")

        if not node_type or not node_type.strip():
            raise ValueError("node_type must not be empty")

        with self._lock:
            node_id = node_id or self._new_id()

            if node_id in self._nodes:
                node = self._nodes[node_id]
                node.content = content.strip()
                node.node_type = node_type.strip()

                if metadata:
                    node.metadata.update(metadata)

                return node_id

            if (
                self.capacity is not None
                and len(self._nodes) >= self.capacity
            ):
                raise MemoryError(
                    "ExperienceGraph capacity reached"
                )

            self._nodes[node_id] = ExperienceNode(
                node_id=node_id,
                node_type=node_type.strip(),
                content=content.strip(),
                metadata=dict(metadata or {}),
            )

            return node_id

    def get_node(
        self,
        node_id: str,
    ) -> ExperienceNode | None:
        with self._lock:
            return self._nodes.get(node_id)

    def add_edge(
        self,
        source: str,
        target: str,
        relation: str = "related",
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        with self._lock:
            if source not in self._nodes:
                return False

            if target not in self._nodes:
                return False

            if not relation or not relation.strip():
                raise ValueError(
                    "relation must not be empty"
                )

            weight = max(0.0, min(float(weight), 1.0))

            key = (
                source,
                target,
                relation.strip(),
            )

            existing = self._edges.get(key)

            if existing:
                existing.weight = max(
                    existing.weight,
                    weight,
                )

                if metadata:
                    existing.metadata.update(metadata)

            else:
                self._edges[key] = ExperienceEdge(
                    source=source,
                    target=target,
                    relation=relation.strip(),
                    weight=weight,
                    metadata=dict(metadata or {}),
                )

            return True

    def related(
        self,
        node_id: str,
        relation: str | None = None,
        direction: str = "out",
        limit: int = 20,
    ) -> list[tuple[ExperienceEdge, ExperienceNode]]:
        if direction not in {"out", "in", "both"}:
            raise ValueError(
                "direction must be 'out', 'in' or 'both'"
            )

        with self._lock:
            results = []

            for edge in self._edges.values():
                matched = False
                target_id = None

                if direction in {"out", "both"}:
                    if edge.source == node_id:
                        matched = True
                        target_id = edge.target

                if (
                    not matched
                    and direction in {"in", "both"}
                    and edge.target == node_id
                ):
                    matched = True
                    target_id = edge.source

                if not matched:
                    continue

                if (
                    relation is not None
                    and edge.relation != relation
                ):
                    continue

                node = self._nodes.get(target_id)

                if node is not None:
                    results.append((edge, node))

            results.sort(
                key=lambda pair: (
                    -pair[0].weight,
                    pair[1].node_id,
                )
            )

            return results[:limit]

    def read_context(
        self,
        node_id: str,
        depth: int = 1,
        limit: int = 50,
    ) -> list[ExperienceNode]:
        depth = max(0, int(depth))

        with self._lock:
            if node_id not in self._nodes:
                return []

            visited = {node_id}
            frontier = {node_id}
            result = []

            for _ in range(depth):
                next_frontier = set()

                for current in frontier:
                    for edge in self._edges.values():
                        neighbour = None

                        if edge.source == current:
                            neighbour = edge.target
                        elif edge.target == current:
                            neighbour = edge.source

                        if (
                            neighbour is not None
                            and neighbour not in visited
                        ):
                            visited.add(neighbour)
                            next_frontier.add(neighbour)

                            node = self._nodes.get(neighbour)

                            if node is not None:
                                result.append(node)

                                if len(result) >= limit:
                                    return result[:limit]

                frontier = next_frontier

                if not frontier:
                    break

            return result[:limit]

    def nodes_by_type(
        self,
        node_type: str,
        limit: int = 50,
    ) -> list[ExperienceNode]:
        with self._lock:
            result = [
                node
                for node in self._nodes.values()
                if node.node_type == node_type
            ]

            result.sort(
                key=lambda node: node.node_id
            )

            return result[:limit]

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "version": self.VERSION,
                "nodes": len(self._nodes),
                "edges": len(self._edges),
                "capacity": self.capacity,
            }
