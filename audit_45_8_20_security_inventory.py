from pathlib import Path
import ast

FILES = [
    Path("core/security.py"),
    Path("symbiont_core.py"),
]

print("=" * 110)
print("STEP 45.8.20 — SECURITY INVENTORY / CONNECTION AUDIT")
print("=" * 110)

for path in FILES:
    print("\n" + "#" * 110)
    print(f"# FILE: {path}")
    print("#" * 110)

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            print(f"\nCLASS {node.name}  [line {node.lineno}]")

            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [
                        a.arg
                        for a in item.args.args
                        if a.arg != "self"
                    ]

                    print(
                        f"  METHOD {item.name}"
                        f"({', '.join(args)})"
                        f"  [line {item.lineno}]"
                    )

print("\n" + "=" * 110)
print("SECURITY-RELATED SYMBOLS / CALLS")
print("=" * 110)

terms = [
    "SMSA",
    "CapabilityGate",
    "OwnerPolicy",
    "SecurePolicy",
    "AuditLog",
    "ReplayGuard",
    "MessageSigner",
    "IntegrityMonitor",
    "SecurityManager",
    "get_security",
    "get_secure_settlement",
    "payment.execute",
    "require(",
    "allow(",
    "deny(",
    "grant(",
    "revoke(",
    "replay",
    "audit",
    "signature",
    "verify(",
    "sign(",
    "scp1",
    "capability",
    "policy",
    "integrity",
]

for path in FILES:
    lines = path.read_text(encoding="utf-8").splitlines()

    print("\n" + "-" * 110)
    print(f"{path}")
    print("-" * 110)

    for i, line in enumerate(lines, 1):
        if any(term.lower() in line.lower() for term in terms):
            print(f"{i:5}: {line}")

print("\n" + "=" * 110)
print("SECURITY FILES / MODULES PRESENT")
print("=" * 110)

for p in sorted(Path(".").rglob("*.py")):
    name = str(p)

    if any(
        x in name.lower()
        for x in (
            "security",
            "smsa",
            "zerotrust",
            "crypto",
            "scp",
            "identity",
            "permission",
            "replay",
            "audit",
            "integrity",
        )
    ):
        print(name)

print("\n" + "=" * 110)
print("ENVIRONMENT SECURITY FLAGS")
print("=" * 110)

import os

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
        )
    ):
        print(f"{key}={os.environ[key]}")

print("\n" + "=" * 110)
print("NO FILES MODIFIED")
print("=" * 110)
