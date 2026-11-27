import json

import pytest
import symbiont_core as core

from symbiont_core import Economy, EconomyStateError, EventJournal


def make_economy(tmp_path):
    return Economy(tmp_path / "state.json", EventJournal(tmp_path / "events.log"))


def test_missing_state_starts_empty_and_can_be_saved(tmp_path):
    economy = make_economy(tmp_path)
    assert economy.snapshot()["balance"] == 0
    economy.credit(12, "test")
    restored = make_economy(tmp_path)
    assert restored.snapshot()["balance"] == 12


def test_valid_escrow_and_payment_state_survives_reload(tmp_path):
    economy = make_economy(tmp_path)
    economy.credit(20, "test")
    assert economy.reserve_quest("q1", 5)
    economy = make_economy(tmp_path)
    assert economy.snapshot()["balance"] == 15
    assert economy.escrow["q1"]["escrow_state"] == "ESCROW"


@pytest.mark.parametrize("raw", [
    "{broken-json",
    "[]",
    '{"wallet": {"balance": -1}}',
    '{"wallet": {"balance": NaN}}',
    '{"wallet": [], "escrow": {}, "payments": {}}',
    '{"wallet": {"balance": 5}, "escrow": []}',
    '{"wallet": {"balance": 5}, "payments": []}',
])
def test_invalid_state_fails_closed_without_overwriting_file(tmp_path, raw):
    path = tmp_path / "state.json"
    path.write_text(raw, encoding="utf-8")
    original = path.read_bytes()

    with pytest.raises(EconomyStateError):
        make_economy(tmp_path)

    assert path.read_bytes() == original

def test_received_payment_and_replay_protection_survive_restart(tmp_path):
    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "events.log"

    journal = EventJournal(journal_path)
    economy = Economy(state_path, journal)

    journal.append("quest.incoming.done", {
        "quest_id": "payment-restart-q1",
        "from": "creator-test",
        "reward": 7,
    })

    assert economy.receive_quest_payment(
        "payment-restart-q1",
        7,
        creator_node="creator-test",
        worker_node="worker-test",
    ) is True

    restored = Economy(state_path, EventJournal(journal_path))

    assert restored.snapshot()["balance"] == 7
    assert "payment-restart-q1" in restored.payments
    assert restored.payments["payment-restart-q1"]["amount"] == 7

    assert restored.receive_quest_payment(
        "payment-restart-q1",
        7,
        creator_node="creator-test",
        worker_node="worker-test",
    ) is False

    assert restored.snapshot()["balance"] == 7

def test_payment_rejected_when_event_journal_is_corrupt(tmp_path):
    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "events.log"
    journal = EventJournal(journal_path)
    economy = Economy(state_path, journal)

    journal.append("quest.incoming.done", {
        "quest_id": "corrupt-journal-q1",
        "from": "creator-test",
        "reward": 7,
    })

    with journal_path.open("a", encoding="utf-8") as stream:
        stream.write("{broken-json\\n")

    assert economy.receive_quest_payment(
        "corrupt-journal-q1",
        7,
        creator_node="creator-test",
        worker_node="worker-test",
    ) is False

    assert economy.snapshot()["balance"] == 0
    assert "corrupt-journal-q1" not in economy.payments


def test_economy_outbox_recovers_event_after_journal_failure(tmp_path):
    journal_path = tmp_path / "events.log"
    journal = EventJournal(journal_path)
    economy = Economy(tmp_path / "state.json", journal)

    original_append = journal.append
    def fail_once(event_type, payload):
        journal.append = original_append
        raise OSError("simulated event journal failure")
    journal.append = fail_once

    economy.credit(13, "outbox test")
    assert economy.snapshot()["balance"] == 13
    assert len(economy.journal_outbox) == 1

    restored = Economy(tmp_path / "state.json", EventJournal(journal_path))
    assert restored.snapshot()["balance"] == 13
    assert restored.journal_outbox == []
    events = EventJournal(journal_path).all_events()
    matching = [e for e in events if e.get("type") == "economy.credit"]
    assert len(matching) == 1
    assert matching[0]["payload"]["amount"] == 13


def test_frozen_escrow_cannot_be_unilaterally_refunded(tmp_path):
    economy = make_economy(tmp_path)
    economy.credit(20, "seed")
    assert economy.reserve_quest("frozen-q", 10)
    assert economy.freeze_quest("frozen-q", "disputed")
    assert economy.refund_quest("frozen-q") is False
    assert economy.escrow["frozen-q"]["escrow_state"] == "FROZEN"
    assert economy.snapshot()["balance"] == 10


def test_economy_rolls_back_memory_when_atomic_state_save_fails(tmp_path, monkeypatch):
    journal = EventJournal(tmp_path / "events.log")
    economy = Economy(tmp_path / "state.json", journal)

    def fail_atomic_write(*_args, **_kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr(core, "atomic_write", fail_atomic_write)

    with pytest.raises(OSError, match="simulated disk full"):
        economy.credit(5, "failed persistence")

    assert economy.snapshot()["balance"] == 0
    assert economy.journal_outbox == []
    assert journal.verify() == (True, 0)
    assert not (tmp_path / "state.json").exists()

def test_frozen_escrow_cannot_be_released_back_to_creator(tmp_path):
    economy = make_economy(tmp_path)
    economy.credit(20, "seed")
    assert economy.reserve_quest("frozen-release-q", 10)
    assert economy.freeze_quest("frozen-release-q", "payment status uncertain")

    assert economy.release_quest("frozen-release-q", worker_node="worker-1") is False
    assert economy.escrow["frozen-release-q"]["escrow_state"] == "FROZEN"
    assert economy.snapshot()["balance"] == 10


def test_confirmed_payment_can_finalize_frozen_escrow_without_refund(tmp_path):
    economy = make_economy(tmp_path)
    economy.credit(20, "seed")
    assert economy.reserve_quest("frozen-finalize-q", 10)
    assert economy.freeze_quest("frozen-finalize-q", "payment confirmation delayed")

    assert economy.finalize_quest_payment(
        "frozen-finalize-q", worker_node="worker-1"
    ) == 10
    assert economy.escrow["frozen-finalize-q"]["escrow_state"] == "RELEASED"
    assert economy.escrow["frozen-finalize-q"]["payment_finalized"] is True
    assert economy.snapshot()["balance"] == 10
