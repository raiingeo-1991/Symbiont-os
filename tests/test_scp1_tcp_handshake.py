import socket
import threading

from core.crypto_protocol import SCP1, SCPReplayGuard
from core.node_identity import NodeIdentity
from core.node_handshake import NodeHandshake
from core.scp1_zerotrust import SCP1ZeroTrust
from symbiont_core import P2PNetwork


def make_wire(identity, payload):
    packet = SCP1.build_payload(
        node_id=identity.node_id,
        public_key=identity.public_key,
        payload=payload,
        capability="network.send",
        message_type="HANDSHAKE",
    )
    return {"scp1": SCP1.sign(identity.private_key, packet)}


def verify_wire(zerotrust, wire, expected_node_id):
    packet = wire["scp1"]
    assert packet["type"] == "HANDSHAKE"
    assert packet["capability"] == "network.send"
    assert zerotrust.verify(packet)
    assert packet["node_id"] == expected_node_id
    return packet["payload"]


def test_mutual_scp1_handshake_over_tcp_frames(tmp_path):
    client_identity = NodeIdentity(tmp_path / "client.json")
    server_identity = NodeIdentity(tmp_path / "server.json")

    client_zt = SCP1ZeroTrust(
        [server_identity.node_id],
        SCPReplayGuard(tmp_path / "client-replay.json"),
    )
    server_zt = SCP1ZeroTrust(
        [client_identity.node_id],
        SCPReplayGuard(tmp_path / "server-replay.json"),
    )

    client_conn, server_conn = socket.socketpair()
    client_conn.settimeout(5)
    server_conn.settimeout(5)

    server_result = {}

    def server_flow():
        try:
            hello_wire = P2PNetwork._recv_tcp_frame(server_conn)
            hello = verify_wire(
                server_zt, hello_wire, client_identity.node_id
            )

            handshake = NodeHandshake(
                server_identity,
                expected_peer_node_id=client_identity.node_id,
            )
            challenge = handshake.create_challenge(
                hello, client_identity.node_id
            )
            assert challenge is not None

            P2PNetwork._send_tcp_frame(
                server_conn, {"scp1": challenge}
            )

            finish_wire = P2PNetwork._recv_tcp_frame(server_conn)
            finish = verify_wire(
                server_zt, finish_wire, client_identity.node_id
            )
            assert handshake.accept_finish(
                finish, client_identity.node_id
            )

            established = handshake.established()
            P2PNetwork._send_tcp_frame(
                server_conn, {"scp1": established}
            )
            server_result["session_id"] = handshake.session_id
            server_result["state"] = handshake.state
        except Exception as exc:
            server_result["error"] = repr(exc)
        finally:
            server_conn.close()

    thread = threading.Thread(target=server_flow)
    thread.start()

    try:
        client = NodeHandshake(
            client_identity,
            expected_peer_node_id=server_identity.node_id,
        )

        hello = client.hello(core_id="core-client")
        P2PNetwork._send_tcp_frame(
            client_conn, {"scp1": hello}
        )

        challenge_wire = P2PNetwork._recv_tcp_frame(client_conn)
        challenge = verify_wire(
            client_zt, challenge_wire, server_identity.node_id
        )
        assert client.accept_challenge(
            challenge, server_identity.node_id
        )

        finish = client.finish(core_id="core-client")
        P2PNetwork._send_tcp_frame(
            client_conn, {"scp1": finish}
        )

        established_wire = P2PNetwork._recv_tcp_frame(client_conn)
        established = verify_wire(
            client_zt, established_wire, server_identity.node_id
        )
        assert client.accept_established(
            established, server_identity.node_id
        )
    finally:
        client_conn.close()
        thread.join(timeout=6)

    assert not thread.is_alive()
    assert "error" not in server_result, server_result.get("error")
    assert client.state == client.ESTABLISHED
    assert server_result["state"] == NodeHandshake.ESTABLISHED
    assert client.session_id == server_result["session_id"]
