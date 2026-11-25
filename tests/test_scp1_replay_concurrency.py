import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.crypto_protocol import SCPReplayGuard


def test_same_nonce_is_accepted_only_once_under_thread_race(tmp_path):
    guard = SCPReplayGuard(tmp_path / "replay.json")
    workers = 16
    barrier = threading.Barrier(workers)

    def attempt(_):
        barrier.wait(timeout=5)
        return guard.check_and_store("SYM-race-test", "same-nonce")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(attempt, range(workers)))

    assert sum(results) == 1


def test_corrupted_replay_store_fails_closed(tmp_path):
    path = tmp_path / "replay.json"
    corrupted = b'{"broken": invalid json'
    path.write_bytes(corrupted)

    with pytest.raises(RuntimeError, match="replay"):
        SCPReplayGuard(path)

    assert path.read_bytes() == corrupted


def test_missing_replay_store_starts_empty(tmp_path):
    path = tmp_path / "new-replay.json"
    guard = SCPReplayGuard(path)

    assert guard.count() == 0
    assert not path.exists()


def test_same_nonce_is_accepted_only_once_across_guard_instances(tmp_path):
    path = tmp_path / "shared-replay.json"
    guards = [SCPReplayGuard(path), SCPReplayGuard(path)]

    def attempt(index):
        return guards[index].check_and_store("SYM-shared", "same-nonce")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (0, 1)))

    assert sum(results) == 1

    verifier = SCPReplayGuard(path)
    assert verifier.contains("SYM-shared", "same-nonce")


def test_failed_replay_store_write_does_not_accept_nonce(tmp_path, monkeypatch):
    guard = SCPReplayGuard(tmp_path / "write-failure.json")

    def fail_save():
        raise OSError("simulated replay storage failure")

    monkeypatch.setattr(guard, "_save", fail_save)

    with pytest.raises(OSError, match="replay storage failure"):
        guard.check_and_store("SYM-write-failure", "nonce-1")

    assert not guard.contains("SYM-write-failure", "nonce-1")
