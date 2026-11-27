import json

import symbiont_core as sc


def test_active_immunity_scan_records_and_anchors_reproduction(
    tmp_path, capsys
):
    assert sc.ImmuneCycle is not None, "ImmuneCycle must be importable"

    sym = sc.Symbiont(
        root=tmp_path,
        show_recovery_phrase=False,
    )
    capsys.readouterr()

    try:
        report = sym.run_immunity_scan()

        assert report["ok"] is True, report.get("errors")
        assert report["patches_applied"] is False
        assert report["memory_recorded"] is True
        assert report["sis_anchored"] is True
        assert report["errors"] == []

        reproduction = report["reproduction"]
        assert reproduction["confirmed"] is True
        assert reproduction["persisted_balance"] == 10.0
        assert reproduction["balance_after_restart"] == 10.0
        assert reproduction["journal_event_count"] == 1
        assert reproduction["economy_credit_event_count"] == 1
        assert reproduction["outbox_pending_before_restart"] == 1
        assert reproduction["outbox_pending_after_restart"] == 0
        assert reproduction["scenario"] == "credit_outbox_recovery_after_journal_failure"
        assert reproduction["isolation"] == "temporary_directory"

        evidence_id = report["evidence_id"]
        assert evidence_id

        evidence = [
            item
            for item in sym.immune_memory.list_evidence()
            if item.get("evidence_id") == evidence_id
        ]
        assert len(evidence) == 1

        sis_status = sym.sis_integrity.status()
        assert sis_status["valid"] is True
        assert sis_status["anchored_records"] >= 1

        report_path = report.get("report_path")
        assert report_path
        saved_report = json.loads(
            __import__("pathlib").Path(report_path).read_text(
                encoding="utf-8"
            )
        )
        assert saved_report["result"] == "reproduction_confirmed"
        assert saved_report["patches_applied"] is False
    finally:
        sym.close()
        capsys.readouterr()


def test_candidate_patch_is_evaluated_recorded_and_anchored(tmp_path, monkeypatch, capsys):
    assert sc.ImmuneCycle is not None
    project = tmp_path / "candidate_project"
    project.mkdir()
    (project / "symbiont_core.py").write_text(
        "class Economy:\n"
        "    def credit(self):\n"
        "        self._save()\n"
        "        self.journal.append('credit', {})\n",
        encoding="utf-8",
    )
    (project / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (project / "test_app.py").write_text(
        "from app import VALUE\ndef test_value():\n    assert VALUE == 2\n",
        encoding="utf-8",
    )
    patch = (
        "--- a/app.py\n+++ b/app.py\n"
        "@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n"
    )
    monkeypatch.setattr(sc, "__file__", str(project / "symbiont_core.py"))
    sym = sc.Symbiont(root=tmp_path / "runtime", show_recovery_phrase=False)
    capsys.readouterr()
    original = (project / "app.py").read_bytes()
    try:
        report = sym.run_immunity_scan(
            candidate_patch=patch,
            allowed_files=["app.py"],
            test_paths=["test_app.py"],
            allow_local_candidate_execution=True,
        )
        assert report["ok"] is True, report["errors"]
        assert report["candidate_evaluated"] is True
        assert report["candidate_accepted"] is True
        assert report["candidate_memory_recorded"] is True
        assert report["candidate_sis_anchored"] is True
        assert report["patches_applied"] is False
        assert (project / "app.py").read_bytes() == original
        evidence = [
            item for item in sym.immune_memory.list_evidence()
            if item.get("evidence_id") == report["candidate_evidence_id"]
        ]
        assert len(evidence) == 1
        assert evidence[0]["source_event_type"] == "immune.candidate.evaluated"
    finally:
        sym.close()
        capsys.readouterr()
