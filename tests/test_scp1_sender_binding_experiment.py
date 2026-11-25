"""SCP-1 sender, binding and replay checks over the production TCP flow."""

import pytest

import symbiont_core as core
from core.crypto_protocol import SCP1
from core.node_identity import NodeIdentity
from tsk import TrustedSecurityKernel

from test_scp1_stage1b_live_tcp import (
    _close,
    _live_pair,
    _open_authenticated_client_connection,
    _receive_live_response,
)


def test_scp1_rejects_mismatched_inner_sender_after_handshake(tmp_path):
    pair = _live_pair(tmp_path)
    a, b, *_rest, a_core, b_core = pair
    conn = None
    try:
        conn, handshake = _open_authenticated_client_connection(pair)
        request = {
            "action": "PING",
            "sender": "core-forged-sender",
            "session_id": handshake.session_id,
        }
        wire = a._scp1_wrap(request, message_type="PING")
        core.P2PNetwork._send_tcp_frame(conn, wire)
        response = _receive_live_response(a, b, b_core, conn)
        assert response.get("status") == "UNAUTHORIZED"
    finally:
        if conn is not None:
            conn.close()
        _close(pair)


def test_confirmed_binding_allows_ping_after_tsk_reload(tmp_path):
    pair = _live_pair(tmp_path)
    a, *_rest, b_core = pair
    try:
        assert a.send_to(b_core, {"action": "PING"})["status"] == "PONG"
    finally:
        _close(pair)


def test_binding_rejects_mismatched_core_key_fingerprint(tmp_path):
    pair = _live_pair(tmp_path)
    a, b, *_rest, a_core, b_core = pair
    try:
        # The server's PeerDirectory key no longer matches its persisted TSK binding.
        b.node.peers.upsert(
            a_core,
            "different-core-public-key",
            "127.0.0.1",
            12345,
            node_id=a.scp_identity.node_id,
            node_public_key_fingerprint=__import__("hashlib").sha256(
                a.scp_identity.public_key
            ).hexdigest(),
        )
        b._sync_scp1_trust()
        assert a.send_to(b_core, {"action": "PING"}) is None
    finally:
        _close(pair)


def test_incoming_scp1_rejects_missing_owner_confirmed_binding(tmp_path):
    pair = _live_pair(tmp_path)
    a, b, *_rest, a_core, b_core = pair
    try:
        # Remove only the server's persisted binding state; do not alter client trust.
        b.node.tsk = TrustedSecurityKernel(root=tmp_path / "empty-server-tsk")
        b._sync_scp1_trust()
        assert a.send_to(b_core, {"action": "PING"}) is None
    finally:
        _close(pair)


def test_incoming_scp1_rejects_replayed_operation_packet(tmp_path):
    pair = _live_pair(tmp_path)
    a, b, *_rest, a_core, b_core = pair
    conn = None
    try:
        conn, handshake = _open_authenticated_client_connection(pair)
        request = {
            "action": "PING",
            "sender": a_core,
            "session_id": handshake.session_id,
        }
        wire = a._scp1_wrap(request, message_type="PING")
        core.P2PNetwork._send_tcp_frame(conn, wire)
        first = _receive_live_response(a, b, b_core, conn)
        assert first.get("status") == "PONG"

        core.P2PNetwork._send_tcp_frame(conn, wire)
        with pytest.raises(ConnectionError):
            core.P2PNetwork._recv_tcp_frame(conn)
    finally:
        if conn is not None:
            conn.close()
        _close(pair)
