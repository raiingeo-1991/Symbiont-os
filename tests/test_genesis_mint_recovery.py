import pytest

from core.security import CapabilityGate, GenesisMint
from symbiont_core import Economy, EventJournal


class RecordingAudit:
    def record(self, event, **data):
        return True


class FailingAudit:
    def record(self, event, **data):
        raise OSError("SIMULATED_AUDIT_FAILURE")


class FakeSecurity:
    def __init__(self, audit=None):
        self.capabilities = CapabilityGate()
        self.capabilities.grant("economy.mint")
        self.audit = audit or RecordingAudit()


def make_economy(root):
    return Economy(
        root / "state.json",
        EventJournal(root / "events.log"),
    )


def test_mint_id_is_not_replayed_after_restart(tmp_path):
    economy = make_economy(tmp_path)
    mint = GenesisMint(economy, FakeSecurity())

    assert mint.mint(10, recipient="test", mint_id="stable-mint-1")
    assert economy.snapshot()["balance"] == 10

    restored = make_economy(tmp_path)
    restarted_mint = GenesisMint(restored, FakeSecurity())

    assert restarted_mint.mint(
        10, recipient="test", mint_id="stable-mint-1"
    ) is False
    assert restored.snapshot()["balance"] == 10


def test_audit_failure_does_not_allow_duplicate_mint_after_restart(
    tmp_path,
):
    economy = make_economy(tmp_path)
    mint = GenesisMint(economy, FakeSecurity(FailingAudit()))

    with pytest.raises(OSError, match="SIMULATED_AUDIT_FAILURE"):
        mint.mint(10, recipient="test", mint_id="stable-mint-2")

    restored = make_economy(tmp_path)
    restarted_mint = GenesisMint(restored, FakeSecurity())

    assert restarted_mint.mint(
        10, recipient="test", mint_id="stable-mint-2"
    ) is False
    assert restored.snapshot()["balance"] == 10


def test_failed_state_save_does_not_leave_uncommitted_balance(
    tmp_path, monkeypatch
):
    economy = make_economy(tmp_path)
    mint = GenesisMint(economy, FakeSecurity())
    original_save = economy._save

    def fail_save():
        raise OSError("SIMULATED_STATE_SAVE_FAILURE")

    monkeypatch.setattr(economy, "_save", fail_save)

    with pytest.raises(OSError, match="SIMULATED_STATE_SAVE_FAILURE"):
        mint.mint(10, recipient="test", mint_id="stable-mint-3")

    assert economy.snapshot()["balance"] == 0

    monkeypatch.setattr(economy, "_save", original_save)

    assert mint.mint(
        10, recipient="test", mint_id="stable-mint-3"
    ) is True
    assert economy.snapshot()["balance"] == 10


@pytest.mark.parametrize("amount", [
    float("nan"),
    float("inf"),
    float("-inf"),
])
def test_mint_rejects_non_finite_amounts(tmp_path, amount):
    economy = make_economy(tmp_path)
    mint = GenesisMint(economy, FakeSecurity())

    assert mint.mint(
        amount, recipient="test", mint_id="non-finite-mint"
    ) is False
    assert economy.snapshot()["balance"] == 0
    assert "non-finite-mint" not in economy.mint_operations
