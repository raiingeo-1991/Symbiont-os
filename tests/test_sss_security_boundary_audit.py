import json

import pytest

import symbiont_core as core
from core.crypto_protocol import SCP1, SCPReplayGuard
from core.node_identity import NodeIdentity
from core.scp1_zerotrust import SCP1ZeroTrust
from core.security import CapabilityGate, SecureSettlement, SecurityError


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


class FakeCoreIdentity:
    def id(self):
        return "core-local-audit"

    def public_key(self):
        return "test-public-key"

    def verify(self, payload, signature, public_key):
        # Имитирует старый Core Identity, чтобы изолированно
        # проверить привязку SCP-1 к внутреннему sender.
        return bool(signature) and len(signature) >= 32


class FakeConnection:
    def __init__(self, incoming):
        self.incoming = incoming
        self.sent = None

    def settimeout(self, timeout):
        pass

    def recv(self, size):
        return self.incoming

    def sendall(self, data):
        self.sent = data


class FakeNode:
    def __init__(self):
        self.identity = FakeCoreIdentity()
        self.peers = core.PeerDirectory()


def test_incoming_scp1_does_not_bind_sender_to_signing_node(
    tmp_path, monkeypatch
):
    signer = NodeIdentity(tmp_path / "signer.json")
    local = NodeIdentity(tmp_path / "local.json")

    node = FakeNode()
    # Внутренний sender указывает на другой Core-узел.
    node.peers.upsert(
        "core-forged-sender",
        "test-peer-key",
        "127.0.0.1",
        12345,
    )

    network = core.P2PNetwork(node, scp_identity=local)
    network.scp1_enabled = True
    network.scp1 = SCP1ZeroTrust(
        trusted_nodes=[signer.node_id],
        replay_guard=SCPReplayGuard(tmp_path / "replay.json"),
    )

    request = {
        "sender": "core-forged-sender",
        "signature": "a" * 64,
        "action": "PING",
    }
    packet = SCP1.build_payload(
        node_id=signer.node_id,
        public_key=signer.public_key,
        payload=request,
        nonce="audit-inbound-mismatch",
        capability="network.send",
        message_type="P2P",
    )
    packet = SCP1.sign(signer.private_key, packet)

    connection = FakeConnection(
        json.dumps({"scp1": packet}).encode("utf-8")
    )

    # Изолируем формат ответа: нас интересует, дошёл ли запрос
    # с несовпадающими идентичностями до обработки PING.
    monkeypatch.setattr(
        network,
        "_scp1_wrap",
        lambda payload, message_type="P2P": {
            "test_response": payload
        },
    )

    network._handle_tcp(connection, ("127.0.0.1", 12345))

    assert connection.sent is not None
    response = json.loads(connection.sent.decode("utf-8"))
    assert response.get("test_response", {}).get("status") == "PONG"
