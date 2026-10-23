import tempfile
from pathlib import Path
import symbiont_core as sc

print("=" * 60)
print("STEP 45.8.5: REAL DELEGATED DOUBLE-COMPLETION REPLAY")
print("=" * 60)

root = Path(tempfile.mkdtemp(prefix="symbiont-step45-"))
sym = sc.Symbiont(root=root)

print("\nSMSA:", sym.smsa is not None)
print("SETTLEMENT:", sym.settlement is not None)

assert sym.smsa is not None
assert sym.settlement is not None

sym.economy.credit(25.0, "STEP45 test funding")

peer_id = "worker-B"

sym.peers.peers[peer_id] = sc.Peer(
    peer_id, "", "127.0.0.1", 9999, 0.0,
    "worker-B", "WORKER"
)

calls = {"send": 0}

def fake_send_to(target, packet):
    calls["send"] += 1
    print("P2P delivery:", calls["send"], packet["quest_id"])
    return {
        "status": "COMPLETED",
        "result": "worker completed quest",
    }

sym.p2p.send_to = fake_send_to

print("\n--- FIRST DELEGATION ---")

q, result = sym.quests.delegate(
    "Replay audit",
    "Verify delegated completion replay.",
    25.0,
    peer_id,
)

print("quest:", q.quest_id if q else None)
print("result:", result)
print("economy:", sym.economy.snapshot())
print("escrow:", sym.economy.escrow.get(q.quest_id) if q else None)

assert q is not None
assert result == "worker completed quest"

quest_id = q.quest_id

assert sym.economy.escrow[quest_id]["escrow_state"] == "RELEASED"
assert sym.economy.snapshot()["balance"] == 0.0
assert calls["send"] == 1

events = sym.journal.all_events()

released = [
    e for e in events
    if e.get("type") == "settlement.released"
    and e.get("payload", {}).get("quest_id") == quest_id
]

done = [
    e for e in events
    if e.get("type") == "quest.delegated.done"
    and e.get("payload", {}).get("quest_id") == quest_id
]

print("\nFIRST EVENTS:")
print("settlement.released:", len(released))
print("quest.delegated.done:", len(done))

assert len(released) == 1
assert len(done) == 1

print("\n--- SECOND RELEASE ---")

second = sym.settlement.release(quest_id, peer_id)

print("result:", second)
print("balance:", sym.economy.snapshot()["balance"])

assert second is False
assert sym.economy.snapshot()["balance"] == 0.0

released = [
    e for e in sym.journal.all_events()
    if e.get("type") == "settlement.released"
    and e.get("payload", {}).get("quest_id") == quest_id
]

assert len(released) == 1

print("\n--- RESTART ---")

sym.stop()
sym2 = sc.Symbiont(root=root)

assert sym2.smsa is not None
assert sym2.settlement is not None

valid, count = sym2.journal.verify()

events = sym2.journal.all_events()

released = [
    e for e in events
    if e.get("type") == "settlement.released"
    and e.get("payload", {}).get("quest_id") == quest_id
]

done = [
    e for e in events
    if e.get("type") == "quest.delegated.done"
    and e.get("payload", {}).get("quest_id") == quest_id
]

print("journal.verify:", valid, count)
print("persisted settlement.released:", len(released))
print("persisted quest.delegated.done:", len(done))
print("operations after restart:", sym2.settlement._operations)

assert valid
assert len(released) == 1
assert len(done) == 1

print("\n--- POST-RESTART RELEASE REPLAY ---")

third = sym2.settlement.release(quest_id, peer_id)

print("result:", third)
print("balance:", sym2.economy.snapshot()["balance"])
print("escrow:", sym2.economy.escrow.get(quest_id))

assert third is False
assert sym2.economy.snapshot()["balance"] == 0.0

events = sym2.journal.all_events()

released = [
    e for e in events
    if e.get("type") == "settlement.released"
    and e.get("payload", {}).get("quest_id") == quest_id
]

done = [
    e for e in events
    if e.get("type") == "quest.delegated.done"
    and e.get("payload", {}).get("quest_id") == quest_id
]

print("settlement.released:", len(released))
print("quest.delegated.done:", len(done))

assert len(released) == 1
assert len(done) == 1

print("\n" + "=" * 60)
print("RESULT: PASS")
print("Delegated settlement is idempotent across restart.")
print("No duplicate payment.")
print("No duplicate settlement.released event.")
print("Persistent journal is the replay evidence.")
print("=" * 60)
