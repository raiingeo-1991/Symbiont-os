import hashlib
import json

import pytest

from core.node_identity import NodeIdentity
from tsk import TSKIntegrityError, TSKRecoveryError, TrustedSecurityKernel


RECOVERY_PHRASE = "alpha beta gamma delta epsilon zeta eta theta"
WRONG_RECOVERY_PHRASE = "amber birch cobalt drift ember forest glacier harbor"


def _create_owner_confirmed_binding(root, node_path):
    node = NodeIdentity(node_path)
    tsk = TrustedSecurityKernel(root=root)

    core_id = "core-recovery-test"
    core_fp = hashlib.sha256(b"recovery-test-core-public-key").hexdigest()

    assert tsk.confirm_core_node_binding(
        core_id=core_id,
        core_public_key_fingerprint=core_fp,
        node_identity_path=node_path,
        owner_confirmation=f"BIND {core_id} TO NODE {node.node_id}",
    )
    return tsk, node, core_id, core_fp


def test_tampered_identity_bindings_are_rejected(tmp_path):
    root = tmp_path / "tsk"
    tsk = TrustedSecurityKernel(root=root)
    state_path = tsk.state_path

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.setdefault("identity_bindings", []).append({
        "identity_type": "CoreNodeBinding",
        "identity_id": "forged-core|forged-node",
        "core_id": "forged-core",
        "node_id": "forged-node",
        "status": "owner_confirmed",
    })
    state_path.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(TSKIntegrityError):
        TrustedSecurityKernel(root=root)


def test_same_phrase_recovery_preserves_owner_confirmed_binding(tmp_path):
    root = tmp_path / "tsk"
    node_path = tmp_path / "node_identity.json"

    # Establish a recovery-bound TSK identity before recording the binding.
    tsk = TrustedSecurityKernel(root=root, auto_create=False)
    assert tsk.recover_from_phrase(RECOVERY_PHRASE)

    tsk, node, core_id, core_fp = _create_owner_confirmed_binding(
        root, node_path
    )
    original_node_id = tsk.node_id()

    recovered = TrustedSecurityKernel.from_recovery_phrase(
        RECOVERY_PHRASE,
        root=root,
    )

    matches = [
        item for item in recovered.list_identity_bindings()
        if item.get("identity_type") == "CoreNodeBinding"
        and item.get("core_id") == core_id
        and item.get("node_id") == node.node_id
        and item.get("core_public_key_fingerprint") == core_fp
        and item.get("status") == "owner_confirmed"
    ]

    assert recovered.node_id() == original_node_id
    assert len(matches) == 1


def test_wrong_phrase_is_rejected_for_recovery_bound_identity(tmp_path):
    root = tmp_path / "tsk"

    tsk = TrustedSecurityKernel(root=root, auto_create=False)
    assert tsk.recover_from_phrase(RECOVERY_PHRASE)

    with pytest.raises(TSKRecoveryError):
        TrustedSecurityKernel.from_recovery_phrase(
            WRONG_RECOVERY_PHRASE,
            root=root,
        )
