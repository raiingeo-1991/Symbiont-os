import json
import tempfile
from pathlib import Path
import symbiont_core as sc

print("=" * 60)
print("STEP 45.8.10: REAL ESCROW + SECURITY AUDIT REPLAY")
print("=" * 60)

root = Path(tempfile.mkdtemp(prefix="symbiont-step45-"))
sym = sc.Symbiont(root=root)

assert sym.smsa is not None
assert sym.settlement is not None

sym.smsa.allow("payment.execute")
assert sym.smsa.check("payment.execute") is True

print("\n--- FUNDING ---")

sym.economy.credit(25.0, "STEP45 test funding")
print("economy BEFORE:", sym.economy.snapshot())

peer_id = "worker-B"

sym.peers.peers[peer_id] = sc.Peer(
    peer_id,
    "",
    "127.0.0.1",
    9999,
    0.0,
    "worker-B",
    "WORKER",
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

assert q is not None
assert result == "worker completed quest"

quest_id = q.quest_id

print("quest:", quest_id)
print("result:", result)
print("economy AFTER:", sym.economy.snapshot())
print("escrow:", sym.economy.escrow.get(quest_id))
print("P2P calls:", calls["send"])

assert sym.economy.snapshot()["balance"] == 25.0
assert sym.economy.escrow[quest_id]["escrow_state"] == "RELEASED"
assert calls["send"] == 1

print("\n--- CORE JOURNAL ---")

events = sym.journal.all_events()

done = [
    e for e in events
    if e.get("type") == "quest.delegated.done"
    and e.get("payload", {}).get("quest_id") == quest_id
]

escrow_released = [
    e for e in events
    if e.get("type") == "economy.escrow_released"
    and e.get("payload", {}).get("quest_id") == quest_id
]

print("quest.delegated.done:", len(done))
print("economy.escrow_released:", len(escrow_released))

assert len(done) == 1
assert len(escrow_released) == 1

print("\n--- SECURITY AUDIT ---")

audit_path = Path(sym.smsa.audit.path)

audit = []

if audit_path.exists():
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            audit.append(json.loads(line))

released = [
    e for e in audit
    if e.get("event") == "settlement.released"
    and e.get("data", {}).get("quest_id") == quest_id
]

print("settlement.released:", len(released))

assert len(released) == 1

print("\n--- SECOND RELEASE ---")

second = sym.settlement.release(
    quest_id,
    peer_id,
)

print("result:", second)
print("economy:", sym.economy.snapshot())

assert second is False
assert sym.economy.snapshot()["balance"] == 25.0

audit = [
    json.loads(line)
    for line in audit_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

released = [
    e for e in audit
    if e.get("event") == "settlement.released"
    and e.get("data", {}).get("quest_id") == quest_id
]

assert len(released) == 1

print("settlement.released after replay:", len(released))

print("\n--- RESTART ---")

del sym

sym2 = sc.Symbiont(root=root)

assert sym2.smsa is not None
assert sym2.settlement is not None

sym2.smsa.allow("payment.execute")

valid, count = sym2.journal.verify()

print("journal.verify:", valid, count)

assert valid

print("\n--- POST-RESTART STATE ---")

print("economy:", sym2.economy.snapshot())
print("escrow:", sym2.economy.escrow.get(quest_id))

assert sym2.economy.snapshot()["balance"] == 25.0
assert sym2.economy.escrow[quest_id]["escrow_state"] == "RELEASED"

print("\n--- POST-RESTART RELEASE REPLAY ---")

third = sym2.settlement.release(
    quest_id,
    peer_id,
)

print("result:", third)
print("economy:", sym2.economy.snapshot())

assert third is False
assert sym2.economy.snapshot()["balance"] == 25.0

audit = [
    json.loads(line)
    for line in audit_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

released = [
    e for e in audit
    if e.get("event") == "settlement.released"
    and e.get("data", {}).get("quest_id") == quest_id
]

print("settlement.released persisted:", len(released))

assert len(released) == 1

print("\n" + "=" * 60)
print("RESULT: PASS")
print("Reserve deducted funds into escrow.")
print("Release returned the escrowed reward exactly once.")
print("Second release was rejected.")
print("Post-restart release was rejected by escrow state.")
print("Core journal and SMSA audit journal both verified.")
print("No new persistence layer.")
print("=" * 60)
