from pathlib import Path
import ast
import re

FILES = [
    Path("core/security.py"),
    Path("core/scp1_zerotrust.py"),
    Path("core/crypto_protocol.py"),
    Path("core/node_identity.py"),
    Path("core/peer_security.py"),
    Path("core/memory_integrity.py"),
    Path("symbiont_core.py"),
]

TERMS = [
    "ReplayGuard",
    "MessageSigner",
    "AuditLog",
    "IntegrityMonitor",
    "CapabilityGate",
    "OwnerPolicy",
    "SecurePolicy",
    "ZeroTrustNetwork",
    "ModuleRegistry",
    "SMSA",
    "SecureSettlement",
    "GenesisMint",
    "SCP1",
    "get_security",
    "get_smsa",
    "get_secure_settlement",
    "payment.execute",
    "economy.mint",
    "network.send",
    "require",
    "authorize",
    "allow",
    "deny",
    "grant",
    "revoke",
    "replay",
    "nonce",
    "timestamp",
    "signature",
    "sign",
    "verify",
    "audit",
    "integrity",
    "capability",
    "policy",
    "trust",
    "node",
    "packet",
]

print("=" * 120)
print("STEP 45.8.21 — SECURITY DEEP AUDIT")
print("=" * 120)
print("READ ONLY — NO FILES MODIFIED")
print()

# ---------------------------------------------------------------------
# 1. FILE INVENTORY
# ---------------------------------------------------------------------

print("=" * 120)
print("1. SECURITY FILE INVENTORY")
print("=" * 120)

for path in FILES:
    if path.exists():
        print(f"[PRESENT] {path}")
    else:
        print(f"[MISSING] {path}")

# ---------------------------------------------------------------------
# 2. CLASSES / METHODS
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("2. SECURITY CLASSES AND METHODS")
print("=" * 120)

for path in FILES:
    if not path.exists():
        continue

    print()
    print("-" * 120)
    print(path)
    print("-" * 120)

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as e:
        print("AST ERROR:", repr(e))
        continue

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            print(f"\nCLASS {node.name} [line {node.lineno}]")

            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = []

                    for a in item.args.args:
                        if a.arg != "self":
                            args.append(a.arg)

                    print(
                        f"  {item.name}"
                        f"({', '.join(args)})"
                        f" [line {item.lineno}]"
                    )

# ---------------------------------------------------------------------
# 3. SECURITY CALL GRAPH — SIMPLE STATIC DISCOVERY
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("3. SECURITY CALLS / CONNECTION POINTS")
print("=" * 120)

for path in FILES:
    if not path.exists():
        continue

    print()
    print("-" * 120)
    print(path)
    print("-" * 120)

    lines = path.read_text(encoding="utf-8").splitlines()

    for i, line in enumerate(lines, 1):
        if any(term.lower() in line.lower() for term in TERMS):
            print(f"{i:5}: {line}")

# ---------------------------------------------------------------------
# 4. SECURITY OBJECT CONSTRUCTION
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("4. SECURITY OBJECT CONSTRUCTION")
print("=" * 120)

constructors = [
    "SMSA(",
    "SecurityManager(",
    "CapabilityGate(",
    "ReplayGuard(",
    "MessageSigner(",
    "AuditLog(",
    "IntegrityMonitor(",
    "OwnerPolicy(",
    "SecurePolicy(",
    "ZeroTrustNetwork(",
    "ModuleRegistry(",
    "SecureSettlement(",
    "GenesisMint(",
    "SCP1(",
    "MemoryIntegrity(",
]

for path in FILES:
    if not path.exists():
        continue

    lines = path.read_text(encoding="utf-8").splitlines()

    for i, line in enumerate(lines, 1):
        if any(x in line for x in constructors):
            print(f"{path}:{i}: {line.strip()}")

# ---------------------------------------------------------------------
# 5. SECURITY REQUIREMENTS
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("5. CAPABILITY REQUIREMENTS")
print("=" * 120)

for path in FILES:
    if not path.exists():
        continue

    lines = path.read_text(encoding="utf-8").splitlines()

    for i, line in enumerate(lines, 1):
        if (
            "require(" in line
            or "authorize(" in line
            or "allowed(" in line
            or "check(" in line
        ):
            print(f"{path}:{i}: {line.strip()}")

# ---------------------------------------------------------------------
# 6. REPLAY / NONCE / TIMESTAMP
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("6. REPLAY / NONCE / TIMESTAMP MECHANISMS")
print("=" * 120)

replay_terms = [
    "ReplayGuard",
    "replay",
    "nonce",
    "timestamp",
    "ttl",
    "check(",
]

