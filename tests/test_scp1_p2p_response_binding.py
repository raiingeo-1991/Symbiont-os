"""Client response binding checks over a real SCP-1 TCP handshake."""

import hashlib

import symbiont_core as core
from core.crypto_protocol import SCP1
from core.node_identity import NodeIdentity

from test_scp1_stage1b_live_tcp import _bind, _close, _live_pair


def test_send_to_accepts_owner_confirmed_core_node_binding(tmp_path):
    pair = _live_pair(tmp_path)
    a, *_rest, b_core = pair
    try:
        response = a.send_to(b_core, {"action": "PING"})
        assert response["status"] == "PONG"
    finally:
        _close(pair)


def test_send_to_rejects_another_trusted_node_response(tmp_path, monkeypatch):
    pair = _live_pair(tmp_path)
    a, b, *_rest, _a_core, b_core = pair
    rogue = NodeIdentity(tmp_path / "rogue-response.json")
    rogue_core_id = "core-rogue-response"
    rogue_core_key = "rogue-core-public-key"

    # Make the alternate signer independently trusted by the client's TSK.
    _bind(a.node.tsk, rogue_core_id, rogue_core_key, rogue)
    a.node.peers.upsert(
        rogue_core_id,
        rogue_core_key,
        "127.0.0.1",
        12346,
        node_id=rogue.node_id,
        node_public_key_fingerprint=hashlib.sha256(
            rogue.public_key
        ).hexdigest(),
    )
    a._sync_scp1_trust()

    def rogue_response(payload, message_type="P2P"):
        packet = SCP1.build_payload(
            node_id=rogue.node_id,
            public_key=rogue.public_key,
            payload=payload,
            capability="network.send",
            message_type=message_type,
        )
        return {"scp1": SCP1.sign(rogue.private_key, packet)}

    monkeypatch.setattr(b, "_scp1_wrap", rogue_response)
    try:
        # Rogue is trusted, but is not the peer authenticated in this session.
        assert a.send_to(b_core, {"action": "PING"}) is None
    finally:
        _close(pair)


def test_send_to_rejects_missing_owner_confirmed_binding(tmp_path):
    pair = _live_pair(tmp_path)
    a, *_rest, b_core = pair
    try:
        from tsk import TrustedSecurityKernel

        a.node.tsk = TrustedSecurityKernel(root=tmp_path / "empty-client-tsk")
        a._sync_scp1_trust()
        assert a.send_to(b_core, {"action": "PING"}) is None
    finally:
        _close(pair)


def test_send_to_rejects_mismatched_core_key_fingerprint(tmp_path):
    pair = _live_pair(tmp_path)
    a, b, *_rest, _a_core, b_core = pair
    try:
        peer = a.node.peers.get(b_core)
        a.node.peers.upsert(
            b_core,
            "different-core-public-key",
            peer.address,
            peer.tcp_port,
            node_id=peer.node_id,
            node_public_key_fingerprint=peer.node_public_key_fingerprint,
        )
        assert a.send_to(b_core, {"action": "PING"}) is None
    finally:
        _close(pair)
