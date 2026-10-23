import os
import tempfile
from pathlib import Path

os.environ["SYMBIONT_SMSA"] = "1"

from symbiont_core import Symbiont

creator_root = Path(tempfile.mkdtemp(prefix="symbiont-creator-"))
worker_root = Path(tempfile.mkdtemp(prefix="symbiont-worker-"))

creator = Symbiont(root=str(creator_root))
worker = Symbiont(root=str(worker_root))

assert creator.smsa is not None
assert creator.smsa.allow("payment.execute") is True

creator.economy.credit(25, "audit funding")

creator_id = creator.identity.id()
worker_id = worker.identity.id()

print("\n=== REAL EARNING PATH AUDIT ===")
print("creator:", creator_id)
print("worker :", worker_id)

print("\n--- INITIAL ---")
print("creator:", creator.economy.snapshot())
print("worker :", worker.economy.snapshot())

def fake_send_to(peer_id, packet):
    assert peer_id == worker_id
    incoming = dict(packet)
    incoming["sender"] = creator_id
    return worker.quests.handle_incoming(incoming)

creator.p2p.send_to = fake_send_to

q, result = creator.quests.delegate(
    "audit earning quest",
    "Проверить существующий путь выплаты за выполненный квест",
    25,
    worker_id,
)

print("\n--- AFTER QUEST ---")
print("quest:", q)
print("result:", result)

print("\n--- CREATOR ---")
print(creator.economy.snapshot())

print("\n--- WORKER ---")
print(worker.economy.snapshot())

print("\n--- ESCROW ---")
print(creator.economy.escrow.get(q.quest_id))

creator_balance = creator.economy.snapshot()["balance"]
worker_balance = worker.economy.snapshot()["balance"]

assert q.status == "completed"
assert creator_balance == 25
assert worker_balance == 0

print("\n=== AUDIT RESULT ===")
print("QUEST COMPLETED: PASS")
print("CREATOR BALANCE:", creator_balance)
print("WORKER BALANCE:", worker_balance)
print("CURRENT PATH DOES NOT PAY WORKER: CONFIRMED")
print("No architecture was changed.")
