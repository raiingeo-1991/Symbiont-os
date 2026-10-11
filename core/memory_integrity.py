from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional


class MemoryIntegrityError(Exception):
    """Ошибка целостности MemoryVault."""


class MemoryIntegrity:
    """
    Read-only integrity layer for MemoryVault.

    MemoryVault remains the source of truth.
    This layer stores only record fingerprints in a separate manifest.
    """

    VERSION = "MEMORY-INTEGRITY/1"

    def __init__(self, vault, manifest_path):
        self.vault = vault
        self.manifest_path = Path(manifest_path)

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def _digest(cls, value: Any) -> str:
        return hashlib.sha256(
            cls._canonical(value).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _record_payload(record) -> Dict[str, Any]:
        """
        Fields that define the actual MemoryVault record.

        recall_count and last_recall are included intentionally:
        changing them is still a mutation of the stored record.
        """
        return {
            "memory_id": record.memory_id,
            "text": record.text,
            "kind": record.kind,
            "importance": record.importance,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "source": record.source,
            "project": record.project,
            "tags": list(record.tags),
            "metadata": dict(record.metadata),
            "recall_count": int(record.recall_count),
            "last_recall": record.last_recall,
        }

    def fingerprint(self, record) -> str:
        return self._digest(self._record_payload(record))

    def snapshot(self) -> Dict[str, Any]:
        """
        Build a complete integrity manifest from current MemoryVault state.

        Does not modify MemoryVault.
        """
        records = self.vault.all_memories()

        entries = {}
        for record in records:
            entries[record.memory_id] = self.fingerprint(record)

        return {
            "version": self.VERSION,
            "memory_count": len(entries),
            "records": dict(sorted(entries.items())),
        }

    def save_snapshot(self) -> Dict[str, Any]:
        manifest = self.snapshot()

        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_suffix(
            self.manifest_path.suffix + ".tmp"
        )

        temporary.write_text(
            self._canonical(manifest),
            encoding="utf-8",
        )

        temporary.replace(self.manifest_path)
        return manifest

    def load_snapshot(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            raise MemoryIntegrityError(
                "Memory Integrity manifest отсутствует"
            )

        try:
            data = json.loads(
                self.manifest_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise MemoryIntegrityError(
                f"Не удалось прочитать manifest: {exc}"
            ) from exc

        if data.get("version") != self.VERSION:
            raise MemoryIntegrityError(
                "Неподдерживаемая версия Memory Integrity manifest"
            )

        if not isinstance(data.get("records"), dict):
            raise MemoryIntegrityError(
                "Повреждён формат Memory Integrity manifest"
            )

        return data

    def verify(self) -> Dict[str, Any]:
        """
        Compare current MemoryVault against the persisted manifest.

        Read-only: MemoryVault and manifest are not modified.
        """
        expected = self.load_snapshot()
        current = self.snapshot()

        expected_records = expected["records"]
        current_records = current["records"]

        expected_ids = set(expected_records)
        current_ids = set(current_records)

        added = sorted(current_ids - expected_ids)
        removed = sorted(expected_ids - current_ids)

        changed = sorted(
            memory_id
            for memory_id in expected_ids & current_ids
            if expected_records[memory_id] != current_records[memory_id]
        )

        valid = not added and not removed and not changed

        return {
            "valid": valid,
            "expected_count": len(expected_records),
            "current_count": len(current_records),
            "added": added,
            "removed": removed,
            "changed": changed,
            "version": self.VERSION,
        }

    def assert_valid(self) -> Dict[str, Any]:
        result = self.verify()

        if not result["valid"]:
            raise MemoryIntegrityError(
                "MemoryVault integrity check failed: "
                + json.dumps(
                    result,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )

        return result
