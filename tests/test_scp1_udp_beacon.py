import symbiont_core as core

from core.node_identity import NodeIdentity
from core.crypto_protocol import SCP1, SCPReplayGuard
from core.scp1_zerotrust import SCP1ZeroTrust


class FakeCoreIdentity:
    def id(self):
        return "local-core-id"

    def public_key(self):
        return "local-core-public-key"


class FakeNode:
    def __init__(self):
        self.identity = FakeCoreIdentity()
        self.peers = core.PeerDirectory()


def make_network(tmp_path):
    local = NodeIdentity(tmp_path / "local-node.json")
    network = core.P2PNetwork(
        FakeNode(),
        scp_identity=local,
    )
    network.scp1 = SCP1ZeroTrust(
        trusted_nodes=[],
        replay_guard=SCPReplayGuard(tmp_path / "replay.json"),
    )
    return network, local


def make_beacon(identity, *, nonce="beacon-nonce", timestamp=None):
    payload = {
        "core_id": "remote-core-id",
        "core_public_key": "remote-core-public-key",
        "name": "Remote",
        "role": "ANALYST",
        "tcp_port": 12345,
        "battery": None,
    }

    packet = SCP1.build_payload(
        node_id=identity.node_id,
        public_key=identity.public_key,
        payload=payload,
        nonce=nonce,
        timestamp=timestamp,
        capability="network.discovery",
        message_type="BEACON",
    )
    return {"scp1": SCP1.sign(identity.private_key, packet)}


def test_valid_beacon_is_authenticated(tmp_path):
    network, _ = make_network(tmp_path)
    remote = NodeIdentity(tmp_path / "remote-node.json")

    result = network._verify_beacon_wire(make_beacon(remote))

    assert result is not None
    payload, node_id = result
    assert payload["core_id"] == "remote-core-id"
    assert node_id == remote.node_id


def test_legacy_beacon_is_rejected(tmp_path):
    network, _ = make_network(tmp_path)

    legacy = {
        "type": "BEACON",
        "symbiont_id": "forged-core-id",
        "public_key": "forged-key",
        "signature": "a" * 64,
    }

    assert network._verify_beacon_wire(legacy) is None


def test_modified_payload_is_rejected(tmp_path):
    network, _ = make_network(tmp_path)
    remote = NodeIdentity(tmp_path / "remote-node.json")
    wire = make_beacon(remote)
    wire["scp1"]["payload"]["core_id"] = "forged-core-id"

    assert network._verify_beacon_wire(wire) is None


def test_invalid_signature_is_rejected(tmp_path):
    network, _ = make_network(tmp_path)
    remote = NodeIdentity(tmp_path / "remote-node.json")
    wire = make_beacon(remote)
    wire["scp1"]["signature"] = "invalid"

    assert network._verify_beacon_wire(wire) is None


def test_mismatched_node_id_is_rejected(tmp_path):
    network, _ = make_network(tmp_path)
    remote = NodeIdentity(tmp_path / "remote-node.json")
    wire = make_beacon(remote)
    wire["scp1"]["node_id"] = "SYM-forged"

    assert network._verify_beacon_wire(wire) is None


def test_expired_beacon_is_rejected(tmp_path):
    import time

    network, _ = make_network(tmp_path)
    remote = NodeIdentity(tmp_path / "remote-node.json")
    wire = make_beacon(
        remote,
        timestamp=int(time.time()) - 1000,
    )

    assert network._verify_beacon_wire(wire) is None


def test_replayed_packet_is_rejected_but_next_beacon_is_allowed(tmp_path):
    network, _ = make_network(tmp_path)
    remote = NodeIdentity(tmp_path / "remote-node.json")

    first = make_beacon(remote, nonce="first")
    second = make_beacon(remote, nonce="second")

    assert network._verify_beacon_wire(first) is not None
    assert network._verify_beacon_wire(first) is None
    assert network._verify_beacon_wire(second) is not None


def test_discovery_does_not_grant_trust(tmp_path):
    network, _ = make_network(tmp_path)
    remote = NodeIdentity(tmp_path / "remote-node.json")

    result = network._verify_beacon_wire(make_beacon(remote))

    assert result is not None
    assert network.scp1.is_trusted(remote.node_id) is False