for path in FILES:
    if not path.exists():
        continue

    lines = path.read_text(encoding="utf-8").splitlines()

    for i, line in enumerate(lines, 1):
        if any(x.lower() in line.lower() for x in replay_terms):
            print(f"{path}:{i}: {line.strip()}")

# ---------------------------------------------------------------------
# 7. SIGNATURE / CRYPTO
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("7. SIGNATURE / CRYPTOGRAPHIC VERIFICATION")
print("=" * 120)

crypto_terms = [
    "sign(",
    "verify(",
    "signature",
    "hmac",
    "ed25519",
    "public_key",
    "private_key",
    "secret_key",
    "MessageSigner",
    "NodeIdentity",
    "SCP1",
]

for path in FILES:
    if not path.exists():
        continue

    lines = path.read_text(encoding="utf-8").splitlines()

    for i, line in enumerate(lines, 1):
        if any(x.lower() in line.lower() for x in crypto_terms):
            print(f"{path}:{i}: {line.strip()}")

# ---------------------------------------------------------------------
# 8. AUDIT / INTEGRITY
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("8. AUDIT / INTEGRITY")
print("=" * 120)

audit_terms = [
    "AuditLog",
    "audit.record",
    "integrity",
    "fingerprint",
    "register(",
    "verify_file",
    "protect_file",
]

for path in FILES:
    if not path.exists():
        continue

    lines = path.read_text(encoding="utf-8").splitlines()

    for i, line in enumerate(lines, 1):
        if any(x.lower() in line.lower() for x in audit_terms):
            print(f"{path}:{i}: {line.strip()}")

# ---------------------------------------------------------------------
# 9. MONEY / SETTLEMENT SECURITY
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("9. MONEY / SETTLEMENT SECURITY CONNECTIONS")
print("=" * 120)

money_terms = [
    "SecureSettlement",
    "payment.execute",
    "economy.mint",
    "reserve_quest",
    "release_quest",
    "refund_quest",
    "freeze_quest",
    "settle_quest_reward",
    "credit(",
    "debit(",
    "escrow",
    "worker_node",
    "creator_node",
    "reward",
    "operation_id",
]

for path in FILES:
    if not path.exists():
        continue

    lines = path.read_text(encoding="utf-8").splitlines()

    for i, line in enumerate(lines, 1):
        if any(x.lower() in line.lower() for x in money_terms):
            print(f"{path}:{i}: {line.strip()}")

# ---------------------------------------------------------------------
# 10. ENVIRONMENT FLAGS
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("10. SECURITY ENVIRONMENT FLAGS")
print("=" * 120)

import os

found = False

for key in sorted(os.environ):
    if any(
        x in key.upper()
        for x in (
            "SMSA",
            "SCP",
            "SECURITY",
            "TRUST",
            "PERMISSION",
            "CRYPTO",
            "ZERO",
        )
    ):
        print(f"{key}={os.environ[key]}")
        found = True

if not found:
    print("(none)")

# ---------------------------------------------------------------------
# 11. POTENTIALLY UNCONNECTED SECURITY MODULES
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("11. POTENTIALLY UNCONNECTED SECURITY MODULES")
print("=" * 120)

module_names = [
    "ZeroTrustNetwork",
    "ModuleRegistry",
    "GenesisMint",
    "ReplayGuard",
    "MessageSigner",
    "IntegrityMonitor",
    "MemoryIntegrity",
    "SCP1",
]

all_source = ""

for path in FILES:
    if path.exists():
        all_source += "\n" + path.read_text(encoding="utf-8")

for name in module_names:
    occurrences = len(re.findall(r"\b" + re.escape(name) + r"\b", all_source))
    print(f"{name:24} occurrences={occurrences}")

# ---------------------------------------------------------------------
# 12. SPECIAL CHECKS
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("12. SPECIAL SECURITY CHECKS")
print("=" * 120)

checks = {
    "Core Identity.verify implementation":
        "return bool(signature) and len(signature) >= 32",

    "SMSA HMAC verification":
        "hmac.compare_digest",

    "SecureSettlement authorization":
        'require("payment.execute")',

    "GenesisMint authorization":
        'require(self.CAPABILITY)',

    "ReplayGuard":
        "self.replay.check",

    "SCP1 verification":
        "self.scp1.verify",

    "Core journal verification":
        "journal.verify",

    "Memory integrity":
        "MemoryIntegrity(",
}

for name, needle in checks.items():
    present = needle in all_source
    print(f"{'FOUND' if present else 'NOT FOUND':10} {name}")
    print(f"           {needle}")

# ---------------------------------------------------------------------
# END
# ---------------------------------------------------------------------

print()
print("=" * 120)
print("STEP 45.8.21 COMPLETE")
print("READ ONLY — NO FILES MODIFIED")
print("=" * 120)
