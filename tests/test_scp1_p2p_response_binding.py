import hashlib
import json

import symbiont_core as core
from core.node_identity import NodeIdentity
from core.crypto_protocol import SCP1, SCPReplayGuard
from core.scp1_zerotrust import SCP1ZeroTrust
from tsk import TrustedSecurityKernel


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
        self.tsk = None


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


def make_network(tmp_path, monkeypatch, response, expected_node,
                 core_id, core_public_key, trusted_nodes,
                 *, bind=True, bound_core_key=None, nonce="response-nonce"):
    local = NodeIdentity(tmp_path / "local.json")
    node = FakeNode()
    node.peers.upsert(
        core_id, core_public_key, "127.0.0.1", 12345
    )

    tsk_root = tmp_path / "tsk"
    node.tsk = TrustedSecurityKernel(root=tsk_root)

    if bind:
        bound_key = (
            core_public_key if bound_core_key is None else bound_core_key
        )
        core_fp = hashlib.sha256(bound_key.encode("utf-8")).hexdigest()
        node_path = tmp_path / "expected-node.json"
        # Use the same persisted NodeIdentity that the binding confirms.
        expected_node_path = expected_node.path
        node.tsk.confirm_core_node_binding(
            core_id=core_id,
            core_public_key_fingerprint=core_fp,
            node_identity_path=expected_node_path,
            owner_confirmation=f"BIND {core_id} TO NODE {expected_node.node_id}",
        )
        # Exercise persisted binding state, not just the original instance.
        node.tsk = TrustedSecurityKernel(root=tsk_root)

    network = core.P2PNetwork(node, scp_identity=local)
    network.scp1_enabled = True
    network.scp1 = SCP1ZeroTrust(
        trusted_nodes=trusted_nodes,
        replay_guard=SCPReplayGuard(tmp_path / "replay.json"),
    )

    fake_socket = FakeSocket(response)
    monkeypatch.setattr(
        core.socket, "socket", lambda *a, **kw: fake_socket
    )
    return network, core_id


def test_send_to_accepts_owner_confirmed_core_node_binding(
    tmp_path, monkeypatch
):
    expected_path = tmp_path / "expected.json"
    expected = NodeIdentity(expected_path)
    core_id = "core-expected"
    core_key = "expected-core-public-key"
    payload = {"status": "OK", "from": expected.node_id}
    response = {"scp1": make_scp_packet(expected, payload, "nonce-valid")}

    network, peer_id = make_network(
        tmp_path, monkeypatch, response, expected,
        core_id, core_key, [expected.node_id],
    )

    assert peer_id == core_id
    assert network.send_to(peer_id, {"action": "TEST"}) == payload


def test_send_to_rejects_another_trusted_node(
    tmp_path, monkeypatch
):
    expected = NodeIdentity(tmp_path / "expected.json")
    other = NodeIdentity(tmp_path / "other.json")
    core_id = "core-expected"
    core_key = "expected-core-public-key"
    response = {
        "scp1": make_scp_packet(
            other, {"status": "FORGED"}, "nonce-wrong-node"
        )
    }

    network, peer_id = make_network(
        tmp_path, monkeypatch, response, expected,
        core_id, core_key, [expected.node_id, other.node_id],
    )

    assert network.send_to(peer_id, {"action": "TEST"}) is None


def test_send_to_rejects_missing_owner_confirmed_binding(
    tmp_path, monkeypatch
):
    expected = NodeIdentity(tmp_path / "expected.json")
    core_id = "core-without-binding"
    core_key = "expected-core-public-key"
    response = {
        "scp1": make_scp_packet(
            expected, {"status": "OK"}, "nonce-no-binding"
        )
    }

    network, peer_id = make_network(
        tmp_path, monkeypatch, response, expected,
        core_id, core_key, [expected.node_id], bind=False,
    )

    assert network.send_to(peer_id, {"action": "TEST"}) is None


def test_send_to_rejects_mismatched_core_key_fingerprint(
    tmp_path, monkeypatch
):
    expected = NodeIdentity(tmp_path / "expected.json")
    core_id = "core-wrong-fingerprint"
    core_key = "expected-core-public-key"
    response = {
        "scp1": make_scp_packet(
            expected, {"status": "OK"}, "nonce-wrong-fingerprint"
        )
    }

    network, peer_id = make_network(
        tmp_path, monkeypatch, response, expected,
        core_id, core_key, [expected.node_id],
        bound_core_key="different-core-public-key",
    )

    assert network.send_to(peer_id, {"action": "TEST"}) is None
