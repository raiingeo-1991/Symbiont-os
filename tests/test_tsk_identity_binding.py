import hashlib

import pytest

from core.node_identity import NodeIdentity
from tsk import TSKError, TrustedSecurityKernel


def test_owner_confirmed_binding_survives_restart(tmp_path):
    root = tmp_path / "tsk"
    node_path = tmp_path / "node_identity.json"
    node = NodeIdentity(node_path)
    tsk = TrustedSecurityKernel(root=root)

    core_id = "core-test-01"
    core_fp = hashlib.sha256(b"test-core-public-key").hexdigest()
    confirmation = f"BIND {core_id} TO NODE {node.node_id}"

    assert tsk.confirm_core_node_binding(
        core_id=core_id,
        core_public_key_fingerprint=core_fp,
        node_identity_path=node_path,
        owner_confirmation=confirmation,
    )

    reloaded = TrustedSecurityKernel(root=root)
    matches = [
        item for item in reloaded.list_identity_bindings()
        if item.get("identity_type") == "CoreNodeBinding"
        and item.get("core_id") == core_id
        and item.get("node_id") == node.node_id
        and item.get("status") == "owner_confirmed"
    ]
    assert len(matches) == 1
    assert matches[0]["core_public_key_fingerprint"] == core_fp


def test_binding_rejects_wrong_owner_confirmation(tmp_path):
    node_path = tmp_path / "node_identity.json"
    node = NodeIdentity(node_path)
    tsk = TrustedSecurityKernel(root=tmp_path / "tsk")
    core_id = "core-test-02"
    core_fp = hashlib.sha256(b"another-core-key").hexdigest()

    with pytest.raises(TSKError):
        tsk.confirm_core_node_binding(
            core_id=core_id,
            core_public_key_fingerprint=core_fp,
            node_identity_path=node_path,
            owner_confirmation=f"BIND {core_id} TO NODE WRONG-ID",
        )

    assert not any(
        item.get("identity_type") == "CoreNodeBinding"
        for item in tsk.list_identity_bindings()
    )
