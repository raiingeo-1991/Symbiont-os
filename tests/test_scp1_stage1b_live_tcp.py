import hashlib
import socket
import threading
import time
from types import SimpleNamespace

import symbiont_core as core
from core.node_identity import NodeIdentity
from core.crypto_protocol import SCP1
from core.node_handshake import NodeHandshake
from tsk import TrustedSecurityKernel


class FakeCoreIdentity:
    def __init__(self, core_id, public_key):
        self._id, self._public_key = core_id, public_key
    def id(self): return self._id
    def public_key(self): return self._public_key


def _node(core_id, core_key, node_identity, tsk, remote_core_id, remote_core_key, remote_node, remote_port):
    peers = core.PeerDirectory()
    peers.upsert(remote_core_id, remote_core_key, "127.0.0.1", remote_port,
                 node_id=remote_node.node_id,
                 node_public_key_fingerprint=hashlib.sha256(remote_node.public_key).hexdigest())
    return SimpleNamespace(identity=FakeCoreIdentity(core_id, core_key), peers=peers, tsk=tsk)


def _bind(tsk, core_id, core_key, remote_node):
    fp = hashlib.sha256(core_key.encode()).hexdigest()
    assert tsk.confirm_core_node_binding(
        core_id=core_id, core_public_key_fingerprint=fp,
        node_identity_path=remote_node.path,
        owner_confirmation=f"BIND {core_id} TO NODE {remote_node.node_id}",
    )
    assert tsk.register_trust(remote_node.node_id, trust_level=1.0)


def _live_pair(tmp_path):
    a_id = NodeIdentity(tmp_path / "a-node.json")
    b_id = NodeIdentity(tmp_path / "b-node.json")
    a_core, b_core = "core-A", "core-B"
    a_key, b_key = "public-A", "public-B"
    a_tsk = TrustedSecurityKernel(root=tmp_path / "a-tsk")
    b_tsk = TrustedSecurityKernel(root=tmp_path / "b-tsk")
    _bind(a_tsk, b_core, b_key, b_id)
    _bind(b_tsk, a_core, a_key, a_id)

    # Reserve a loopback port, then hand it to a minimal real TCP accept loop.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    listener.settimeout(0.2)
    port = listener.getsockname()[1]

    a_node = _node(a_core, a_key, a_id, a_tsk, b_core, b_key, b_id, port)
    b_node = _node(b_core, b_key, b_id, b_tsk, a_core, a_key, a_id, 0)
    a = core.P2PNetwork(a_node, scp_identity=a_id)
    b = core.P2PNetwork(b_node, scp_identity=b_id)
    a.scp1_enabled = b.scp1_enabled = True
    a._sync_scp1_trust(); b._sync_scp1_trust()

    stop = threading.Event()
    accepted = []
    def accept_loop():
        while not stop.is_set():
            try: conn, addr = listener.accept()
            except socket.timeout: continue
            except OSError: break
            accepted.append(threading.Thread(target=b._handle_tcp, args=(conn, addr), daemon=True))
            accepted[-1].start()
    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    return a, b, listener, stop, thread, accepted, a_core, b_core


def _open_authenticated_session(pair):
    """Open a raw TCP session and complete the same handshake as send_to()."""
    a, b, listener, *_rest, a_core, b_core = pair
    conn = socket.create_connection(listener.getsockname(), timeout=2)
    conn.settimeout(2)
    peer = a.node.peers.get(b_core)
    handshake = NodeHandshake(
        a.scp_identity,
        scp=SCP1,
        expected_peer_node_id=peer.node_id,
    )
    hello = handshake.hello(core_id=a_core)
    a._send_tcp_frame(conn, {"scp1": hello})

    challenge_wire = a._recv_tcp_frame(conn)
    challenge = a._scp1_receive_checked(
        challenge_wire, "HANDSHAKE", expected_peer_id=peer.node_id
    )
    assert challenge is not None
    challenge_payload, _ = challenge
    assert handshake.accept_challenge(challenge_payload, peer.node_id)

    finish = handshake.finish(core_id=a_core)
    a._send_tcp_frame(conn, {"scp1": finish})
    established_wire = a._recv_tcp_frame(conn)
    established = a._scp1_receive_checked(
        established_wire, "HANDSHAKE", expected_peer_id=peer.node_id
    )
    assert established is not None
    established_payload, _ = established
    assert handshake.accept_established(established_payload, peer.node_id)
    assert handshake.state == NodeHandshake.ESTABLISHED
    return conn, handshake


def _close(pair):
    a, b, listener, stop, thread, accepted, *_ = pair
    stop.set()
    listener.close()
    thread.join(timeout=2)
    for worker in accepted: worker.join(timeout=3)


def test_live_tcp_handshake_and_ping(tmp_path):
    pair = _live_pair(tmp_path)
    a, *_rest, b_core = pair
    try:
        assert a.send_to(b_core, {"action": "PING"})["status"] == "PONG"
    finally:
        _close(pair)


