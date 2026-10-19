import json

import symbiont_core as core
from core.node_identity import NodeIdentity
from core.crypto_protocol import SCP1, SCPReplayGuard
from core.scp1_zerotrust import SCP1ZeroTrust


class FakeCoreIdentity:
    def id(self):
        return "core-local-test-id"

    def public_key(self):
        return "test-core-public-key"

    def sign(self, payload):
        return "a" * 64

    def verify(self, payload, signature, public_key):
        return True


class FakeSocket:
    def __init__(self, response):
        self.response = response

    def settimeout(self, timeout):
        pass

    def connect(self, address):
        self.address = address

    def sendall(self, data):
        self.sent = data

    def recv(self, size):
        return json.dumps(self.response).encode("utf-8")

    def close(self):
        pass


class FakeNode:
    def __init__(self):
        self.identity = FakeCoreIdentity()
        self.peers = core.PeerDirectory()


def make_scp_packet(identity, payload, nonce):
    packet = SCP1.build_payload(
        node_id=identity.node_id,
        public_key=identity.public_key,
        payload=payload,
        nonce=nonce,
        capability="network.send",
        message_type="RESPONSE",
    )
    return SCP1.sign(identity.private_key, packet)


def test_send_to_does_not_bind_response_to_expected_peer(
    tmp_path, monkeypatch
):
    expected = NodeIdentity(tmp_path / "expected.json")
    other = NodeIdentity(tmp_path / "other.json")
    local = NodeIdentity(tmp_path / "local.json")

    node = FakeNode()
    node.peers.upsert(
        expected.node_id, "unused-core-key", "127.0.0.1", 12345
    )

    network = core.P2PNetwork(node, scp_identity=local)
    network.scp1_enabled = True
    network.scp1 = SCP1ZeroTrust(
        trusted_nodes=[expected.node_id, other.node_id],
        replay_guard=SCPReplayGuard(tmp_path / "replay.json"),
    )

    response_packet = make_scp_packet(
        other,
        {"status": "OK", "from": other.node_id},
        "response-nonce-other",
    )
    fake_socket = FakeSocket({"scp1": response_packet})
    monkeypatch.setattr(
        core.socket, "socket", lambda *a, **kw: fake_socket
    )

    result = network.send_to(expected.node_id, {"action": "TEST"})

    # Expected security behavior: reject a response from the wrong node.
    assert result is None

def test_send_to_accepts_response_from_expected_peer(
    tmp_path, monkeypatch
):
    expected = NodeIdentity(tmp_path / "expected-positive.json")
    local = NodeIdentity(tmp_path / "local-positive.json")

    node = FakeNode()
    node.peers.upsert(
        expected.node_id, "unused-core-key", "127.0.0.1", 12345
    )

    network = core.P2PNetwork(node, scp_identity=local)
    network.scp1_enabled = True
    network.scp1 = SCP1ZeroTrust(
        trusted_nodes=[expected.node_id],
        replay_guard=SCPReplayGuard(tmp_path / "replay-positive.json"),
    )

    payload = {"status": "OK", "from": expected.node_id}
    response_packet = make_scp_packet(
        expected, payload, "response-nonce-expected-positive"
    )
    fake_socket = FakeSocket({"scp1": response_packet})
    monkeypatch.setattr(
        core.socket, "socket", lambda *a, **kw: fake_socket
    )

    result = network.send_to(expected.node_id, {"action": "TEST"})
    assert result == payload
