import os
import tempfile
from pathlib import Path

os.environ["SYMBIONT_SMSA"] = "1"

from symbiont_core import Symbiont


def snap(sym):
    s = sym.economy.snapshot()
    return {
        "balance": float(s["balance"]),
        "lifetime_received": float(s["lifetime_received"]),
        "lifetime_spent": float(s["lifetime_spent"]),
    }


creator_root = Path(tempfile.mkdtemp(prefix="symbiont-earning-creator-"))
worker_root = Path(tempfile.mkdtemp(prefix="symbiont-earning-worker-"))

creator = Symbiont(root=str(creator_root))
worker = Symbiont(root=str(worker_root))

assert creator.smsa is not None
assert worker.smsa is not None

assert creator.smsa.allow("payment.execute") is True
assert worker.smsa.allow("payment.execute") is True

creator.economy.credit(25, "earning contract funding")

creator_id = creator.identity.id()
worker_id = worker.identity.id()

print("\n" + "=" * 80)
print("STEP 45.8.13 — REAL EARNING CONTRACT")
print("=" * 80)

print("\nIDENTITIES")
print("creator:", creator_id)
print("worker :", worker_id)

print("\n1. INITIAL FUNDING")
print("creator:", snap(creator))
print("worker :", snap(worker))

assert snap(creator)["balance"] == 25.0
assert snap(worker)["balance"] == 0.0

# Existing P2P path is represented here without changing Core architecture.
# The only thing this fake transport does is deliver the existing QUEST_OFFER.
def fake_send_to(peer_id, packet):
    assert peer_id == worker_id

    incoming = dict(packet)
    incoming["sender"] = creator_id

    return worker.quests.handle_incoming(incoming)


creator.p2p.send_to = fake_send_to

print("\n2. CREATE + EXECUTE QUEST")

q, result = creator.quests.delegate(
    "earning-contract",
    "Выполнить оплачиваемую работу",
    25,
    worker_id,
)

print("quest status:", q.status)
print("result:", result)

assert q.status == "completed"

print("\n3. CURRENT SETTLEMENT STATE")
print("creator:", snap(creator))
print("worker :", snap(worker))
print("escrow :", creator.economy.escrow.get(q.quest_id))

print("\n4. REQUIRED POST-SETTLEMENT CONTRACT")

creator_balance = snap(creator)["balance"]
worker_balance = snap(worker)["balance"]

print("REQUIRED creator balance = 0")
print("ACTUAL   creator balance =", creator_balance)

print("REQUIRED worker balance  = 25")
print("ACTUAL   worker balance  =", worker_balance)

# These assertions intentionally encode the desired future contract.
assert creator_balance == 0.0, (
    "CONTRACT NOT IMPLEMENTED: creator still owns the released reward"
)

assert worker_balance == 25.0, (
    "CONTRACT NOT IMPLEMENTED: worker did not receive the reward"
)

print("\n5. MONEY CONSERVATION")

total = creator_balance + worker_balance
print("total balance:", total)

assert total == 25.0

print("\n6. RESTART WORKER")

del worker

worker = Symbiont(root=str(worker_root))

print("worker after restart:", snap(worker))

assert snap(worker)["balance"] == 25.0

print("\n7. RESTART CREATOR")

del creator

creator = Symbiont(root=str(creator_root))

print("creator after restart:", snap(creator))
print("escrow after restart :", creator.economy.escrow.get(q.quest_id))

assert snap(creator)["balance"] == 0.0

print("\n8. REPLAY PROTECTION")

before_worker = snap(worker)["balance"]

replay = creator.settlement.release(
    q.quest_id,
    worker_id,
)

print("creator release replay:", replay)
print("worker balance:", snap(worker)["balance"])

assert replay is False
assert snap(worker)["balance"] == before_worker

print("\n9. FINAL CONTRACT")

print("REAL EARNING CONTRACT: PASS")
print("creator balance:", snap(creator)["balance"])
print("worker balance :", snap(worker)["balance"])
print("total          :", snap(creator)["balance"] + snap(worker)["balance"])
