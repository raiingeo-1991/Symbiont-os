import pytest

from core.node_identity import NodeIdentity
from core.node_handshake import NodeHandshake


def make_pair(tmp_path):
    a = NodeIdentity(tmp_path / "a.json")
    b = NodeIdentity(tmp_path / "b.json")
    return a, b


def test_mutual_handshake_reaches_established(tmp_path):
    a, b = make_pair(tmp_path)

    client = NodeHandshake(a, expected_peer_node_id=b.node_id)
    server = NodeHandshake(b)

    hello = client.hello()
    challenge = server.create_challenge(
        hello["payload"], a.node_id
    )

    assert challenge is not None
    assert server.state == server.CHALLENGE_SENT

    assert client.accept_challenge(
        challenge["payload"], b.node_id
    )
    assert client.state == client.CHALLENGE_RECEIVED

    finish = client.finish()

    assert server.accept_finish(
        finish["payload"], a.node_id
    )
    assert server.state == server.ESTABLISHED

    established = server.established()

    assert client.accept_established(
        established["payload"], b.node_id
    )
    assert client.state == client.ESTABLISHED
    assert client.session_id == server.session_id


def test_handshake_rejects_wrong_challenge(tmp_path):
    a, b = make_pair(tmp_path)

    client = NodeHandshake(a, expected_peer_node_id=b.node_id)
    server = NodeHandshake(b)

    hello = client.hello()
    challenge = server.create_challenge(
        hello["payload"], a.node_id
    )

    forged = dict(challenge["payload"])
    forged["challenge"] = "wrong-challenge-value"

    assert not client.accept_challenge(forged, b.node_id)
    assert client.state == client.REJECTED


def test_handshake_rejects_wrong_peer(tmp_path):
    a, b = make_pair(tmp_path)
    other = NodeIdentity(tmp_path / "other.json")

    client = NodeHandshake(a, expected_peer_node_id=b.node_id)
    server = NodeHandshake(b)

    hello = client.hello()
    challenge = server.create_challenge(
        hello["payload"], a.node_id
    )

    assert not client.accept_challenge(
        challenge["payload"], other.node_id
    )
    assert client.state == client.REJECTED


def test_handshake_rejects_finish_without_challenge(tmp_path):
    a, b = make_pair(tmp_path)

    server = NodeHandshake(b)

    assert not server.accept_finish(
        {
            "handshake": server.VERSION,
            "action": "FINISH",
            "hello_id": "fake",
            "session_id": "SES-fake",
            "challenge": "fake",
        },
        a.node_id,
    )
    assert server.state == server.REJECTED


def test_handshake_rejects_out_of_order_messages(tmp_path):
    a, _ = make_pair(tmp_path)

    client = NodeHandshake(a)

    with pytest.raises(RuntimeError):
        client.finish()

    assert client.state == client.IDLE


def test_handshake_rejects_replayed_hello(tmp_path):
    a, b = make_pair(tmp_path)
    client = NodeHandshake(a)
    server = NodeHandshake(b)

    hello = client.hello()
    assert server.create_challenge(hello["payload"], a.node_id)
    assert server.create_challenge(hello["payload"], a.node_id) is None
    assert server.state == server.REJECTED


def test_handshake_rejects_missing_session_id(tmp_path):
    a, b = make_pair(tmp_path)
    client = NodeHandshake(a, expected_peer_node_id=b.node_id)
    server = NodeHandshake(b)

    hello = client.hello()
    payload = dict(hello["payload"])
    payload["session_id"] = None

    assert server.create_challenge(payload, a.node_id) is None
    assert server.state == server.REJECTED


def test_handshake_rejects_wrong_established_peer(tmp_path):
    a, b = make_pair(tmp_path)
    other = NodeIdentity(tmp_path / "other.json")

    client = NodeHandshake(a, expected_peer_node_id=b.node_id)
    server = NodeHandshake(b)

    hello = client.hello()
    challenge = server.create_challenge(hello["payload"], a.node_id)
    assert client.accept_challenge(challenge["payload"], b.node_id)

    finish = client.finish()
    assert server.accept_finish(finish["payload"], a.node_id)

    established = server.established()
    assert not client.accept_established(
        established["payload"], other.node_id
    )
    assert client.state == client.REJECTED


def test_handshake_rejects_substituted_session_id(tmp_path):
    a, b = make_pair(tmp_path)

    client = NodeHandshake(a, expected_peer_node_id=b.node_id)
    server = NodeHandshake(b)

    hello = client.hello()
    original_session_id = client.session_id

    challenge = server.create_challenge(
        hello["payload"], a.node_id
    )
    assert challenge is not None

    forged = dict(challenge["payload"])
    forged["session_id"] = "SES-" + "0" * 48

    assert forged["session_id"] != original_session_id
    assert not client.accept_challenge(forged, b.node_id)
    assert client.state == client.REJECTED
    assert client.session_id == original_session_id
