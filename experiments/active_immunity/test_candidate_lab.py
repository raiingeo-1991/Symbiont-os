from pathlib import Path

import pytest

from experiments.active_immunity.candidate_lab import (
    CandidateLab,
    CandidateRejected,
)


def make_project(root: Path):
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "test_app.py").write_text(
        "from app import VALUE\n"
        "def test_value():\n"
        "    assert VALUE == 2\n",
        encoding="utf-8",
    )


def valid_patch():
    return (
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1 +1 @@\n"
        "-VALUE = 1\n"
        "+VALUE = 2\n"
    )


def test_valid_candidate_runs_only_in_temporary_copy(tmp_path):
    make_project(tmp_path)
    original = (tmp_path / "app.py").read_bytes()

    result = CandidateLab(tmp_path).evaluate_unified_diff(
        valid_patch(),
        allowed_files=["app.py"],
        test_paths=["test_app.py"],
    )

    assert result["accepted"] is True
    assert result["tests"]["passed"] is True
    assert result["live_files_unchanged"] is True
    assert (tmp_path / "app.py").read_bytes() == original


def test_candidate_rejects_unauthorized_patch_target(tmp_path):
    make_project(tmp_path)
    lab = CandidateLab(tmp_path)
    patch = valid_patch().replace("app.py", "../outside.py")

    with pytest.raises(CandidateRejected):
        lab.evaluate_unified_diff(
            patch,
            allowed_files=["app.py"],
            test_paths=["test_app.py"],
        )


def test_failed_patch_is_rejected_and_live_source_stays_unchanged(tmp_path):
    make_project(tmp_path)
    original = (tmp_path / "app.py").read_bytes()
    bad_patch = valid_patch().replace("VALUE = 1", "VALUE = 999")

    result = CandidateLab(tmp_path).evaluate_unified_diff(
        bad_patch,
        allowed_files=["app.py"],
        test_paths=["test_app.py"],
    )

    assert result["accepted"] is False
    assert (tmp_path / "app.py").read_bytes() == original


def test_report_directory_outside_project_is_rejected_before_creation(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    make_project(project)
    outside = tmp_path / "must-not-be-created"
    with pytest.raises(CandidateRejected):
        CandidateLab(project).save_report({"example": True}, outside)
    assert not outside.exists()


def test_report_is_saved_inside_project_without_overwrite(tmp_path):
    make_project(tmp_path)
    lab = CandidateLab(tmp_path)
    reports = tmp_path / "reports"
    first = lab.save_report({"case": 1}, reports)
    second = lab.save_report({"case": 2}, reports)
    assert first.is_file() and second.is_file()
    assert first != second
    assert '"case": 1' in first.read_text(encoding="utf-8")
    assert '"case": 2' in second.read_text(encoding="utf-8")


def test_failed_patch_reports_live_files_unchanged(tmp_path):
    make_project(tmp_path)
    original = (tmp_path / "app.py").read_bytes()

    result = CandidateLab(tmp_path).evaluate_unified_diff(
        valid_patch().replace("VALUE = 1", "VALUE = 999"),
        allowed_files=["app.py"],
        test_paths=["test_app.py"],
    )

    assert result["accepted"] is False
    assert result["reason"] == "patch_application_failed"
    assert result["live_files_unchanged"] is True
    assert (tmp_path / "app.py").read_bytes() == original


def test_patch_timeout_is_handled_and_live_files_remain_unchanged(
    tmp_path, monkeypatch
):
    import subprocess
    from experiments.active_immunity import candidate_lab as candidate_module

    make_project(tmp_path)
    original = (tmp_path / "app.py").read_bytes()
    real_run = subprocess.run

    def timeout_patch(command, *args, **kwargs):
        if command and command[0] == "patch":
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout", 1))
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(candidate_module.subprocess, "run", timeout_patch)

    result = CandidateLab(tmp_path).evaluate_unified_diff(
        valid_patch(),
        allowed_files=["app.py"],
        test_paths=["test_app.py"],
        timeout_seconds=2,
    )

    assert result["accepted"] is False
    assert result["reason"] == "patch_application_timed_out"
    assert result["patch_timed_out"] is True
    assert result["sandbox_discarded"] is True
    assert result["live_files_unchanged"] is True
    assert (tmp_path / "app.py").read_bytes() == original


def test_candidate_rejects_mismatched_diff_header_paths(tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("OTHER = 1\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import VALUE\n"
        "def test_value():\n"
        "    assert VALUE == 2\n",
        encoding="utf-8",
    )
    mismatched_patch = (
        "--- a/app.py\n"
        "+++ b/other.py\n"
        "@@ -1 +1 @@\n"
        "-VALUE = 1\n"
        "+VALUE = 2\n"
    )

    with pytest.raises(CandidateRejected):
        CandidateLab(tmp_path).evaluate_unified_diff(
            mismatched_patch,
            allowed_files=["app.py", "other.py"],
            test_paths=["test_app.py"],
        )
