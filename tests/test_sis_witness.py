import sqlite3

import pytest

from core.sss.sis_witness import (
    Anchor,
    PersistentWitness,
    WitnessError,
    ZERO_HASH,
)


def h(char):
    return char * 64


def test_missing_store_fails_closed(tmp_path):
    with pytest.raises(WitnessError):
        PersistentWitness(tmp_path / "missing.sqlite3")


def test_explicit_initialization_creates_zero_state(tmp_path):
    path = tmp_path / "witness.sqlite3"
    witness = PersistentWitness.initialize(path)
    try:
        assert witness.current == Anchor(0, ZERO_HASH)
        assert witness.pending is None
    finally:
        witness.close()


def test_existing_store_cannot_be_reinitialized(tmp_path):
    path = tmp_path / "witness.sqlite3"
    witness = PersistentWitness.initialize(path)
    witness.close()

    with pytest.raises(WitnessError, match="already exists"):
        PersistentWitness.initialize(path)


def test_committed_anchor_survives_restart(tmp_path):
    path = tmp_path / "witness.sqlite3"
    witness = PersistentWitness.initialize(path)
    zero = Anchor(0, ZERO_HASH)
    one = Anchor(1, h("a"))

    try:
        assert witness.prepare(zero, one) == "PREPARED"
        assert witness.commit(one) == "COMMITTED"
    finally:
        witness.close()

    witness = PersistentWitness(path)
    try:
        assert witness.current == one
        assert witness.pending is None
    finally:
        witness.close()


def test_pending_operation_survives_restart_and_can_commit(tmp_path):
    path = tmp_path / "witness.sqlite3"
    witness = PersistentWitness.initialize(path)
    zero = Anchor(0, ZERO_HASH)
    one = Anchor(1, h("a"))

    try:
        assert witness.prepare(zero, one) == "PREPARED"
    finally:
        witness.close()

    witness = PersistentWitness(path)
    try:
        assert witness.pending == (zero, one)
        assert witness.prepare(zero, one) == "PREPARE_IDEMPOTENT"
        assert witness.commit(one) == "COMMITTED"
        assert witness.current == one
    finally:
        witness.close()


def test_conflicting_pending_operation_is_rejected(tmp_path):
    witness = PersistentWitness.initialize(tmp_path / "witness.sqlite3")
    zero = Anchor(0, ZERO_HASH)

    try:
        witness.prepare(zero, Anchor(1, h("a")))
        with pytest.raises(WitnessError, match="Conflicting pending"):
            witness.prepare(zero, Anchor(1, h("b")))
        assert witness.current == zero
    finally:
        witness.close()


def test_stale_expected_anchor_is_rejected(tmp_path):
    witness = PersistentWitness.initialize(tmp_path / "witness.sqlite3")
    zero = Anchor(0, ZERO_HASH)

    try:
        witness.prepare(zero, Anchor(1, h("a")))
        witness.commit(Anchor(1, h("a")))

        with pytest.raises(WitnessError, match="Stale"):
            witness.prepare(zero, Anchor(2, h("b")))
    finally:
        witness.close()


@pytest.mark.parametrize(
    "candidate",
    [
        Anchor(2, h("b")),
        Anchor(1, ZERO_HASH),
        Anchor(1, "A" * 64),
        Anchor(True, h("a")),
        Anchor(-1, h("a")),
    ],
)
def test_invalid_candidate_is_rejected_without_state_change(
    tmp_path, candidate
):
    witness = PersistentWitness.initialize(tmp_path / "witness.sqlite3")
    zero = Anchor(0, ZERO_HASH)

    try:
        with pytest.raises(WitnessError):
            witness.prepare(zero, candidate)
        assert witness.current == zero
        assert witness.pending is None
    finally:
        witness.close()


def test_local_rollback_and_fork_are_detected(tmp_path):
    witness = PersistentWitness.initialize(tmp_path / "witness.sqlite3")
    zero = Anchor(0, ZERO_HASH)
    one = Anchor(1, h("a"))

    try:
        witness.prepare(zero, one)
        witness.commit(one)

        assert witness.compare_local(zero) == "LOCAL_BEHIND"
        assert witness.compare_local(Anchor(1, h("b"))) == "FORK_OR_REWRITE"
        assert witness.compare_local(Anchor(2, h("c"))) == (
            "LOCAL_AHEAD_UNCONFIRMED"
        )
        assert witness.compare_local(one) == "MATCH"
    finally:
        witness.close()


def test_empty_existing_file_fails_closed(tmp_path):
    path = tmp_path / "empty.sqlite3"
    path.touch()

    with pytest.raises(WitnessError):
        PersistentWitness(path)


def test_missing_schema_table_fails_closed(tmp_path):
    path = tmp_path / "bad-schema.sqlite3"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE unrelated (value TEXT)")
    db.commit()
    db.close()

    with pytest.raises(WitnessError):
        PersistentWitness(path)


def test_corrupt_state_fails_closed(tmp_path):
    path = tmp_path / "witness.sqlite3"
    witness = PersistentWitness.initialize(path)
    witness.close()

    db = sqlite3.connect(path)
    db.execute(
        "UPDATE witness_state SET last_hash=? WHERE id=1",
        ("not-a-valid-hash",),
    )
    db.commit()
    db.close()

    with pytest.raises(WitnessError):
        PersistentWitness(path)


def test_missing_state_row_fails_closed(tmp_path):
    path = tmp_path / "witness.sqlite3"
    witness = PersistentWitness.initialize(path)
    witness.close()

    db = sqlite3.connect(path)
    db.execute("DELETE FROM witness_state WHERE id=1")
    db.commit()
    db.close()

    with pytest.raises(WitnessError):
        PersistentWitness(path)


def test_commit_is_idempotent(tmp_path):
    witness = PersistentWitness.initialize(tmp_path / "witness.sqlite3")
    zero = Anchor(0, ZERO_HASH)
    one = Anchor(1, h("a"))

    try:
        witness.prepare(zero, one)
        assert witness.commit(one) == "COMMITTED"
        assert witness.commit(one) == "COMMIT_IDEMPOTENT"
    finally:
        witness.close()