def test_live_tcp_rejects_operation_before_handshake(tmp_path):
    pair = _live_pair(tmp_path)
    a, b, listener, *_ = pair
    conn = socket.create_connection(listener.getsockname(), timeout=2)
    conn.settimeout(2)
    try:
        payload = {"action": "PING", "sender": a.node.identity.id()}
        packet = SCP1.build_payload(
            node_id=a.scp_identity.node_id,
            public_key=a.scp_identity.public_key,
            payload=payload,
            capability="network.send",
            message_type="PING",
        )
        packet = SCP1.sign(a.scp_identity.private_key, packet)
        core.P2PNetwork._send_tcp_frame(conn, {"scp1": packet})
        # The server must close the connection instead of processing PING.
        assert conn.recv(1) == b""
    finally:
        conn.close()
        _close(pair)


def test_live_tcp_rejects_spoofed_sender_after_handshake(tmp_path):
    pair = _live_pair(tmp_path)
    a, *_rest, a_core, b_core = pair
    conn = None
    try:
        conn, handshake = _open_authenticated_session(pair)
        # The packet is genuinely signed by A, but claims that B sent it.
        wire = a._scp1_wrap(
            {
                "action": "PING",
                "sender": b_core,
                "session_id": handshake.session_id,
            },
            message_type="PING",
        )
        a._send_tcp_frame(conn, wire)
        response_wire = a._recv_tcp_frame(conn)
        received = a._scp1_receive_checked(
            response_wire,
            expected_type="RESPONSE",
            expected_peer_id=a.node.peers.get(b_core).node_id,
        )
        assert received is not None
        response, _signer = received
        assert response.get("status") == "UNAUTHORIZED"
        assert response.get("status") != "PONG"
    finally:
        if conn is not None:
            conn.close()
        _close(pair)


def test_live_tcp_rejects_mismatched_core_fingerprint(tmp_path):
    pair = _live_pair(tmp_path)
    a, b, *_rest, _a_core, b_core = pair
    try:
        # Corrupt only the server's persisted PeerDirectory view of A.
        peer = b.node.peers.get(a.node.identity.id())
        peer.public_key = "different-core-public-key"
        assert a.send_to(b_core, {"action": "PING"}) is None
    finally:
        _close(pair)


def test_live_tcp_rejects_replayed_hello_packet(tmp_path):
    pair = _live_pair(tmp_path)
    a, _b, listener, *_rest = pair
    first = second = None
    try:
        peer = a.node.peers.get(pair[-1])
        handshake = NodeHandshake(
            a.scp_identity,
            scp=SCP1,
            expected_peer_node_id=peer.node_id,
        )
        hello_wire = {"scp1": handshake.hello(core_id=pair[-2])}

        first = socket.create_connection(listener.getsockname(), timeout=2)
        first.settimeout(2)
        a._send_tcp_frame(first, hello_wire)
        challenge_wire = a._recv_tcp_frame(first)
        assert a._scp1_receive_checked(
            challenge_wire, "HANDSHAKE", expected_peer_id=peer.node_id
        ) is not None
        # The server has now consumed this HELLO nonce. Closing before FINISH
        # leaves the exact same signed wire available for a replay attempt.
        first.close()
        first = None

        second = socket.create_connection(listener.getsockname(), timeout=2)
        second.settimeout(2)
        a._send_tcp_frame(second, hello_wire)
        assert second.recv(1) == b""
    finally:
        if first is not None:
            first.close()
        if second is not None:
            second.close()
        _close(pair)


def _open_authenticated_client_connection(pair):
    """Open a raw client connection and complete the production handshake."""
    from core.node_handshake import NodeHandshake

    a, b, listener, *_rest, a_core, b_core = pair
    conn = socket.create_connection(listener.getsockname(), timeout=3)
    conn.settimeout(3)
    handshake = NodeHandshake(
        a.scp_identity,
        scp=SCP1,
        expected_peer_node_id=b.scp_identity.node_id,
    )

    hello = handshake.hello(core_id=a_core)
    core.P2PNetwork._send_tcp_frame(conn, {"scp1": hello})

    challenge_wire = core.P2PNetwork._recv_tcp_frame(conn)
    challenge = a._scp1_receive_checked(
        challenge_wire,
        expected_type="HANDSHAKE",
        expected_peer_id=b.scp_identity.node_id,
    )
    assert challenge is not None
    challenge_payload, signer = challenge
    assert a._scp1_verified_peer(b_core, signer) is not None
    assert handshake.accept_challenge(
        challenge_payload, b.scp_identity.node_id
    )

    finish = handshake.finish(core_id=a_core)
    core.P2PNetwork._send_tcp_frame(conn, {"scp1": finish})

    established_wire = core.P2PNetwork._recv_tcp_frame(conn)
    established = a._scp1_receive_checked(
        established_wire,
        expected_type="HANDSHAKE",
        expected_peer_id=b.scp_identity.node_id,
    )
    assert established is not None
    established_payload, signer = established
    assert a._scp1_verified_peer(b_core, signer) is not None
    assert handshake.accept_established(
        established_payload, b.scp_identity.node_id
    )
    return conn, handshake


def _receive_live_response(a, b, b_core, conn):
    response_wire = core.P2PNetwork._recv_tcp_frame(conn)
    received = a._scp1_receive_checked(
        response_wire,
        expected_type="RESPONSE",
        expected_peer_id=b.scp_identity.node_id,
    )
    assert received is not None
    response, signer = received
    assert a._scp1_verified_peer(b_core, signer) is not None
    return response
