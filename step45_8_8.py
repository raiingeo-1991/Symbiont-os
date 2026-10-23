import tempfile
from pathlib import Path
import symbiont_core as sc

print("=" * 60)
print("STEP 45.8.8: REAL DELEGATED DOUBLE-COMPLETION REPLAY")
print("=" * 60)

root = Path(tempfile.mkdtemp(prefix="symbiont-step45-"))
sym = sc.Symbiont(root=root)

print("\n--- SECURITY ---")
print("SMSA:", sym.smsa is not None)
print("SETTLEMENT:", sym.settlement is not None)

assert sym.smsa is not None
assert sym.settlement is not None

print("payment.execute BEFORE:",
      sym.smsa.check("payment.execute"))

# Use the existing SMSA authorization path.
sym.smsa.allow("payment.execute")

print("payment.execute AFTER:",
      sym.smsa.check("payment.execute"))

assert sym.smsa.check("payment.execute") is True

print("\n--- FUNDING ---")

sym.economy.credit(
    25.0,
    "STEP45 test funding",
)

print("economy:", sym.economy.snapshot())

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

    print(
        "P2P delivery:",
        calls["send"],
        packet["quest_id"],
    )

    return {
        "status": "COMPLETED",
        "result": "worker completed quest",
    }

# Transport only is replaced.
# QuestBoard.delegate() and SecureSettlement remain real.
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
print(
    "escrow:",
    sym.economy.escrow.get(q.quest_id) if q else None,
)
print("P2P calls:", calls["send"])

assert q is not None
assert result == "worker completed quest"

quest_id = q.quest_id

assert (
    sym.economy.escrow[quest_id]["escrow_state"]
    == "RELEASED"
)

assert sym.economy.snapshot()["balance"] == 25.0
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

print("\n--- FIRST COMPLETION EVENTS ---")
print("settlement.released:", len(released))
print("quest.delegated.done:", len(done))

assert len(released) == 1
assert len(done) == 1

print("\n--- SECOND RELEASE ---")

second = sym.settlement.release(
    quest_id,
    peer_id,
)

print("result:", second)
print("balance:", sym.economy.snapshot()["balance"])

assert second is False
assert sym.economy.snapshot()["balance"] == 25.0

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

# Restore authorization through the real SMSA path
# after constructing the new runtime.
sym2.smsa.allow("payment.execute")

assert sym2.smsa.check("payment.execute") is True

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
print(
    "operations after restart:",
    sym2.settlement._operations,
)

assert valid
assert len(released) == 1
assert len(done) == 1

print("\n--- POST-RESTART RELEASE REPLAY ---")

third = sym2.settlement.release(
    quest_id,
    peer_id,
)

print("result:", third)
print("balance:", sym2.economy.snapshot()["balance"])
print(
    "escrow:",
    sym2.economy.escrow.get(quest_id),
)

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
print("No new persistence layer.")
print("=" * 60)
