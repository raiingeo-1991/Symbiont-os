import json
import sqlite3

import pytest

from core.sss.sis_anchor_ledger import AnchorLedger, IntegrityError, ZERO_HASH


def make_ledger(root):
    return AnchorLedger(
        root / "anchors.sqlite3",
        root / "checkpoint.json",
        root / "anchor.key",
    )


def test_empty_ledger_is_valid(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        assert ledger.verify() == (True, 0)
    finally:
        ledger.close()


def test_append_builds_valid_chain_and_survives_restart(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        first_hash = ledger.append("event-1", "first evidence")
        second_hash = ledger.append("event-2", "second evidence")

        assert first_hash != second_hash
        assert ledger.verify() == (True, 2)
    finally:
        ledger.close()

    reopened = make_ledger(tmp_path)
    try:
        assert reopened.verify() == (True, 2)
    finally:
        reopened.close()


def test_duplicate_delivery_is_idempotent(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        first = ledger.append("event-1", "evidence")
        second = ledger.append("event-1", "evidence")

        assert first == second
        assert ledger.verify() == (True, 1)
    finally:
        ledger.close()


def test_conflicting_duplicate_is_rejected(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        ledger.append("event-1", "original")
        with pytest.raises(ValueError, match="Conflicting event redelivery"):
            ledger.append("event-1", "changed")
        assert ledger.verify() == (True, 1)
    finally:
        ledger.close()


def test_tampered_database_record_is_detected(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.append("event-1", "original")
    ledger.close()

    db = sqlite3.connect(tmp_path / "anchors.sqlite3")
    try:
        db.execute(
            "UPDATE evidence SET summary = ? WHERE event_id = ?",
            ("tampered", "event-1"),
        )
        db.commit()
    finally:
        db.close()

    with pytest.raises(IntegrityError):
        make_ledger(tmp_path)


def test_tampered_checkpoint_is_detected(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.append("event-1", "evidence")
    ledger.close()

    path = tmp_path / "checkpoint.json"
    document = json.loads(path.read_text("utf-8"))
    document["sequence"] = 0
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(IntegrityError):
        make_ledger(tmp_path)


def test_missing_key_refuses_reinitialization(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.close()
    (tmp_path / "anchor.key").unlink()

    with pytest.raises(IntegrityError, match="Incomplete ledger state"):
        make_ledger(tmp_path)


def test_corrupted_ledger_refuses_new_evidence(tmp_path):
    ledger = make_ledger(tmp_path)
    ledger.append("event-1", "original")

    ledger.db.execute(
        "UPDATE evidence SET summary = ? WHERE event_id = ?",
        ("tampered", "event-1"),
    )
    ledger.db.commit()

    with pytest.raises(IntegrityError):
        ledger.append("event-2", "later evidence")

    ledger.close()


def test_initial_checkpoint_uses_zero_hash(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        checkpoint = ledger._read_checkpoint()
        assert checkpoint["sequence"] == 0
        assert checkpoint["last_hash"] == ZERO_HASH
    finally:
        ledger.close()


def test_checkpoint_write_failure_leaves_ledger_untrusted(
    tmp_path, monkeypatch
):
    ledger = make_ledger(tmp_path)
    original_write = ledger._write_checkpoint

    def fail_checkpoint(sequence, last_hash):
        raise OSError("simulated checkpoint write failure")

    monkeypatch.setattr(ledger, "_write_checkpoint", fail_checkpoint)

    with pytest.raises(OSError, match="simulated checkpoint write failure"):
        ledger.append("event-1", "evidence")

    monkeypatch.setattr(ledger, "_write_checkpoint", original_write)

    # The database commit happened, but the old checkpoint must not be trusted.
    assert ledger.verify() == (False, 1)
    ledger.close()

    with pytest.raises(IntegrityError):
        make_ledger(tmp_path)


def test_concurrent_appends_preserve_chain(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    ledger = make_ledger(tmp_path)
    try:
        def append_one(index):
            return ledger.append(f"event-{index}", f"evidence-{index}")

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(append_one, range(12)))

        assert len(set(results)) == 12
        assert ledger.verify() == (True, 12)
    finally:
        ledger.close()
