from types import SimpleNamespace

import symbiont_core as core


def test_p2p_source_rate_limit_is_per_source_and_channel():
    node = SimpleNamespace(peers=core.PeerDirectory())
    network = core.P2PNetwork(node)
    network._tcp_rate_limit = 2
    network._udp_rate_limit = 1

    assert network._allow_source(("192.0.2.10", 1234), "tcp")
    assert network._allow_source(("192.0.2.10", 4321), "tcp")
    assert not network._allow_source(("192.0.2.10", 9999), "tcp")
    assert network._allow_source(("192.0.2.11", 1234), "tcp")
    assert network._allow_source(("192.0.2.10", 1234), "udp")
    assert not network._allow_source(("192.0.2.10", 4321), "udp")


def test_p2p_rate_limit_releases_expired_entries(monkeypatch):
    node = SimpleNamespace(peers=core.PeerDirectory())
    network = core.P2PNetwork(node)
    network._tcp_rate_limit = 1
    clock = [100.0]
    monkeypatch.setattr(core.time, "monotonic", lambda: clock[0])

    assert network._allow_source("198.51.100.8", "tcp")
    assert not network._allow_source("198.51.100.8", "tcp")
    clock[0] += network._rate_window_seconds + 0.1
    assert network._allow_source("198.51.100.8", "tcp")


def test_p2p_rate_limit_has_hard_memory_cap_and_reclaims_expired_sources(monkeypatch):
    node = SimpleNamespace(peers=core.PeerDirectory())
    network = core.P2PNetwork(node)
    clock = [100.0]
    monkeypatch.setattr(core.time, "monotonic", lambda: clock[0])

    cap = network._source_rate_max_entries
    for index in range(cap):
        assert network._allow_source(f"198.51.{index // 256}.{index % 256}", "udp")
    assert len(network._source_rate) == cap
    assert not network._allow_source("203.0.113.250", "udp")
    assert len(network._source_rate) == cap

    clock[0] += network._rate_window_seconds + 0.1
    assert network._allow_source("203.0.113.250", "udp")
    assert len(network._source_rate) == 1
