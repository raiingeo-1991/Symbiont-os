import hashlib

import symbiont_core as core
from core.node_identity import NodeIdentity
from tsk import TrustedSecurityKernel


class FakeNode:
    def __init__(self, tsk=None):
        self.tsk = tsk
        self.peers = core.PeerDirectory()


def make_bound_network(tmp_path, monkeypatch, *,
                       confirm=True, trust_level=1.0,
                       peer_core_key=None, peer_node_fp=None,
                       binding_status=None):
    monkeypatch.setenv("SYMBIONT_SCP1_TRUSTED_NODES", "")

    tsk = TrustedSecurityKernel(root=tmp_path / "tsk")
    identity = NodeIdentity(tmp_path / "node-identity.json")

    core_id = "core-test-001"
    core_public_key = "core-public-key"
    core_fp = hashlib.sha256(
        core_public_key.encode("utf-8")
    ).hexdigest()
    node_fp = hashlib.sha256(identity.public_key).hexdigest()

    if confirm:
        assert tsk.confirm_core_node_binding(
            core_id=core_id,
            core_public_key_fingerprint=core_fp,
            node_identity_path=identity.path,
            owner_confirmation=(
                f"BIND {core_id} TO NODE {identity.node_id}"
            ),
        )

    if binding_status is not None:
        original = tsk.list_identity_bindings

        def altered_bindings():
            records = original()
            for item in records:
                if item.get("identity_type") == "CoreNodeBinding":
                    item["status"] = binding_status
            return records

        tsk.list_identity_bindings = altered_bindings

    assert tsk.register_trust(
        identity.node_id, trust_level=trust_level
    )

    node = FakeNode(tsk)
    node.peers.upsert(
        core_id,
        peer_core_key if peer_core_key is not None else core_public_key,
        "127.0.0.1",
        12345,
        node_id=identity.node_id,
        node_public_key_fingerprint=(
            peer_node_fp if peer_node_fp is not None else node_fp
        ),
    )

    network = core.P2PNetwork(node)
    return network, tsk, identity


def test_owner_confirmed_binding_and_full_trust_admit_node(
    tmp_path, monkeypatch
):
    network, _, identity = make_bound_network(tmp_path, monkeypatch)

    assert network.scp1.is_trusted(identity.node_id)


def test_tsk_trust_without_owner_binding_is_not_enough(
    tmp_path, monkeypatch
):
    network, _, identity = make_bound_network(
        tmp_path, monkeypatch, confirm=False
    )

    assert not network.scp1.is_trusted(identity.node_id)


def test_mismatched_core_public_key_is_rejected(
    tmp_path, monkeypatch
):
    network, _, identity = make_bound_network(
        tmp_path,
        monkeypatch,
        peer_core_key="different-core-public-key",
    )

    assert not network.scp1.is_trusted(identity.node_id)


def test_mismatched_node_fingerprint_is_rejected(
    tmp_path, monkeypatch
):
    network, _, identity = make_bound_network(
        tmp_path,
        monkeypatch,
        peer_node_fp="0" * 64,
    )

    assert not network.scp1.is_trusted(identity.node_id)


def test_trust_level_below_one_is_rejected(
    tmp_path, monkeypatch
):
    network, _, identity = make_bound_network(
        tmp_path, monkeypatch, trust_level=0.5
    )

    assert not network.scp1.is_trusted(identity.node_id)


def test_non_owner_confirmed_binding_is_rejected(
    tmp_path, monkeypatch
):
    network, _, identity = make_bound_network(
        tmp_path, monkeypatch, binding_status="unverified"
    )

    assert not network.scp1.is_trusted(identity.node_id)


def test_revocation_removes_tsk_derived_trust_on_next_sync(
    tmp_path, monkeypatch
):
    network, tsk, identity = make_bound_network(tmp_path, monkeypatch)

    assert network.scp1.is_trusted(identity.node_id)

    assert tsk.revoke_trust(identity.node_id)
    assert network._sync_scp1_trust() is True

    assert not network.scp1.is_trusted(identity.node_id)


def test_missing_peer_does_not_receive_tsk_trust(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SYMBIONT_SCP1_TRUSTED_NODES", "")
    tsk = TrustedSecurityKernel(root=tmp_path / "tsk")
    identity = NodeIdentity(tmp_path / "node-identity.json")
    assert tsk.register_trust(identity.node_id, trust_level=1.0)

    network = core.P2PNetwork(FakeNode(tsk))

    assert not network.scp1.is_trusted(identity.node_id)


def test_environment_trust_remains_supported(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "SYMBIONT_SCP1_TRUSTED_NODES",
        "SYM-env-001, SYM-env-002",
    )

    network = core.P2PNetwork(
        FakeNode(TrustedSecurityKernel(root=tmp_path / "tsk"))
    )

    assert network.scp1.is_trusted("SYM-env-001")
    assert network.scp1.is_trusted("SYM-env-002")


def test_tsk_failure_keeps_explicit_environment_trust(monkeypatch):
    monkeypatch.setenv(
        "SYMBIONT_SCP1_TRUSTED_NODES",
        "SYM-env-fallback-001",
    )

    class BrokenTSK:
        def list_identity_bindings(self):
            raise RuntimeError("TSK unavailable")

        def is_trusted(self, node_id, min_level=1.0):
            raise RuntimeError("TSK unavailable")

    network = core.P2PNetwork(FakeNode(BrokenTSK()))

    assert network.scp1.is_trusted("SYM-env-fallback-001")
    assert not network.scp1.is_trusted("SYM-tsk-unavailable-001")
