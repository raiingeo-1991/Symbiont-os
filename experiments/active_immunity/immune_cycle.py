"""SSS Active Immunity v0.1 — read-only risk discovery prototype.

This module does not modify source code or apply patches.
It reports candidate risks for subsequent isolated reproduction.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ImmuneCycle:
    VERSION = "SSS-ACTIVE-IMMUNITY/0.1"

    def __init__(self, project_root: str | Path, report_dir: str | Path):
        self.root = Path(project_root).resolve()
        self.report_dir = Path(report_dir).resolve()

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def discover_economy_write_order(
        self, relative_path: str = "symbiont_core.py"
    ) -> dict[str, Any]:
        """Find Economy methods that save state before appending an event."""
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Source path must remain inside project root")

        raw = path.read_bytes()
        tree = ast.parse(raw, filename=str(path))
        findings = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name != "Economy":
                continue

            for method in node.body:
                if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                calls = []
                for item in ast.walk(method):
                    if not isinstance(item, ast.Call):
                        continue
                    func = item.func
                    if isinstance(func, ast.Attribute):
                        if isinstance(func.value, ast.Name) and func.value.id == "self":
                            if func.attr in {"_save", "append"}:
                                calls.append((item.lineno, func.attr))
                        elif (
                            isinstance(func.value, ast.Attribute)
                            and isinstance(func.value.value, ast.Name)
                            and func.value.value.id == "self"
                            and func.value.attr == "journal"
                            and func.attr == "append"
                        ):
                            calls.append((item.lineno, "journal.append"))

                save_lines = [line for line, name in calls if name == "_save"]
                append_lines = [
                    line for line, name in calls if name == "journal.append"
                ]

                if save_lines and append_lines and min(save_lines) < max(append_lines):
                    findings.append({
                        "rule_id": "ECONOMY-SAVE-BEFORE-JOURNAL",
                        "method": method.name,
                        "line": min(save_lines),
                        "save_lines": sorted(save_lines),
                        "journal_append_lines": sorted(append_lines),
                        "severity": "review",
                        "status": "candidate",
                        "reason": (
                            "Persisted state may change before event append "
                            "succeeds; verify with a controlled failure test."
                        ),
                    })

        return {
            "rule_id": "ECONOMY-SAVE-BEFORE-JOURNAL",
            "source": str(path.relative_to(self.root)),
            "source_sha256": self._sha256(raw),
            "findings": findings,
            "finding_count": len(findings),
        }

    def run_pytest(
        self,
        test_paths: list[str],
        timeout_seconds: int = 120,
    ) -> dict[str, Any]:
        """Run explicitly selected tests; never modifies source or applies patches."""
        if not test_paths:
            raise ValueError("At least one explicit test path is required")
        if timeout_seconds < 1 or timeout_seconds > 600:
            raise ValueError("timeout_seconds must be between 1 and 600")

        safe_paths = []
        for item in test_paths:
            path = (self.root / item).resolve()
            if not path.is_relative_to(self.root):
                raise ValueError("Test path must remain inside project root")
            if not path.is_file():
                raise FileNotFoundError(path)
            safe_paths.append(str(path))

        command = [
            sys.executable, "-m", "pytest", "-q", *safe_paths
        ]
        try:
            result = subprocess.run(
                command,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            return {
                "command": command,
                "returncode": result.returncode,
                "passed": result.returncode == 0,
                "stdout": result.stdout[-12000:],
                "stderr": result.stderr[-12000:],
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "command": command,
                "returncode": None,
                "passed": False,
                "stdout": str(exc.stdout or "")[-12000:],
                "stderr": str(exc.stderr or "")[-12000:],
                "timed_out": True,
            }

    def save_report(self, report: dict[str, Any]) -> Path:
        """Write a new uniquely named report; never overwrite an existing report."""
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        report = {
            "version": self.VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **report,
        }
        path = self.report_dir / f"immune-report-{timestamp}.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        return path

    def record_reproduction(
        self,
        memory: Any,
        finding: dict[str, Any],
        reproduction: dict[str, Any],
    ) -> str:
        """Record a confirmed reproduction as hash-chained immune evidence."""
        if reproduction.get("confirmed") is not True:
            raise ValueError("Only confirmed reproductions may be recorded as facts")

        source_hash = str(finding.get("source_sha256", "")).lower()
        if len(source_hash) != 64 or any(
            ch not in "0123456789abcdef" for ch in source_hash
        ):
            raise ValueError("Finding must include a valid source SHA-256")

        rule_id = str(finding.get("rule_id", "")).strip()
        method = str(finding.get("method", "")).strip()
        if not rule_id or not method:
            raise ValueError("Finding must identify its rule and method")

        reproduction_json = json.dumps(
            reproduction, sort_keys=True, ensure_ascii=False, default=str
        )
        incident_digest = self._sha256(
            (source_hash + "|" + rule_id + "|" + method + "|" +
             reproduction_json).encode("utf-8")
        )
        source_event_id = "immune-repro-" + incident_digest

        return memory.record_evidence(
            source_event_id=source_event_id,
            source_event_type="immune.reproduction.confirmed",
            source_event_hash=source_hash,
            evidence_kind="fact",
            summary=f"Confirmed reproduction: {rule_id} in Economy.{method}",
            incident_id=incident_digest,
            details={
                "rule_id": rule_id,
                "method": method,
                "finding": finding,
                "reproduction": reproduction,
            },
        )


    def reproduce_credit_journal_failure(self) -> dict[str, Any]:
        """Reproduce save-before-journal failure using disposable state."""
        import tempfile

        # Import the implementation under test, but never use its live state.
        from symbiont_core import Economy, EventJournal

        with tempfile.TemporaryDirectory(prefix="sym-immune-repro-") as temp:
            root = Path(temp)
            state_path = root / "state.json"
            journal_path = root / "events.log"

            journal = EventJournal(journal_path)
            economy = Economy(state_path, journal)
            error_type = None

            def injected_failure(*args, **kwargs):
                raise OSError("SIMULATED_JOURNAL_FAILURE")

            journal.append = injected_failure

            try:
                economy.credit(10, "isolated immune reproduction")
            except OSError as exc:
                error_type = type(exc).__name__

            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            persisted_balance = persisted["wallet"]["balance"]

            restored_journal = EventJournal(journal_path)
            restored = Economy(state_path, restored_journal)
            journal_valid, event_count = restored_journal.verify()

            confirmed = (
                error_type == "OSError"
                and persisted_balance == 10.0
                and restored.wallet.balance == 10.0
                and journal_valid
                and event_count == 0
            )

            return {
                "confirmed": confirmed,
                "scenario": "credit_state_saved_before_journal_failure",
                "failure": "SIMULATED_JOURNAL_FAILURE",
                "exception_type": error_type,
                "persisted_balance": persisted_balance,
                "balance_after_restart": restored.wallet.balance,
                "journal_valid": journal_valid,
                "journal_event_count": event_count,
                "isolation": "temporary_directory",
            }
