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
        allow_local_execution=True,
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
            allow_local_execution=True,
        )


def test_failed_patch_is_rejected_and_live_source_stays_unchanged(tmp_path):
    make_project(tmp_path)
    original = (tmp_path / "app.py").read_bytes()
    bad_patch = valid_patch().replace("VALUE = 1", "VALUE = 999")

    result = CandidateLab(tmp_path).evaluate_unified_diff(
        bad_patch,
        allowed_files=["app.py"],
        test_paths=["test_app.py"],
        allow_local_execution=True,
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
        allow_local_execution=True,
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
        allow_local_execution=True,
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
            allow_local_execution=True,
        )


def test_baseline_must_fail_before_candidate_can_be_accepted(tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import VALUE\ndef test_value():\n    assert VALUE == 1\n",
        encoding="utf-8",
    )
    result = CandidateLab(tmp_path).evaluate_unified_diff(
        valid_patch(), allowed_files=["app.py"], test_paths=["test_app.py"],
        allow_local_execution=True,
    )
    assert result["baseline_tests"]["passed"] is True
    assert result["tests"]["passed"] is False
    assert result["accepted"] is False
    assert result["reason"] == "baseline_has_no_confirmed_test_failures"


def test_candidate_cannot_patch_test_file(tmp_path):
    make_project(tmp_path)
    test_patch = (
        "--- a/test_app.py\n+++ b/test_app.py\n"
        "@@ -1,3 +1,3 @@\n-from app import VALUE\n"
        "+from app import VALUE\n def test_value():\n    assert VALUE == 2\n"
    )
    with pytest.raises(CandidateRejected, match="not allowed|test/support"):
        CandidateLab(tmp_path).evaluate_unified_diff(
            test_patch,
            allowed_files=["app.py", "test_app.py"],
            test_paths=["test_app.py"],
            allow_local_execution=True,
        )


def test_support_file_is_copied_for_candidate_imports(tmp_path):
    (tmp_path / "app.py").write_text("from helper import VALUE\n", encoding="utf-8")
    (tmp_path / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import VALUE\ndef test_value():\n    assert VALUE == 2\n",
        encoding="utf-8",
    )
    patch = (
        "--- a/helper.py\n+++ b/helper.py\n"
        "@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n"
    )
    result = CandidateLab(tmp_path).evaluate_unified_diff(
        patch, allowed_files=["helper.py"], test_paths=["test_app.py"],
        support_files=["app.py"], allow_local_execution=True,
    )
    assert result["accepted"] is True
    assert result["support_files"] == ["app.py"]
    assert result["live_files_unchanged"] is True


def test_candidate_execution_is_disabled_by_default(tmp_path):
    make_project(tmp_path)
    with pytest.raises(CandidateRejected, match="disabled by default"):
        CandidateLab(tmp_path).evaluate_unified_diff(
            valid_patch(), allowed_files=["app.py"], test_paths=["test_app.py"]
        )


def test_candidate_cannot_be_accepted_by_skipping_baseline_failure(tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import VALUE\n"
        "def test_value():\n"
        "    assert VALUE == 2\n", encoding="utf-8"
    )
    skip_patch = (
        "--- a/app.py\n+++ b/app.py\n@@ -1 +1,2 @@\n"
        "-VALUE = 1\n+import pytest\n+pytest.skip('hide failing test', allow_module_level=True)\n"
    )
    result = CandidateLab(tmp_path).evaluate_unified_diff(
        skip_patch, allowed_files=["app.py"], test_paths=["test_app.py"],
        allow_local_execution=True,
    )
    assert result["accepted"] is False
    assert result["reason"] == "candidate_did_not_pass_all_baseline_failures"
    assert result["baseline_failures_resolved"] is False
    assert result["live_files_unchanged"] is True


def test_candidate_cannot_be_accepted_by_xfail(tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import VALUE\n"
        "import pytest\n"
        "@pytest.mark.xfail(reason='mask failure')\n"
        "def test_value():\n"
        "    assert VALUE == 2\n", encoding="utf-8"
    )
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n"
    result = CandidateLab(tmp_path).evaluate_unified_diff(
        patch, allowed_files=["app.py"], test_paths=["test_app.py"],
        allow_local_execution=True,
    )
    assert result["accepted"] is False
    assert result["reason"] == "baseline_has_no_confirmed_test_failures"


def test_pytest_config_and_conftest_are_included_automatically(tmp_path):
    make_project(tmp_path)
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -ra\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "def pytest_configure(config):\n    config._candidate_lab_fixture_loaded = True\n",
        encoding="utf-8",
    )
    result = CandidateLab(tmp_path).evaluate_unified_diff(
        valid_patch(), allowed_files=["app.py"], test_paths=["test_app.py"],
        allow_local_execution=True,
    )
    assert result["accepted"] is True
    assert "pytest.ini" in result["support_files"]
    assert "conftest.py" in result["support_files"]
