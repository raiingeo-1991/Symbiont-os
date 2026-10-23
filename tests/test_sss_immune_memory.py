import sqlite3

import pytest

from core.sss.immune_memory import (
    ImmuneMemory,
    ImmuneMemoryIntegrityError,
)


def source_event(event_id="core-event-1", event_type="security.test"):
    return {
        "source_event_id": event_id,
        "source_event_type": event_type,
        "source_event_hash": "a" * 64,
    }


def record(memory, **overrides):
    args = {
        **source_event(),
        "evidence_kind": "fact",
        "summary": "Core registered a security event",
        "incident_id": "incident-1",
        "details": {"source": "test", "private_key": "DO-NOT-STORE"},
    }
    args.update(overrides)
    return memory.record_evidence(**args)


def test_duplicate_delivery_is_idempotent(tmp_path):
    memory = ImmuneMemory(tmp_path / "immune.sqlite3")
    try:
        first = record(memory)
        second = record(memory)
        assert first == second
        assert len(memory.list_evidence()) == 1
        assert memory.verify() == (True, 1)
    finally:
        memory.close()


def test_evidence_survives_restart(tmp_path):
    path = tmp_path / "immune.sqlite3"
    first = ImmuneMemory(path)
    evidence_id = record(first)
    first.close()

    second = ImmuneMemory(path)
    try:
        items = second.list_evidence()
        assert len(items) == 1
        assert items[0]["evidence_id"] == evidence_id
        assert items[0]["source_event_id"] == "core-event-1"
        assert second.verify() == (True, 1)
    finally:
        second.close()


def test_fact_suspicion_and_conclusion_are_distinct(tmp_path):
    memory = ImmuneMemory(tmp_path / "immune.sqlite3")
    try:
        for kind in ("fact", "suspicion", "conclusion"):
            record(
                memory,
                evidence_kind=kind,
                summary=f"Evidence classification: {kind}",
            )
        assert [x["evidence_kind"] for x in memory.list_evidence()] == [
            "fact", "suspicion", "conclusion"
        ]
        assert memory.verify() == (True, 3)
    finally:
        memory.close()


def test_sensitive_detail_keys_are_not_persisted(tmp_path):
    memory = ImmuneMemory(tmp_path / "immune.sqlite3")
    try:
        record(
            memory,
            details={
                "public_context": "test",
                "secret_key": "TOP-SECRET",
                "nested": {"password": "HIDDEN", "status": "ok"},
            },
        )
        item = memory.list_evidence()[0]
        serialized = str(item["details"])
        assert "TOP-SECRET" not in serialized
        assert "HIDDEN" not in serialized
        assert item["details"]["public_context"] == "test"
        assert item["details"]["nested"]["status"] == "ok"
    finally:
        memory.close()


def test_conflicting_redelivery_is_rejected(tmp_path):
    memory = ImmuneMemory(tmp_path / "immune.sqlite3")
    try:
        record(memory)
        with pytest.raises(ValueError, match="Conflicting evidence"):
            record(memory, summary="Contradictory replacement")
        assert len(memory.list_evidence()) == 1
    finally:
        memory.close()


def test_invalid_evidence_kind_is_rejected(tmp_path):
    memory = ImmuneMemory(tmp_path / "immune.sqlite3")
    try:
        with pytest.raises(ValueError, match="Unsupported evidence kind"):
            record(memory, evidence_kind="trusted")
        assert memory.list_evidence() == []
    finally:
        memory.close()


def test_tampering_is_detected_on_reopen(tmp_path):
    path = tmp_path / "immune.sqlite3"
    memory = ImmuneMemory(path)
    record(memory)
    memory.close()

    db = sqlite3.connect(path)
    db.execute(
        "UPDATE immune_evidence SET summary = ? WHERE source_event_id = ?",
        ("modified without updating hash", "core-event-1"),
    )
    db.commit()
    db.close()

    with pytest.raises(ImmuneMemoryIntegrityError):
        ImmuneMemory(path)


def test_corrupted_chain_refuses_new_evidence(tmp_path):
    path = tmp_path / "immune.sqlite3"
    memory = ImmuneMemory(path)
    record(memory)
    memory.db.execute(
        "UPDATE immune_evidence SET summary = ? WHERE source_event_id = ?",
        ("tampered", "core-event-1"),
    )
    memory.db.commit()

    with pytest.raises(ImmuneMemoryIntegrityError):
        record(
            memory,
            source_event_id="core-event-2",
            summary="A later event",
        )
    memory.close()
