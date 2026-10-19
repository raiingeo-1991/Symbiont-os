import base64
import subprocess
import time

from core.crypto_protocol import SCP1, SCPReplayGuard
from core.scp1_zerotrust import SCP1ZeroTrust


def make_keys(tmp_path):
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"

    subprocess.run(
        [
            "openssl", "genpkey", "-algorithm", "ED25519",
            "-out", str(private_path),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl", "pkey", "-in", str(private_path),
            "-pubout", "-out", str(public_path),
        ],
        check=True,
        capture_output=True,
    )

    return private_path.read_bytes(), public_path.read_bytes()


def make_packet(tmp_path, *, nonce="test-nonce", timestamp=None):
    private_key, public_key_pem = make_keys(tmp_path)
    packet = SCP1.build_payload(
        node_id=SCP1.node_id(public_key_pem),
        public_key=public_key_pem,
        payload={"message": "security-test"},
        nonce=nonce,
        timestamp=timestamp,
    )
    return private_key, public_key_pem, SCP1.sign(private_key, packet)


def test_valid_signature_is_accepted(tmp_path):
    _, _, packet = make_packet(tmp_path)
    assert SCP1.verify(packet)


def test_modified_payload_is_rejected(tmp_path):
    _, _, packet = make_packet(tmp_path)
    packet["payload"]["message"] = "tampered"
    assert not SCP1.verify(packet)


def test_invalid_signature_is_rejected(tmp_path):
    _, _, packet = make_packet(tmp_path)
    packet["signature"] = base64.b64encode(b"invalid-signature").decode()
    assert not SCP1.verify(packet)


def test_expired_packet_is_rejected(tmp_path):
    _, _, packet = make_packet(
        tmp_path,
        timestamp=int(time.time()) - 1000,
    )
    assert not SCP1.verify(packet, max_age=300)


def test_untrusted_node_is_rejected(tmp_path):
    _, _, packet = make_packet(tmp_path)
    guard = SCP1ZeroTrust(
        trusted_nodes=[],
        replay_guard=SCPReplayGuard(tmp_path / "replay.json"),
    )
    assert not guard.verify(packet)


def test_replay_is_rejected(tmp_path):
    _, _, packet = make_packet(tmp_path)
    node_id = packet["node_id"]
    guard = SCP1ZeroTrust(
        trusted_nodes=[node_id],
        replay_guard=SCPReplayGuard(tmp_path / "replay.json"),
    )

    assert guard.verify(packet)
    assert not guard.verify(packet)


def test_replay_guard_persists_across_instances(tmp_path):
    path = tmp_path / "replay.json"
    first = SCPReplayGuard(path)
    assert first.check_and_store("node-A", "nonce-A")

    second = SCPReplayGuard(path)
    assert not second.check_and_store("node-A", "nonce-A")
