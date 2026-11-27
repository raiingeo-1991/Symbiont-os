"""Isolated candidate-patch evaluation for SSS Active Immunity.

The evaluator never applies candidate patches to the live project tree.
It is a testing harness, not a security boundary for hostile code.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CandidateRejected(ValueError):
    """A candidate is invalid or cannot be safely evaluated."""


class CandidateLab:
    VERSION = "SSS-CANDIDATE-LAB/0.1"

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        if not self.root.is_dir():
            raise ValueError("Project root must be an existing directory")

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _safe_project_file(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root):
            raise CandidateRejected("Path escapes project root")
        if not path.is_file():
            raise CandidateRejected(f"Project file does not exist: {relative_path}")
        return path

    def evaluate_unified_diff(
        self,
        patch_text: str,
        allowed_files: list[str],
        test_paths: list[str],
        timeout_seconds: int = 120,
        support_files: list[str] | None = None,
        allow_local_execution: bool = False,
    ) -> dict[str, Any]:
        """Compare baseline and patched tests in separate disposable copies.

        This protects the project tree from accidental patch/test writes. It is
        not an OS sandbox and must not be used to execute hostile candidate code.
        """
        if not allow_local_execution:
            raise CandidateRejected(
                "Candidate execution is disabled by default; explicitly enable trusted local code only. "
                "This evaluator is not an OS sandbox and must never run untrusted patches."
            )
        if not isinstance(patch_text, str) or not patch_text.strip():
            raise CandidateRejected("Patch text must not be empty")
        if not allowed_files:
            raise CandidateRejected("At least one allowed target file is required")
        if not test_paths:
            raise CandidateRejected("At least one explicit test path is required")
        if timeout_seconds < 1 or timeout_seconds > 600:
            raise CandidateRejected("timeout_seconds must be between 1 and 600")

        support_files = list(support_files or [])
        def normalize_existing(paths: list[str], label: str) -> dict[str, Path]:
            found: dict[str, Path] = {}
            for relative in paths:
                path = self._safe_project_file(relative)
                name = path.relative_to(self.root).as_posix()
                if name in found:
                    raise CandidateRejected(f"Duplicate {label} path: {name}")
                found[name] = path
            return found

        allowed = normalize_existing(allowed_files, "allowed")
        tests_map = normalize_existing(test_paths, "test")
        support_map = normalize_existing(support_files, "support")
        # Preserve pytest's project-level configuration and conftest fixtures.
        # Other application/import dependencies remain explicit support_files.
        config_names = ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")
        auto_support: set[str] = set()
        for config_name in config_names:
            candidate = self.root / config_name
            if candidate.is_file():
                auto_support.add(candidate.relative_to(self.root).as_posix())
        for test_name in tests_map:
            parent = (self.root / test_name).parent
            while parent == self.root or self.root in parent.parents:
                conftest = parent / "conftest.py"
                if conftest.is_file():
                    auto_support.add(conftest.relative_to(self.root).as_posix())
                if parent == self.root:
                    break
                parent = parent.parent
        for name in sorted(auto_support):
            support_map.setdefault(name, self._safe_project_file(name))
        support = sorted(support_map)
        overlap = set(allowed) & (set(tests_map) | set(support_map))
        if overlap:
            raise CandidateRejected(
                "Patch targets cannot be test/support files: " + ", ".join(sorted(overlap))
            )
        tests = sorted(tests_map)
        support = sorted(support_map)
        copy_map = {**allowed, **tests_map, **support_map}
        originals = {name: self._sha256(path.read_bytes()) for name, path in copy_map.items()}
        patch_hash = self._sha256(patch_text.encode("utf-8"))

        patch_targets: set[str] = set()
        pending_old: str | None = None
        def normalize_header(line: str) -> str:
            name = line[4:].split("\t", 1)[0].strip()
            if name == "/dev/null":
                raise CandidateRejected("Creating or deleting files is not allowed")
            if name.startswith(("a/", "b/")):
                name = name[2:]
            if name not in allowed:
                raise CandidateRejected(f"Patch target is not allowed: {name}")
            if name in tests_map or name in support_map:
                raise CandidateRejected(f"Patch cannot target test/support file: {name}")
            return name

        for line in patch_text.splitlines():
            if line.startswith("--- "):
                if pending_old is not None:
                    raise CandidateRejected("Diff has an unmatched old-file header")
                pending_old = normalize_header(line)
                patch_targets.add(pending_old)
            elif line.startswith("+++ "):
                if pending_old is None:
                    raise CandidateRejected("Diff has a new-file header without an old-file header")
                new_name = normalize_header(line)
                patch_targets.add(new_name)
                if pending_old != new_name:
                    raise CandidateRejected(f"Mismatched diff header paths: {pending_old} != {new_name}")
                pending_old = None
        if pending_old is not None:
            raise CandidateRejected("Diff has an unmatched old-file header")
        if not patch_targets:
            raise CandidateRejected("No unified-diff file headers found")

        result: dict[str, Any] = {
            "version": self.VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "patch_sha256": patch_hash,
            "original_sha256": originals,
            "allowed_files": sorted(allowed),
            "patch_targets": sorted(patch_targets),
            "test_paths": tests,
            "support_files": support,
            "accepted": False,
            "reason": None,
            "baseline_tests": None,
            "tests": None,
        }

        def make_copy(destination: Path) -> None:
            destination.mkdir(parents=True, exist_ok=True)
            for name, source in copy_map.items():
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

        def run_tests(cwd: Path, label: str) -> dict[str, Any]:
            report_path = temp_root / f"{label}-junit.xml"
            command = [
                __import__("sys").executable, "-m", "pytest", "-q",
                "--junitxml", str(report_path), *tests,
            ]
            try:
                completed = subprocess.run(
                    command, cwd=cwd, capture_output=True, text=True,
                    timeout=timeout_seconds, check=False,
                )
                cases: dict[str, str] = {}
                collection_errors = False
                if report_path.is_file():
                    try:
                        root = ET.parse(report_path).getroot()
                        for case in root.iter("testcase"):
                            node_id = f"{case.get('classname', '')}::{case.get('name', '')}"
                            if case.find("failure") is not None:
                                outcome = "failed"
                            elif case.find("error") is not None:
                                outcome = "error"
                            elif case.find("skipped") is not None:
                                outcome = "skipped"
                            else:
                                outcome = "passed"
                            cases[node_id] = outcome
                        collection_errors = any(
                            suite.get("errors", "0") not in ("0", "")
                            for suite in root.iter("testsuite")
                        )
                    except (ET.ParseError, OSError):
                        collection_errors = True
                actual_passed = sum(value == "passed" for value in cases.values())
                actual_failed = sum(value in {"failed", "error"} for value in cases.values())
                actual_skipped = sum(value == "skipped" for value in cases.values())
                return {
                    "returncode": completed.returncode,
                    "passed": completed.returncode == 0 and actual_passed > 0
                        and actual_failed == 0 and not collection_errors,
                    "stdout": completed.stdout[-12000:],
                    "stderr": completed.stderr[-12000:],
                    "timed_out": False,
                    "cases": cases,
                    "passed_count": actual_passed,
                    "failed_count": actual_failed,
                    "skipped_count": actual_skipped,
                    "collection_errors": collection_errors,
                    "junit_report_present": report_path.is_file(),
                }
            except subprocess.TimeoutExpired as exc:
                return {
                    "returncode": None, "passed": False,
                    "stdout": str(exc.stdout or "")[-12000:],
                    "stderr": str(exc.stderr or "")[-12000:],
                    "timed_out": True,
                    "cases": {}, "passed_count": 0, "failed_count": 0,
                    "skipped_count": 0, "collection_errors": False,
                    "junit_report_present": False,
                }

        with tempfile.TemporaryDirectory(prefix="sym-candidate-lab-") as temp:
            temp_root = Path(temp)
            baseline_dir = temp_root / "baseline"
            candidate_dir = temp_root / "candidate"
            make_copy(baseline_dir)
            make_copy(candidate_dir)
            result["baseline_tests"] = run_tests(baseline_dir, "baseline")

            patch_file = temp_root / "candidate.patch"
            patch_file.write_text(patch_text, encoding="utf-8")
            try:
                applied = subprocess.run(
                    ["patch", "--batch", "--forward", "-p1", "-i", str(patch_file)],
                    cwd=candidate_dir, capture_output=True, text=True,
                    timeout=timeout_seconds, check=False,
                )
                result["patch_returncode"] = applied.returncode
                result["patch_stdout"] = applied.stdout[-6000:]
                result["patch_stderr"] = applied.stderr[-6000:]
            except subprocess.TimeoutExpired as exc:
                applied = None
                result["reason"] = "patch_application_timed_out"
                result["patch_returncode"] = None
                result["patch_stdout"] = str(exc.stdout or "")[-6000:]
                result["patch_stderr"] = str(exc.stderr or "")[-6000:]
                result["patch_timed_out"] = True
            except OSError as exc:
                applied = None
                result["reason"] = f"patch_tool_unavailable: {type(exc).__name__}: {exc}"

            if applied is not None and applied.returncode == 0:
                result["tests"] = run_tests(candidate_dir, "candidate")
                baseline = result["baseline_tests"]
                candidate = result["tests"]
                baseline_cases = baseline.get("cases", {})
                candidate_cases = candidate.get("cases", {})
                baseline_failures = {
                    node_id for node_id, outcome in baseline_cases.items()
                    if outcome in {"failed", "error"}
                }
                baseline_valid = (
                    not baseline["timed_out"]
                    and baseline["returncode"] not in (None, 0)
                    and not baseline.get("collection_errors")
                    and bool(baseline_failures)
                    and not baseline.get("skipped_count", 0)
                )
                candidate_resolved = all(
                    candidate_cases.get(node_id) == "passed"
                    for node_id in baseline_failures
                )
                no_new_failures = candidate.get("failed_count", 0) == 0
                no_skip_increase = (
                    candidate.get("skipped_count", 0)
                    <= baseline.get("skipped_count", 0)
                )
                candidate_valid = (
                    candidate["passed"] and not candidate["timed_out"]
                    and not candidate.get("collection_errors")
                    and candidate_resolved and no_new_failures
                    and no_skip_increase
                )
                result["baseline_failure_nodeids"] = sorted(baseline_failures)
                result["baseline_failures_resolved"] = candidate_resolved
                result["no_new_failures"] = no_new_failures
                result["no_skip_increase"] = no_skip_increase
                result["accepted"] = bool(baseline_valid and candidate_valid)
                if result["accepted"]:
                    result["reason"] = "baseline_failures_resolved_candidate_suite_passed"
                elif baseline["timed_out"]:
                    result["reason"] = "baseline_tests_timed_out"
                elif baseline.get("collection_errors") or not baseline.get("junit_report_present"):
                    result["reason"] = "baseline_collection_or_reporting_error"
                elif not baseline_failures:
                    result["reason"] = "baseline_has_no_confirmed_test_failures"
                elif not candidate_resolved:
                    result["reason"] = "candidate_did_not_pass_all_baseline_failures"
                elif not no_skip_increase:
                    result["reason"] = "candidate_increased_skipped_tests"
                else:
                    result["reason"] = "candidate_tests_failed_or_timed_out"
            elif applied is not None:
                result["reason"] = "patch_application_failed"
            result["sandbox_discarded"] = True

        current = {name: self._sha256(path.read_bytes()) for name, path in copy_map.items()}
        result["live_files_unchanged"] = current == originals
        if not result["live_files_unchanged"]:
            result["accepted"] = False
            result["reason"] = "live_project_hash_changed"
        return result

    def save_report(self, report: dict[str, Any], report_dir: str | Path) -> Path:
        """Save a unique report without overwriting prior reports."""
        directory = Path(report_dir).resolve()
        if not directory.is_relative_to(self.root):
            raise CandidateRejected("Report directory must be inside project root")
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = directory / f"candidate-report-{stamp}.json"
        payload = {
            "version": self.VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **report,
        }
        with destination.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        return destination
