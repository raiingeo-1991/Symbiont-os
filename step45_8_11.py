from pathlib import Path
import json
import tempfile
import os

from symbiont_core import Symbiont

print("=" * 60)
print("STEP 45.8.11: REAL FREEZE / REFUND / RESTART AUDIT")
print("=" * 60)

root = Path(tempfile.mkdtemp(prefix="symbiont-escrow-refund-"))

os.environ["SYMBIONT_SMSA"] = "1"

sym = Symbiont(root=str(root))

# ------------------------------------------------------------
# FUND
# ------------------------------------------------------------
sym.economy.credit(25, "audit funding")

before = sym.economy.snapshot()
print("\n--- FUNDING ---")
print("economy BEFORE:", before)

# ------------------------------------------------------------
# RESERVE
# ------------------------------------------------------------
quest_id = "audit-refund-" + __import__("uuid").uuid4().hex

reserved = sym.settlement.reserve(
    quest_id,
    25,
    creator_node=sym.identity.id(),
    worker_node="worker-B",
)

print("\n--- RESERVE ---")
print("reserved:", reserved)
print("economy:", sym.economy.snapshot())
print("escrow:", sym.economy.escrow.get(quest_id))

assert reserved is True
assert sym.economy.snapshot()["balance"] == 0.0
assert sym.economy.escrow[quest_id]["escrow_state"] == "ESCROW"

# ------------------------------------------------------------
# FREEZE
# ------------------------------------------------------------
frozen = sym.settlement.freeze(
    quest_id,
    "audit freeze",
)

print("\n--- FREEZE ---")
print("frozen:", frozen)
print("economy:", sym.economy.snapshot())
print("escrow:", sym.economy.escrow.get(quest_id))

assert frozen is True
assert sym.economy.snapshot()["balance"] == 0.0
assert sym.economy.escrow[quest_id]["escrow_state"] == "FROZEN"

# ------------------------------------------------------------
# RESTART
# ------------------------------------------------------------
del sym

sym2 = Symbiont(root=str(root))

print("\n--- POST-RESTART FROZEN STATE ---")
print("economy:", sym2.economy.snapshot())
print("escrow:", sym2.economy.escrow.get(quest_id))

assert sym2.economy.escrow[quest_id]["escrow_state"] == "FROZEN"
assert sym2.economy.snapshot()["balance"] == 0.0

# ------------------------------------------------------------
# REFUND
# ------------------------------------------------------------
refunded = sym2.settlement.refund(quest_id)

print("\n--- REFUND ---")
print("refunded:", refunded)
print("economy:", sym2.economy.snapshot())
print("escrow:", sym2.economy.escrow.get(quest_id))

assert refunded == 25.0
assert sym2.economy.snapshot()["balance"] == 25.0
assert sym2.economy.escrow[quest_id]["escrow_state"] == "REFUNDED"

# ------------------------------------------------------------
# SECOND REFUND
# ------------------------------------------------------------
second = sym2.settlement.refund(quest_id)

print("\n--- SECOND REFUND ---")
print("result:", second)
print("economy:", sym2.economy.snapshot())

assert second is False
assert sym2.economy.snapshot()["balance"] == 25.0

# ------------------------------------------------------------
# SECOND RESTART
# ------------------------------------------------------------
del sym2

sym3 = Symbiont(root=str(root))

print("\n--- POST-REFUND RESTART ---")
print("economy:", sym3.economy.snapshot())
print("escrow:", sym3.economy.escrow.get(quest_id))

assert sym3.economy.snapshot()["balance"] == 25.0
assert sym3.economy.escrow[quest_id]["escrow_state"] == "REFUNDED"

# ------------------------------------------------------------
# POST-RESTART REFUND REPLAY
# ------------------------------------------------------------
third = sym3.settlement.refund(quest_id)

print("\n--- POST-RESTART REFUND REPLAY ---")
print("result:", third)
print("economy:", sym3.economy.snapshot())

assert third is False
assert sym3.economy.snapshot()["balance"] == 25.0

# ------------------------------------------------------------
# JOURNALS
# ------------------------------------------------------------
events = []
events_path = sym3.journal.path

if events_path.exists():
    for line in events_path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except Exception:
            pass

core_refunds = [
    e for e in events
    if e.get("type") == "economy.escrow_refunded"
    and e.get("payload", {}).get("quest_id") == quest_id
]

core_freezes = [
    e for e in events
    if e.get("type") == "economy.escrow_frozen"
    and e.get("payload", {}).get("quest_id") == quest_id
]

audit_path = Path(sym3.smsa.audit.path)

audit = []
audit_path = Path(sym3.smsa.audit.path)

if audit_path.exists():
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            if entry.get("data", {}).get("quest_id") == quest_id:
                audit.append(entry)
        except Exception:
            pass

audit_refunds = [
    e for e in audit
    if e.get("event") == "settlement.refunded"
    and e.get("payload", {}).get("quest_id") == quest_id
]

audit_freezes = [
    e for e in audit
    if e.get("event") == "settlement.frozen"
    and e.get("payload", {}).get("quest_id") == quest_id
]

print("\n--- JOURNALS ---")
print("CORE escrow_frozen:", len(core_freezes))
print("CORE escrow_refunded:", len(core_refunds))
print("SMSA settlement.frozen:", len(audit_freezes))
print("SMSA settlement.refunded:", len(audit_refunds))

assert len(core_freezes) == 1
assert len(core_refunds) == 1
assert len(audit_freezes) == 1
assert len(audit_refunds) == 1

print("\n" + "=" * 60)
print("RESULT: PASS")
print("Reserve deducted funds into escrow.")
print("Freeze survived restart.")
print("Refund returned the escrowed reward exactly once.")
print("Second refund was rejected.")
print("Post-restart refund replay was rejected.")
print("Core journal and SMSA audit journal both verified.")
print("No new persistence layer.")
print("=" * 60)
