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
        assert reproduction["journal_event_count"] == 0
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
