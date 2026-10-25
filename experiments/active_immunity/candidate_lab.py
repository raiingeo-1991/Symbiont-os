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
    ) -> dict[str, Any]:
        """Apply a unified diff only in a temporary copy, then run selected tests.

        Only explicitly listed existing project files may be changed.
        Test paths must also be existing project files. The project root is
        never used as the patch target or pytest working directory.
        """
        if not isinstance(patch_text, str) or not patch_text.strip():
            raise CandidateRejected("Patch text must not be empty")
        if not allowed_files:
            raise CandidateRejected("At least one allowed target file is required")
        if not test_paths:
            raise CandidateRejected("At least one explicit test path is required")
        if timeout_seconds < 1 or timeout_seconds > 600:
            raise CandidateRejected("timeout_seconds must be between 1 and 600")

        allowed: dict[str, Path] = {}
        for relative in allowed_files:
            path = self._safe_project_file(relative)
            normalized = path.relative_to(self.root).as_posix()
            if normalized in allowed:
                raise CandidateRejected(f"Duplicate allowed path: {normalized}")
            allowed[normalized] = path

        tests: list[str] = []
        for relative in test_paths:
            path = self._safe_project_file(relative)
            tests.append(path.relative_to(self.root).as_posix())

        # Validate unified-diff headers as ordered old/new pairs.
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
            return name

        for line in patch_text.splitlines():
            if line.startswith("--- "):
                if pending_old is not None:
                    raise CandidateRejected("Diff has an unmatched old-file header")
                pending_old = normalize_header(line)
                patch_targets.add(pending_old)
            elif line.startswith("+++ "):
                if pending_old is None:
                    raise CandidateRejected(
                        "Diff has a new-file header without an old-file header"
                    )
                new_name = normalize_header(line)
                patch_targets.add(new_name)
                if pending_old != new_name:
                    raise CandidateRejected(
                        f"Mismatched diff header paths: {pending_old} != {new_name}"
                    )
                pending_old = None

        if pending_old is not None:
            raise CandidateRejected("Diff has an unmatched old-file header")

        if not patch_targets:
            raise CandidateRejected("No unified-diff file headers found")

        originals = {
            name: self._sha256(path.read_bytes())
            for name, path in allowed.items()
        }
        patch_hash = self._sha256(patch_text.encode("utf-8"))

        result: dict[str, Any] = {
            "version": self.VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "patch_sha256": patch_hash,
            "original_sha256": originals,
            "allowed_files": sorted(allowed),
            "patch_targets": sorted(patch_targets),
            "test_paths": tests,
            "accepted": False,
            "reason": None,
            "tests": None,
        }

        with tempfile.TemporaryDirectory(prefix="sym-candidate-lab-") as temp:
            sandbox = Path(temp) / "project"
            sandbox.mkdir()

            # Copy only the explicitly allowed files and requested tests.
            copy_names = set(allowed)
            copy_names.update(tests)
            for name in sorted(copy_names):
                source = self._safe_project_file(name)
                destination = sandbox / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

            patch_file = Path(temp) / "candidate.patch"
            patch_file.write_text(patch_text, encoding="utf-8")

            try:
                apply = subprocess.run(
                    ["patch", "--batch", "--forward", "-p1", "-i", str(patch_file)],
                    cwd=sandbox,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                result["patch_returncode"] = apply.returncode
                result["patch_stdout"] = apply.stdout[-6000:]
                result["patch_stderr"] = apply.stderr[-6000:]
            except subprocess.TimeoutExpired as exc:
                result["reason"] = "patch_application_timed_out"
                result["patch_returncode"] = None
                result["patch_stdout"] = str(exc.stdout or "")[-6000:]
                result["patch_stderr"] = str(exc.stderr or "")[-6000:]
                result["patch_timed_out"] = True
                result["sandbox_discarded"] = True
                apply = None

            if apply is None or apply.returncode != 0:
                if apply is not None:
                    result["reason"] = "patch_application_failed"
                result["sandbox_discarded"] = True
            else:

                # Ensure only explicitly permitted targets changed.
                unauthorized_change = False
                for name in copy_names:
                    copied = sandbox / name
                    if name in allowed:
                        continue
                    original_bytes = self._safe_project_file(name).read_bytes()
                    if copied.read_bytes() != original_bytes:
                        unauthorized_change = True
                        break

                if unauthorized_change:
                    result["reason"] = "non_target_file_changed"
                else:
                    command = [
                        __import__("sys").executable, "-m", "pytest", "-q", *tests
                    ]
                    try:
                        tested = subprocess.run(
                            command,
                            cwd=sandbox,
                            capture_output=True,
                            text=True,
                            timeout=timeout_seconds,
                            check=False,
                        )
                        result["tests"] = {
                            "returncode": tested.returncode,
                            "passed": tested.returncode == 0,
                            "stdout": tested.stdout[-12000:],
                            "stderr": tested.stderr[-12000:],
                            "timed_out": False,
                        }
                    except subprocess.TimeoutExpired as exc:
                        result["tests"] = {
                            "returncode": None,
                            "passed": False,
                            "stdout": str(exc.stdout or "")[-12000:],
                            "stderr": str(exc.stderr or "")[-12000:],
                            "timed_out": True,
                        }

                    result["accepted"] = bool(
                        result["tests"]["passed"] and not result["tests"]["timed_out"]
                    )
                    result["reason"] = (
                        "tests_passed_in_temporary_copy"
                        if result["accepted"]
                        else "tests_failed_or_timed_out"
                    )
                result["sandbox_discarded"] = True

        # Reconfirm that the live project files were not changed.
        current = {
            name: self._sha256(path.read_bytes())
            for name, path in allowed.items()
        }
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
