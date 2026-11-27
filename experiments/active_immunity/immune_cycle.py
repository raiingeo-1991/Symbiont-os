"""SSS Active Immunity v0.1 — read-only risk discovery prototype.

This module does not modify source code or apply patches.
It reports candidate risks for subsequent isolated reproduction.
"""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from experiments.active_immunity.candidate_lab import CandidateLab
except Exception:
    from candidate_lab import CandidateLab


class ImmuneCycle:
    VERSION = "SSS-ACTIVE-IMMUNITY/0.2"

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
        """Disabled: never execute tests with the live project as cwd."""
        raise RuntimeError(
            "Live-project pytest execution is disabled; use evaluate_candidate_patch()"
        )

    def evaluate_candidate_patch(
        self,
        patch_text: str,
        allowed_files: list[str],
        test_paths: list[str],
        support_files: list[str] | None = None,
        timeout_seconds: int = 120,
        allow_local_execution: bool = False,
    ) -> dict[str, Any]:
        """Evaluate explicitly trusted local code in disposable copies.

        This is not a security sandbox. Untrusted or remote candidate patches
        must not be executed until an OS-level sandbox is integrated.
        """
        return CandidateLab(self.root).evaluate_unified_diff(
            patch_text=patch_text,
            allowed_files=allowed_files,
            test_paths=test_paths,
            support_files=support_files,
            timeout_seconds=timeout_seconds,
            allow_local_execution=allow_local_execution,
        )

    def record_candidate_evaluation(
        self, memory: Any, finding: dict[str, Any], evaluation: dict[str, Any]
    ) -> dict[str, str]:
        """Record an observed candidate evaluation as a fact, accepted or not."""
        if evaluation.get("live_files_unchanged") is not True:
            raise ValueError("Candidate evaluation did not preserve live files")
        patch_hash = str(evaluation.get("patch_sha256", "")).lower()
        source_hashes = evaluation.get("original_sha256")
        baseline = evaluation.get("baseline_tests")
        candidate = evaluation.get("tests")
        if len(patch_hash) != 64 or not isinstance(source_hashes, dict):
            raise ValueError("Candidate evaluation is missing patch/source hashes")
        if not isinstance(baseline, dict) or not isinstance(candidate, dict):
            raise ValueError("Candidate evaluation is missing baseline/candidate results")
        if not source_hashes or any(
            len(str(value)) != 64 for value in source_hashes.values()
        ):
            raise ValueError("Candidate evaluation contains invalid source hashes")

        payload = {
            "rule_id": finding.get("rule_id"),
            "method": finding.get("method"),
            "patch_sha256": patch_hash,
            "original_sha256": source_hashes,
            "test_paths": evaluation.get("test_paths", []),
            "support_files": evaluation.get("support_files", []),
            "accepted": bool(evaluation.get("accepted")),
            "reason": evaluation.get("reason"),
            "baseline_tests": baseline,
            "tests": candidate,
            "live_files_unchanged": True,
        }
        incident_digest = self._sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        )
        evidence_id = memory.record_evidence(
            source_event_id="immune-candidate-" + incident_digest,
            source_event_type="immune.candidate.evaluated",
            source_event_hash=patch_hash,
            evidence_kind="fact",
            summary=("Candidate patch evaluation: " +
                     ("accepted" if payload["accepted"] else "not accepted")),
            incident_id=incident_digest,
            details=payload,
        )
        return {"evidence_id": evidence_id, "incident_id": incident_digest}

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
        """Verify durable outbox recovery after an injected journal failure."""
        import tempfile

        from symbiont_core import Economy, EventJournal

        with tempfile.TemporaryDirectory(prefix="sym-immune-repro-") as temp:
            root = Path(temp)
            state_path = root / "state.json"
            journal_path = root / "events.log"
            journal = EventJournal(journal_path)
            economy = Economy(state_path, journal)

            def injected_failure(*args, **kwargs):
                raise OSError("SIMULATED_JOURNAL_FAILURE")

            journal.append = injected_failure
            economy.credit(10, "isolated immune outbox reproduction")
            error_text = economy.last_outbox_error or ""
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            persisted_balance = persisted["wallet"]["balance"]
            pending_before_restart = len(persisted.get("journal_outbox", []))

            restored_journal = EventJournal(journal_path)
            restored = Economy(state_path, restored_journal)
            journal_valid, event_count = restored_journal.verify()
            pending_after_restart = len(restored.journal_outbox)
            economy_event_count = sum(
                event.get("type") == "economy.credit"
                for event in restored_journal.all_events()
            )

            confirmed = (
                "OSError" in error_text
                and persisted_balance == 10.0
                and restored.wallet.balance == 10.0
                and pending_before_restart == 1
                and pending_after_restart == 0
                and journal_valid
                and event_count == 1
                and economy_event_count == 1
            )
            return {
                "confirmed": confirmed,
                "scenario": "credit_outbox_recovery_after_journal_failure",
                "failure": "SIMULATED_JOURNAL_FAILURE",
                "exception_type": "OSError" if "OSError" in error_text else None,
                "persisted_balance": persisted_balance,
                "balance_after_restart": restored.wallet.balance,
                "journal_valid": journal_valid,
                "journal_event_count": event_count,
                "economy_credit_event_count": economy_event_count,
                "outbox_pending_before_restart": pending_before_restart,
                "outbox_pending_after_restart": pending_after_restart,
                "isolation": "temporary_directory",
            }
