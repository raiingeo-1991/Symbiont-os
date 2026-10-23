import json

import pytest

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
