import json

import symbiont_core as core


class FakeConnection:
    def __init__(self):
        self.sent = None
        self.closed = False

    def sendall(self, data):
        self.sent = data

    def close(self):
        self.closed = True


def make_legacy_disabled_network():
    network = object.__new__(core.P2PNetwork)
    network.scp1_enabled = False
    return network


def test_incoming_legacy_tcp_is_rejected_before_request_processing():
    network = make_legacy_disabled_network()
    connection = FakeConnection()

    network._handle_tcp(connection, ("127.0.0.1", 12345))

    response = json.loads(connection.sent.decode("utf-8"))

    assert response["status"] == "UNAUTHORIZED"
    assert response["reason"] == "scp1_required"
    assert connection.closed is True


def test_outgoing_legacy_send_is_rejected_without_socket_or_packet_mutation():
    network = make_legacy_disabled_network()
    packet = {"action": "PING"}
    original = dict(packet)

    result = network.send_to("untrusted-peer", packet)

    assert result is None
    assert packet == original
