import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from immune_cycle import ImmuneCycle


def test_discovers_confirmed_economy_write_order_pattern(tmp_path):
    source = tmp_path / "symbiont_core.py"
    source.write_text(
        """
class Economy:
    def credit(self):
        self._save()
        self.journal.append("economy.credit", {})
""",
        encoding="utf-8",
    )

    cycle = ImmuneCycle(tmp_path, tmp_path / "reports")
    report = cycle.discover_economy_write_order()

    assert report["finding_count"] == 1
    finding = report["findings"][0]
    assert finding["method"] == "credit"
    assert finding["status"] == "candidate"
    assert len(report["source_sha256"]) == 64


def test_does_not_flag_journal_before_save(tmp_path):
    source = tmp_path / "symbiont_core.py"
    source.write_text(
        """
class Economy:
    def credit(self):
        self.journal.append("economy.credit", {})
        self._save()
""",
        encoding="utf-8",
    )

    report = ImmuneCycle(
        tmp_path, tmp_path / "reports"
    ).discover_economy_write_order()

    assert report["finding_count"] == 0


def test_rejects_source_path_outside_project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("class Economy: pass", encoding="utf-8")

    cycle = ImmuneCycle(root, tmp_path / "reports")
    with pytest.raises(ValueError, match="inside project root"):
        cycle.discover_economy_write_order("../outside.py")


def test_report_creation_does_not_overwrite_existing_report(tmp_path):
    cycle = ImmuneCycle(tmp_path, tmp_path / "reports")
    first = cycle.save_report({"result": "first"})
    second = cycle.save_report({"result": "second"})

    assert first != second
    assert first.exists() and second.exists()
    assert '"result": "first"' in first.read_text(encoding="utf-8")
    assert '"result": "second"' in second.read_text(encoding="utf-8")


def test_confirmed_reproduction_is_recorded_idempotently(tmp_path):
    from core.sss.immune_memory import ImmuneMemory

    cycle = ImmuneCycle(tmp_path, tmp_path / "reports")
    memory = ImmuneMemory(tmp_path / "immune.sqlite3")
    finding = {
        "rule_id": "ECONOMY-SAVE-BEFORE-JOURNAL",
        "method": "credit",
        "source_sha256": "a" * 64,
        "status": "candidate",
    }
    reproduction = {
        "confirmed": True,
        "failure": "SIMULATED_JOURNAL_FAILURE",
        "persisted_balance": 10.0,
        "journal_event_count": 0,
    }

    try:
        first = cycle.record_reproduction(memory, finding, reproduction)
        second = cycle.record_reproduction(memory, finding, reproduction)

        assert first == second
        assert memory.verify() == (True, 1)
        evidence = memory.list_evidence()[0]
        assert evidence["evidence_kind"] == "fact"
        assert evidence["source_event_type"] == "immune.reproduction.confirmed"
        assert evidence["details"]["reproduction"]["persisted_balance"] == 10.0
    finally:
        memory.close()


def test_unconfirmed_reproduction_is_not_recorded(tmp_path):
    from core.sss.immune_memory import ImmuneMemory

    cycle = ImmuneCycle(tmp_path, tmp_path / "reports")
    memory = ImmuneMemory(tmp_path / "immune.sqlite3")

    try:
        with pytest.raises(ValueError, match="Only confirmed reproductions"):
            cycle.record_reproduction(
                memory,
                {
                    "rule_id": "TEST",
                    "method": "credit",
                    "source_sha256": "a" * 64,
                },
                {"confirmed": False},
            )

        assert memory.list_evidence() == []
    finally:
        memory.close()


def test_runner_reproduces_economy_journal_failure_in_isolation(tmp_path):
    cycle = ImmuneCycle(
        Path(__file__).resolve().parents[2],
        tmp_path / "reports",
    )

    result = cycle.reproduce_credit_journal_failure()

    assert result["confirmed"] is True
    assert result["persisted_balance"] == 10.0
    assert result["balance_after_restart"] == 10.0
    assert result["journal_valid"] is True
    assert result["journal_event_count"] == 0
    assert result["isolation"] == "temporary_directory"


def test_runner_result_can_be_recorded_as_immune_evidence(tmp_path):
    from core.sss.immune_memory import ImmuneMemory

    cycle = ImmuneCycle(
        Path(__file__).resolve().parents[2],
        tmp_path / "reports",
    )
    finding = cycle.discover_economy_write_order()
    credit_finding = next(
        item for item in finding["findings"]
        if item["method"] == "credit"
    )
    credit_finding["source_sha256"] = finding["source_sha256"]

    reproduction = cycle.reproduce_credit_journal_failure()
    memory = ImmuneMemory(tmp_path / "immune.sqlite3")

    try:
        evidence_id = cycle.record_reproduction(
            memory, credit_finding, reproduction
        )
        evidence = memory.list_evidence()

        assert evidence_id
        assert len(evidence) == 1
        assert evidence[0]["evidence_kind"] == "fact"
        assert evidence[0]["details"]["reproduction"]["confirmed"] is True
        assert memory.verify() == (True, 1)
    finally:
        memory.close()
