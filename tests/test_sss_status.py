import symbiont_core as sc


def test_sss_status_is_healthy_with_valid_empty_stores(tmp_path, capsys):
    sym = sc.Symbiont(root=tmp_path)
    capsys.readouterr()
    try:
        status = sym.status()["sss"]

        assert status["state"] == "healthy"
        assert status["journal"]["valid"] is True
        assert status["immune_memory"]["verified"] is True
        assert status["immune_memory"]["evidence_count"] == 0
        assert status["sis_integrity"]["valid"] is True
        assert status["sis_integrity"]["anchored_records"] == 0
        assert status["evidence_count_mismatch"] is False
    finally:
        sym.close()
        capsys.readouterr()


def test_sss_status_is_degraded_when_evidence_write_fails(
    tmp_path, capsys
):
    sym = sc.Symbiont(root=tmp_path)
    capsys.readouterr()
    try:
        def fail_write(**kwargs):
            raise OSError("simulated evidence storage failure")

        sym.immune_memory.record_evidence = fail_write
        sym.journal.append(
            "security.status_failure_test",
            {"incident_id": "status-failure-test"},
        )

        status = sym.status()["sss"]

        assert status["state"] == "degraded"
        assert "OSError" in status["immune_memory"]["error"]
    finally:
        sym.close()
        capsys.readouterr()


def test_sss_status_is_degraded_when_sis_is_invalid(tmp_path, capsys):
    sym = sc.Symbiont(root=tmp_path)
    capsys.readouterr()
    try:
        original_status = sym.sis_integrity.status

        def invalid_status():
            result = original_status()
            result["valid"] = False
            return result

        sym.sis_integrity.status = invalid_status

        status = sym.status()["sss"]

        assert status["state"] == "degraded"
        assert status["sis_integrity"]["valid"] is False
    finally:
        sym.close()
        capsys.readouterr()


def test_sss_status_detects_evidence_anchor_count_mismatch(
    tmp_path, capsys
):
    sym = sc.Symbiont(root=tmp_path)
    capsys.readouterr()
    try:
        sym.journal.append(
            "security.status_count_test",
            {"incident_id": "status-count-test"},
        )
        original_status = sym.sis_integrity.status

        def mismatched_status():
            result = original_status()
            result["anchored_records"] = 0
            return result

        sym.sis_integrity.status = mismatched_status

        status = sym.status()["sss"]

        assert status["immune_memory"]["evidence_count"] == 1
        assert status["evidence_count_mismatch"] is True
        assert status["state"] == "degraded"
    finally:
        sym.close()
        capsys.readouterr()


def test_sss_status_is_disabled_when_components_are_absent(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(sc, "ImmuneMemory", None)
    monkeypatch.setattr(sc, "SISIntegrity", None)

    sym = sc.Symbiont(root=tmp_path)
    capsys.readouterr()
    try:
        status = sym.status()["sss"]

        assert status["state"] == "disabled"
        assert status["immune_memory"]["enabled"] is False
        assert status["sis_integrity"]["enabled"] is False
    finally:
        sym.close()
        capsys.readouterr()


def test_sss_status_is_unavailable_when_components_fail_to_load(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(sc, "ImmuneMemory", None)
    monkeypatch.setattr(sc, "SISIntegrity", None)

    sym = sc.Symbiont(root=tmp_path)
    capsys.readouterr()
    try:
        sym.immune_memory_error = "ImportError: simulated"
        sym.sis_integrity_error = "ImportError: simulated"

        status = sym.status()["sss"]

        assert status["state"] == "unavailable"
        assert status["immune_memory"]["error"] is not None
        assert status["sis_integrity"]["error"] is not None
    finally:
        sym.close()
        capsys.readouterr()
