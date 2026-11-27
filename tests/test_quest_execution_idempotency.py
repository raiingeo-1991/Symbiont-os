import threading
import sqlite3

import pytest
import time
from types import SimpleNamespace

from symbiont_core import EventJournal, PermissionGate, QuestBoard


class FakeIdentity:
    def id(self):
        return "worker-node"


class FakeBodies:
    def battery(self):
        return 90


class FakeMind:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
        self.lock = threading.Lock()

    def think(self, _description):
        with self.lock:
            self.calls += 1
        time.sleep(0.03)
        if self.fail:
            raise RuntimeError("simulated crash")
        return {"response": "done"}


class FakeMemory:
    def remember(self, *args, **kwargs):
        return "memory-id"


def make_board(tmp_path, allow=True, fail=False):
    permissions = PermissionGate()
    if allow:
        permissions.allow("task_execution")
    node = SimpleNamespace(
        permissions=permissions,
        identity=FakeIdentity(),
        bodies=FakeBodies(),
        mind=FakeMind(fail=fail),
        memory=FakeMemory(),
        journal=EventJournal(tmp_path / "events.log"),
    )
    return QuestBoard(node), node


def packet():
    return {
        "quest_id": "same-quest",
        "description": "perform one task",
        "reward": 5,
        "sender": "creator-node",
        "title": "test",
    }


def test_duplicate_concurrent_quest_executes_once(tmp_path):
    board, node = make_board(tmp_path)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(board.handle_incoming(packet())))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert node.mind.calls == 1
    assert sum(result["status"] == "COMPLETED" for result in results) == 1
    assert sum(result["status"] == "REPLAYED" for result in results) == 1


def test_quest_execution_denied_without_permission(tmp_path):
    board, node = make_board(tmp_path, allow=False)
    result = board.handle_incoming(packet())
    assert result["status"] == "REJECTED"
    assert result["reason"] == "task_execution_permission_denied"
    assert node.mind.calls == 0


def test_crashed_started_quest_is_not_executed_again(tmp_path):
    board, node = make_board(tmp_path, fail=True)
    try:
        board.handle_incoming(packet())
    except RuntimeError:
        pass
    result = board.handle_incoming(packet())
    assert result["status"] == "IN_PROGRESS_OR_RECOVERY_REQUIRED"
    assert node.mind.calls == 1


def test_separate_quest_board_instances_share_durable_claim(tmp_path):
    first_board, first_node = make_board(tmp_path)
    second_permissions = PermissionGate()
    second_permissions.allow("task_execution")
    second_node = SimpleNamespace(
        permissions=second_permissions,
        identity=FakeIdentity(),
        bodies=FakeBodies(),
        mind=first_node.mind,
        memory=FakeMemory(),
        journal=EventJournal(tmp_path / "events.log"),
    )
    second_board = QuestBoard(second_node)

    results = []
    threads = [
        threading.Thread(target=lambda: results.append(first_board.handle_incoming(packet()))),
        threading.Thread(target=lambda: results.append(second_board.handle_incoming(packet()))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert first_node.mind.calls == 1
    assert sum(result["status"] == "COMPLETED" for result in results) == 1
    assert sum(result["status"] in {"REPLAYED", "IN_PROGRESS_OR_RECOVERY_REQUIRED"}
               for result in results) == 1


def test_durable_quest_claim_survives_restart_before_journal_started_event(tmp_path):
    board, node = make_board(tmp_path)
    claimed = board._claim_incoming_quest("crash-window-quest")
    assert claimed is None

    restarted_node = SimpleNamespace(
        permissions=node.permissions,
        identity=node.identity,
        bodies=node.bodies,
        mind=node.mind,
        memory=node.memory,
        journal=EventJournal(tmp_path / "events.log"),
    )
    restarted = QuestBoard(restarted_node)
    assert restarted._claim_incoming_quest("crash-window-quest") == "started"


def test_durable_quest_claim_is_atomic_across_processes(tmp_path):
    import subprocess
    import sys

    worker = r'''import sys
from pathlib import Path
from types import SimpleNamespace
from symbiont_core import EventJournal, PermissionGate, QuestBoard
class Identity:
    def id(self): return "worker-node"
class Bodies:
    def battery(self): return 90
class Mind:
    def think(self, _description): return {"response": "done"}
class Memory:
    def remember(self, *args, **kwargs): return "memory-id"
root = Path(sys.argv[1])
permissions = PermissionGate()
permissions.allow("task_execution")
node = SimpleNamespace(
    permissions=permissions, identity=Identity(), bodies=Bodies(),
    mind=Mind(), memory=Memory(), journal=EventJournal(root / "events.log"),
)
board = QuestBoard(node)
claim = board._claim_incoming_quest("cross-process-quest")
print("CLAIMED" if claim is None else claim)
'''
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", worker, str(tmp_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=30) for process in processes]

    assert all(process.returncode == 0 for process in processes), results
    statuses = [stdout.strip() for stdout, _stderr in results]
    assert statuses.count("CLAIMED") == 1
    assert statuses.count("started") == 1


@pytest.mark.parametrize("reward", [0, -1, float("nan"), float("inf"), "not-a-number", True])
def test_invalid_quest_rewards_are_rejected_before_claim_or_execution(tmp_path, reward):
    board, node = make_board(tmp_path)
    incoming = packet()
    incoming["reward"] = reward

    result = board.handle_incoming(incoming)

    assert result["status"] == "REJECTED"
    assert result["reason"] == "invalid_quest_reward"
    assert node.mind.calls == 0
    with sqlite3.connect(str(board._incoming_db_path)) as db:
        assert db.execute("SELECT COUNT(*) FROM incoming_quests").fetchone()[0] == 0


def test_corrupt_quest_claim_status_fails_closed(tmp_path):
    board, node = make_board(tmp_path)
    with sqlite3.connect(str(board._incoming_db_path)) as db:
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(
            "INSERT INTO incoming_quests(quest_id,status,updated_at) VALUES(?,?,?)",
            ("same-quest", "unknown", "2026-11-27T00:00:00+00:00"),
        )
        db.commit()

    result = board.handle_incoming(packet())

    assert result["status"] == "REJECTED"
    assert result["reason"] == "quest_claim_storage_unavailable"
    assert node.mind.calls == 0
