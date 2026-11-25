import threading

import symbiont_core as core


class FakeJournal:
    def __init__(self):
        self.events = []

    def append(self, event, data):
        self.events.append((event, data))


class FakeNode:
    def __init__(self):
        self.journal = FakeJournal()
        self.peers = core.PeerDirectory()


def make_network():
    network = core.P2PNetwork(FakeNode())
    network.udp_port = 0
    network.tcp_port = 0
    return network


def test_start_is_idempotent_and_stop_joins_workers(monkeypatch):
    network = make_network()
    entered = threading.Event()

    def worker():
        entered.set()
        network._stop_event.wait()

    monkeypatch.setattr(network, "_udp_listen", worker)
    monkeypatch.setattr(network, "_udp_beacon", worker)
    monkeypatch.setattr(network, "_tcp_server", worker)

    assert network.start() is True
    assert entered.wait(1.0)
    assert network.start() is False

    assert network.stop() is True
    assert network.running is False
    assert not any(thread.is_alive() for thread in network._threads)


def test_worker_spawn_rejected_after_stop():
    network = make_network()
    network.running = False
    network._stop_event.set()

    assert network._spawn_worker(lambda: None) is False
    assert network._threads == set()


def test_socket_registration_rejected_after_stop():
    network = make_network()
    network.running = False
    network._stop_event.set()

    class FakeSocket:
        closed = False

        def close(self):
            self.closed = True

    sock = FakeSocket()
    assert network._register_socket(sock) is False
    assert sock.closed is True
    assert sock not in network._sockets


def test_repeated_stop_is_safe():
    network = make_network()

    assert network.stop() is True
    assert network.stop() is True


def test_real_udp_tcp_workers_start_and_stop():
    network = make_network()

    assert network.start() is True
    assert network.stop() is True
    assert network.running is False
    assert network._sockets == set()
    assert not any(thread.is_alive() for thread in network._threads)


def test_real_network_can_restart_after_stop():
    network = make_network()

    assert network.start() is True
    assert network.stop() is True

    assert network.start() is True
    assert network.stop() is True
    assert network._sockets == set()
