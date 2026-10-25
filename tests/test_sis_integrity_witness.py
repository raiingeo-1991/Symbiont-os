import pytest

from core.sss.sis_integrity import SISIntegrity
from core.sss.sis_witness import (
    Anchor,
    PersistentWitness,
    WitnessError,
    ZERO_HASH,
)


def evidence(evidence_id="evidence-1"):
    return {
        "evidence_id": evidence_id,
        "source_event_id": f"event-{evidence_id}",
        "source_event_type": "security.test",
        "source_event_hash": "a" * 64,
        "evidence_kind": "fact",
        "incident_id": "test-incident",
        "record_hash": "b" * 64,
    }


def setup_pair(tmp_path):
    root = tmp_path / "sis"
    witness_path = tmp_path / "witness.sqlite3"
    witness = PersistentWitness.initialize(witness_path)
    sis = SISIntegrity(root, witness=witness)
    return sis, witness, witness_path


def close_pair(sis, witness):
    sis.close()
    witness.close()


def test_witness_mode_anchors_and_confirms_record(tmp_path):
    sis, witness, _ = setup_pair(tmp_path)
    try:
        sis.anchor_evidence(evidence())
        status = sis.status()
        assert status["valid"] is True
        assert status["witness_valid"] is True
        assert status["witness_state"] == "MATCH"
        assert witness.current.sequence == 1
    finally:
        close_pair(sis, witness)


def test_duplicate_delivery_does_not_advance_witness_twice(tmp_path):
    sis, witness, _ = setup_pair(tmp_path)
    try:
        first = sis.anchor_evidence(evidence())
        second = sis.anchor_evidence(evidence())
        assert first == second
        assert sis.status()["anchored_records"] == 1
        assert witness.current.sequence == 1
    finally:
        close_pair(sis, witness)


def test_mismatched_witness_fails_closed_before_new_append(tmp_path):
    sis, witness, _ = setup_pair(tmp_path)
    try:
        sis.ledger.append("existing", "existing evidence")
        with pytest.raises(WitnessError):
            sis.anchor_evidence(evidence())
        assert sis.ledger.verify() == (True, 1)
        assert witness.current == Anchor(0, ZERO_HASH)
    finally:
        close_pair(sis, witness)


def test_pending_candidate_is_committed_only_when_ledger_matches(tmp_path):
    sis, witness, _ = setup_pair(tmp_path)
    try:
        previous = sis.ledger.head_anchor()
        sis.ledger.append("prepared-event", "prepared evidence")
        candidate = sis.ledger.head_anchor()
        witness.prepare(previous, candidate)

        status = sis.status()
        assert status["valid"] is False
        assert status["witness_valid"] is False
        assert witness.current == previous
        assert witness.pending == (previous, candidate)

        assert sis._check_witness(recover_pending=True) == "RECOVERED_COMMIT"
        assert witness.current == candidate
        assert sis.status()["witness_valid"] is True
    finally:
        close_pair(sis, witness)


def test_checkpoint_failure_does_not_confirm_untrusted_ledger(tmp_path, monkeypatch):
    sis, witness, _ = setup_pair(tmp_path)
    try:
        original = sis.ledger._write_checkpoint

        def fail_checkpoint(sequence, last_hash):
            raise OSError("simulated checkpoint failure")

        monkeypatch.setattr(sis.ledger, "_write_checkpoint", fail_checkpoint)
        with pytest.raises(OSError, match="simulated checkpoint failure"):
            sis.anchor_evidence(evidence())

        assert witness.current == Anchor(0, ZERO_HASH)
        assert sis.ledger.verify() == (False, 1)

        monkeypatch.setattr(sis.ledger, "_write_checkpoint", original)
    finally:
        close_pair(sis, witness)


def test_status_reports_local_ledger_ahead_of_witness(tmp_path):
    sis, witness, _ = setup_pair(tmp_path)
    try:
        sis.ledger.append("unconfirmed", "unconfirmed evidence")
        status = sis.status()
        assert status["valid"] is False
        assert status["witness_valid"] is False
        assert status["witness_state"] == "ERROR"
    finally:
        close_pair(sis, witness)


def test_witness_state_survives_reopen(tmp_path):
    sis, witness, witness_path = setup_pair(tmp_path)
    sis.anchor_evidence(evidence())
    sis.close()
    witness.close()

    reopened_witness = PersistentWitness(witness_path)
    reopened_sis = SISIntegrity(tmp_path / "sis", witness=reopened_witness)
    try:
        status = reopened_sis.status()
        assert status["valid"] is True
        assert status["witness_valid"] is True
        assert status["witness_state"] == "MATCH"
        assert reopened_witness.current.sequence == 1
    finally:
        close_pair(reopened_sis, reopened_witness)


def test_pending_without_ledger_candidate_blocks_new_evidence(tmp_path):
    sis, witness, _ = setup_pair(tmp_path)
    try:
        previous = sis.ledger.head_anchor()
        candidate = Anchor(1, "c" * 64)
        witness.prepare(previous, candidate)

        with pytest.raises(WitnessError, match="not reflected in the Ledger"):
            sis.anchor_evidence(evidence("blocked-event"))

        assert sis.ledger.verify() == (True, 0)
        assert witness.current == previous
        assert witness.pending == (previous, candidate)
    finally:
        close_pair(sis, witness)
