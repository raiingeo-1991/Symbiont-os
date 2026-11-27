import pytest

import symbiont_core as core
from core.security import CapabilityGate, SecureSettlement, SecurityError

from test_scp1_stage1b_live_tcp import (
    _close,
    _live_pair,
    _open_authenticated_client_connection,
    _receive_live_response,
)


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, event, **data):
        self.events.append((event, data))


class FakeSecurity:
    def __init__(self):
        self.capabilities = CapabilityGate()
        self.audit = FakeAudit()


class FakeEconomy:
    def __init__(self):
        self.calls = []

    def reserve_quest(self, quest_id, reward, **kwargs):
        self.calls.append(("reserve", quest_id, reward))
        return True


def test_settlement_denial_does_not_call_economy():
    economy = FakeEconomy()
    security = FakeSecurity()
    settlement = SecureSettlement(economy, security)

    with pytest.raises(SecurityError):
        settlement.reserve("audit-denied", 10)

    assert economy.calls == []
    assert security.audit.events == []


def test_settlement_allows_explicitly_granted_payment_capability():
    economy = FakeEconomy()
    security = FakeSecurity()
    security.capabilities.grant("payment.execute")
    settlement = SecureSettlement(economy, security)

    assert settlement.reserve("audit-allowed", 10) is True
    assert economy.calls == [("reserve", "audit-allowed", 10)]
    assert len(security.audit.events) == 1
    assert security.audit.events[0][0] == "settlement.reserved"


def test_incoming_scp1_rejects_sender_signer_mismatch_over_live_tcp(tmp_path):
    pair = _live_pair(tmp_path)
    a, b, *_rest, _a_core, b_core = pair
    conn = None
    try:
        conn, handshake = _open_authenticated_client_connection(pair)
        request = {
            "sender": "core-forged-sender",
            "action": "PING",
            "session_id": handshake.session_id,
        }
        core.P2PNetwork._send_tcp_frame(
            conn, a._scp1_wrap(request, message_type="PING")
        )
        response = _receive_live_response(a, b, b_core, conn)
        assert response.get("status") == "UNAUTHORIZED"
    finally:
        if conn is not None:
            conn.close()
        _close(pair)


def test_core_payment_permission_is_separate_and_denied_by_default(tmp_path, monkeypatch):
    import symbiont_core as core

    monkeypatch.setenv("SYMBIONT_SMSA", "1")
    monkeypatch.setenv("SYMBIONT_SCA1_SHADOW", "0")
    sym = core.Symbiont(tmp_path / "sym", show_recovery_phrase=False)
    try:
        assert sym.permissions.check("payment_execute") is False
        assert sym.smsa is not None
        assert sym.smsa.check("payment.execute") is False

        sym.permissions.allow("payment_execute")
        assert sym.smsa.check("payment.execute") is True

        sym.permissions.deny("payment_execute")
        assert sym.smsa.check("payment.execute") is False
    finally:
        sym.close()
