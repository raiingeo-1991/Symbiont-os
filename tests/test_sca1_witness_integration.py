import os
import shutil
from pathlib import Path

import pytest

from core.continuity.shadow import ContinuityShadow
from core.sss.sis_witness import Anchor, PersistentWitness, WitnessError, ZERO_HASH


class FakeIdentity:
    def id(self):
        return "TEST-SYMBIONT"

    def public_key(self):
        return "TEST-PUBLIC-KEY"


def core_event(event_id, previous, event_hash):
    return {
        "event_id": event_id,
        "type": "memory.created",
        "previous": previous,
        "hash": event_hash,
        "payload": {"memory_id": event_id},
    }


def make_shadow(root):
    witness = PersistentWitness(root / "sca1_witness.sqlite3")
    return ContinuityShadow(root, FakeIdentity(), witness=witness)


def test_witness_detects_rollback_of_continuity_directory(tmp_path):
    root = tmp_path / "node"
    root.mkdir()
    witness = PersistentWitness.initialize(root / "sca1_witness.sqlite3")
    shadow = ContinuityShadow(root, FakeIdentity(), witness=witness)
    try:
        first = core_event("e1", ZERO_HASH, "a" * 64)
        shadow.on_core_event(first)
        snapshot = tmp_path / "continuity-snapshot"
        shutil.copytree(root / "continuity", snapshot)

        second = core_event("e2", "a" * 64, "b" * 64)
        shadow.on_core_event(second)
        assert shadow.status()["witness_valid"] is True
    finally:
        shadow.close()

    # Restore the local SCA-1 files, but deliberately keep the witness DB.
    shutil.rmtree(root / "continuity")
    shutil.copytree(snapshot, root / "continuity")
    reopened_witness = PersistentWitness(root / "sca1_witness.sqlite3")
    try:
        with pytest.raises(WitnessError, match="Ledger/Witness mismatch"):
            ContinuityShadow(root, FakeIdentity(), witness=reopened_witness)
    finally:
        reopened_witness.close()


def test_restart_recovers_commit_after_ledger_persisted(tmp_path, monkeypatch):
    root = tmp_path / "node"
    root.mkdir()
    witness = PersistentWitness.initialize(root / "sca1_witness.sqlite3")
    shadow = ContinuityShadow(root, FakeIdentity(), witness=witness)

    def fail_commit(_candidate):
        raise OSError("simulated crash before witness commit")

    monkeypatch.setattr(witness, "commit", fail_commit)
    with pytest.raises(OSError, match="simulated crash"):
        shadow.on_core_event(core_event("e1", ZERO_HASH, "a" * 64))
    shadow.close()

    recovered = make_shadow(root)
    try:
        status = recovered.status()
        assert status["witness_valid"] is True
        assert status["witness_state"] == "MATCH"
        assert recovered.ledger.witness.current.sequence == 1
        assert recovered.state.memory_version == 1
    finally:
        recovered.close()


def test_restart_aborts_prepare_when_ledger_was_not_written(tmp_path):
    root = tmp_path / "node"
    root.mkdir()
    witness = PersistentWitness.initialize(root / "sca1_witness.sqlite3")
    candidate = Anchor(1, "c" * 64)
    witness.prepare(Anchor(0, ZERO_HASH), candidate)
    witness.close()

    shadow = make_shadow(root)
    try:
        assert shadow.ledger.witness.pending is None
        assert shadow.ledger.witness.current == Anchor(0, ZERO_HASH)
        assert shadow.status()["witness_valid"] is True
    finally:
        shadow.close()


def test_witness_rejects_missing_or_rolled_back_ledger(tmp_path):
    root = tmp_path / "node"
    root.mkdir()
    witness = PersistentWitness.initialize(root / "sca1_witness.sqlite3")
    witness.prepare(Anchor(0, ZERO_HASH), Anchor(1, "d" * 64))
    witness.commit(Anchor(1, "d" * 64))
    witness.close()

    with pytest.raises(WitnessError, match="Ledger/Witness mismatch"):
        make_shadow(root)


def test_core_witness_flag_enables_shadow_and_uses_existing_store(tmp_path, monkeypatch):
    from symbiont_core import Symbiont

    root = tmp_path / "node"
    root.mkdir()
    provisioned = PersistentWitness.initialize(root / "sca1_witness.sqlite3")
    provisioned.close()

    monkeypatch.setenv("SYMBIONT_SCA1_WITNESS", "1")
    monkeypatch.setenv("SYMBIONT_SCA1_SHADOW", "0")
    sym = Symbiont(root=root, show_recovery_phrase=False)
    try:
        assert sym.continuity_shadow is not None
        status = sym.continuity_shadow.status()
        assert status["witness_enabled"] is True
        assert status["witness_valid"] is True
    finally:
        assert sym.close() is True


def test_core_witness_flag_fails_closed_when_store_is_missing(tmp_path, monkeypatch):
    from symbiont_core import Symbiont

    monkeypatch.setenv("SYMBIONT_SCA1_WITNESS", "1")
    monkeypatch.setenv("SYMBIONT_SCA1_SHADOW", "0")
    sym = Symbiont(root=tmp_path / "node", show_recovery_phrase=False)
    try:
        assert sym.continuity_shadow is None
        assert "Witness database is missing" in sym.continuity_shadow_error
        assert not (tmp_path / "node" / "sca1_witness.sqlite3").exists()
    finally:
        assert sym.close() is True
