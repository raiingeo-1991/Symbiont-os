from pathlib import Path
import re

ROOT = Path(".")
FILES = [
    Path("symbiont_core.py"),
    Path("core/security.py"),
]

PATTERNS = [
    r"\bcredit\s*\(",
    r"\brelease_quest\s*\(",
    r"\brefund_quest\s*\(",
    r"\bfreeze_quest\s*\(",
    r"\breserve_quest\s*\(",
    r"\bsettle_quest_reward\s*\(",
    r"\blifetime_received\b",
    r"\blifetime_spent\b",
    r"\bbalance\b",
    r"\bworker_node\b",
    r"\bcreator_node\b",
    r"\bpayment\.execute\b",
    r"\bsettlement\.(reserve|release|refund|freeze)\b",
]

print("=" * 90)
print("STEP 45.8.14 — MONEY FLOW AUDIT")
print("=" * 90)

for path in FILES:
    if not path.exists():
        print(f"\n[SKIP] {path} not found")
        continue

    print(f"\n{'#' * 90}")
    print(f"# {path}")
    print(f"{'#' * 90}")

    lines = path.read_text(encoding="utf-8").splitlines()

    hits = []
    for i, line in enumerate(lines, 1):
        if any(re.search(p, line) for p in PATTERNS):
            hits.append(i)

    shown = set()

    for line_no in hits:
        start = max(1, line_no - 4)
        end = min(len(lines), line_no + 5)

        key = (start, end)
        if key in shown:
            continue
        shown.add(key)

        print(f"\n--- lines {start}-{end} ---")
        for n in range(start, end + 1):
            marker = ">>>" if n == line_no else "   "
            print(f"{marker} {n:5}: {lines[n-1]}")

print("\n" + "=" * 90)
print("TARGET")
print("=" * 90)
print("""
Найти существующий минимальный путь:

Creator balance
    -> reserve
    -> ESCROW
    -> Worker executes
    -> release
    -> Worker balance

Не добавлять новый архитектурный слой.
Не использовать settle_quest_reward() как доказательство выплаты.
Не исправлять lifetime_received на этом шаге.
Не менять файлы проекта.
""")
