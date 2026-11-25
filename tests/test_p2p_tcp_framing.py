import json
import struct

import pytest

from symbiont_core import P2PNetwork


class FragmentedConnection:
    def __init__(self, incoming=b"", chunk_size=3):
        self.incoming = bytearray(incoming)
        self.chunk_size = chunk_size
        self.sent = None

    def recv(self, size):
        if not self.incoming:
            return b""
        count = min(size, self.chunk_size, len(self.incoming))
        result = bytes(self.incoming[:count])
        del self.incoming[:count]
        return result

    def sendall(self, data):
        self.sent = bytes(data)


def test_send_tcp_frame_uses_four_byte_network_order_length():
    conn = FragmentedConnection()
    payload = {"action": "PING", "value": 42}

    P2PNetwork._send_tcp_frame(conn, payload)

    size = struct.unpack("!I", conn.sent[:4])[0]
    body = conn.sent[4:]

    assert size == len(body)
    assert json.loads(body.decode("utf-8")) == payload


def test_recv_tcp_frame_handles_fragmented_header_and_body():
    payload = {"action": "PING", "nested": {"value": 42}}
    body = json.dumps(payload).encode("utf-8")
    wire = struct.pack("!I", len(body)) + body
    conn = FragmentedConnection(wire, chunk_size=2)

    assert P2PNetwork._recv_tcp_frame(conn) == payload


@pytest.mark.parametrize("size", [0, P2PNetwork._TCP_FRAME_MAX + 1])
def test_recv_tcp_frame_rejects_invalid_length(size):
    conn = FragmentedConnection(struct.pack("!I", size))

    with pytest.raises(ValueError):
        P2PNetwork._recv_tcp_frame(conn)


def test_recv_tcp_frame_rejects_non_object_json():
    body = b'["not", "an", "object"]'
    wire = struct.pack("!I", len(body)) + body
    conn = FragmentedConnection(wire)

    with pytest.raises(ValueError):
        P2PNetwork._recv_tcp_frame(conn)


def test_recv_tcp_frame_rejects_incomplete_frame():
    body = b'{"action":"PING"}'
    wire = struct.pack("!I", len(body) + 5) + body
    conn = FragmentedConnection(wire)

    with pytest.raises(ConnectionError):
        P2PNetwork._recv_tcp_frame(conn)
