import json

import pytest

from core.continuity.ledger import ContinuityVerificationError
from core.continuity.shadow import ContinuityShadow
from core.node_identity import NodeIdentity


def test_core_shadow_ledger_uses_node_identity_ed25519_signatures(tmp_path):
    identity = NodeIdentity(tmp_path / "node_identity.json")
    shadow = ContinuityShadow(tmp_path / "node", identity)

    assert shadow.ledger.signer is identity
    shadow.on_core_event({
        "event_id": "core-event-1",
        "type": "memory.created",
        "previous": "0" * 64,
        "hash": "core-hash-1",
        "payload": {"memory_id": "mem-1"},
    })
    saved = json.loads(
        (tmp_path / "node" / "continuity" / "ledger.jsonl")
        .read_text(encoding="utf-8").splitlines()[0]
    )
    assert saved["signature"]
    assert shadow.ledger.verify() is True

    restarted = ContinuityShadow(tmp_path / "node", identity)
    assert restarted.ledger.signer is identity
    assert restarted.ledger.verify() is True


def test_core_shadow_rejects_modified_signed_ledger(tmp_path):
    identity = NodeIdentity(tmp_path / "node_identity.json")
    shadow = ContinuityShadow(tmp_path / "node", identity)
    shadow.on_core_event({
        "event_id": "core-event-2",
        "type": "memory.created",
        "previous": "0" * 64,
        "hash": "core-hash-2",
        "payload": {"memory_id": "mem-2"},
    })

    ledger_path = tmp_path / "node" / "continuity" / "ledger.jsonl"
    record = json.loads(ledger_path.read_text(encoding="utf-8"))
    record["payload"]["memory_id"] = "tampered"
    ledger_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ContinuityVerificationError):
        ContinuityShadow(tmp_path / "node", identity)
