from symbiont_core import Symbiont


def test_core_security_event_is_recorded_in_immune_memory(tmp_path):
    sym = Symbiont(root=tmp_path)
    try:
        event = sym.journal.append(
            "security.integration_test",
            {
                "incident_id": "incident-integration-1",
                "reason": "test event",
            },
        )

        assert getattr(sym, "immune_memory", None) is not None

        evidence = sym.immune_memory.list_evidence(
            incident_id="incident-integration-1"
        )
        assert len(evidence) == 1
        assert evidence[0]["source_event_id"] == event["event_id"]
        assert evidence[0]["source_event_hash"] == event["hash"]
        assert evidence[0]["source_event_type"] == "security.integration_test"
        assert sym.immune_memory.verify() == (True, 1)
    finally:
        immune = getattr(sym, "immune_memory", None)
        if immune is not None:
            immune.close()


def test_security_evidence_is_not_duplicated_after_restart(tmp_path):
    first = Symbiont(root=tmp_path)
    event = first.journal.append(
        "security.restart_test",
        {"incident_id": "incident-restart-1"},
    )
    first.immune_memory.close()

    second = Symbiont(root=tmp_path)
    try:
        evidence = second.immune_memory.list_evidence(
            incident_id="incident-restart-1"
        )
        assert len(evidence) == 1
        assert evidence[0]["source_event_id"] == event["event_id"]
        assert second.immune_memory.verify() == (True, 1)
        assert second.immune_memory_error is None
    finally:
        second.immune_memory.close()


def test_non_security_event_is_not_recorded(tmp_path):
    sym = Symbiont(root=tmp_path)
    try:
        sym.journal.append(
            "symbiont.integration_test",
            {"note": "ordinary event"},
        )
        assert sym.immune_memory.list_evidence() == []
        assert sym.immune_memory.verify() == (True, 0)
    finally:
        sym.immune_memory.close()


def test_immune_memory_write_failure_is_observable(tmp_path):
    sym = Symbiont(root=tmp_path)
    try:
        def fail_write(**kwargs):
            raise OSError("simulated evidence storage failure")

        sym.immune_memory.record_evidence = fail_write
        sym.journal.append(
            "security.storage_failure_test",
            {"incident_id": "incident-storage-failure"},
        )

        assert sym.immune_memory_error is not None
        assert "OSError" in sym.immune_memory_error
        assert "simulated evidence storage failure" in sym.immune_memory_error
    finally:
        sym.immune_memory.close()


def test_economy_and_quest_events_share_quest_incident(tmp_path):
    sym = Symbiont(root=tmp_path)
    try:
        reserved = sym.journal.append(
            "economy.escrow_reserved",
            {"quest_id": "quest-sss-42", "reward": 12.5},
        )
        completed = sym.journal.append(
            "quest.delegated.done",
            {"quest_id": "quest-sss-42", "peer": "test-peer"},
        )

        evidence = sym.immune_memory.list_evidence(
            incident_id="quest-sss-42"
        )
        assert len(evidence) == 2
        by_id = {item["source_event_id"]: item for item in evidence}
        assert by_id[reserved["event_id"]]["source_event_hash"] == reserved["hash"]
        assert by_id[completed["event_id"]]["source_event_hash"] == completed["hash"]
        assert by_id[reserved["event_id"]]["source_event_type"] == "economy.escrow_reserved"
        assert by_id[completed["event_id"]]["source_event_type"] == "quest.delegated.done"
        assert sym.immune_memory.verify() == (True, 2)
    finally:
        if sym.immune_memory is not None:
            sym.immune_memory.close()


def test_economy_evidence_is_not_duplicated_after_restart(tmp_path):
    first = Symbiont(root=tmp_path)
    event = first.journal.append(
        "economy.escrow_frozen",
        {"quest_id": "quest-restart-7", "reason": "test"},
    )
    first.immune_memory.close()

    second = Symbiont(root=tmp_path)
    try:
        evidence = second.immune_memory.list_evidence(
            incident_id="quest-restart-7"
        )
        assert len(evidence) == 1
        assert evidence[0]["source_event_id"] == event["event_id"]
        assert evidence[0]["source_event_hash"] == event["hash"]
        assert second.immune_memory.verify() == (True, 1)
        assert second.immune_memory_error is None
    finally:
        if second.immune_memory is not None:
            second.immune_memory.close()
