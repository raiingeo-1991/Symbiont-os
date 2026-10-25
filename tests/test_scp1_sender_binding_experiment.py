"""Эксперимент: SCP-1 подписант не должен выдавать себя за другого sender."""

import importlib.util
import json
import sys
from pathlib import Path


# Повторно используем тестовую инфраструктуру проекта,
# не изменяя её и не копируя фиктивные реализации.
audit_path = Path(__file__).with_name(
    "test_sss_security_boundary_audit.py"
)
spec = importlib.util.spec_from_file_location(
    "_scp1_existing_security_audit", audit_path
)
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


def test_scp1_rejects_mismatched_inner_sender(tmp_path, monkeypatch):
    signer = audit.NodeIdentity(tmp_path / "signer.json")
    local = audit.NodeIdentity(tmp_path / "local.json")

    node = audit.FakeNode()
    node.peers.upsert(
        "core-forged-sender",
        "test-peer-key",
        "127.0.0.1",
        12345,
    )

    network = audit.core.P2PNetwork(node, scp_identity=local)
    network.scp1_enabled = True
    network.scp1 = audit.SCP1ZeroTrust(
        trusted_nodes=[signer.node_id],
        replay_guard=audit.SCPReplayGuard(
            tmp_path / "replay.json"
        ),
    )

    # Криптографически подписывает A, но внутри указывает B.
    request = {
        "sender": "core-forged-sender",
        "signature": "a" * 64,
        "action": "PING",
    }
    packet = audit.SCP1.build_payload(
        node_id=signer.node_id,
        public_key=signer.public_key,
        payload=request,
        nonce="sender-binding-experiment",
        capability="network.send",
        message_type="P2P",
    )
    packet = audit.SCP1.sign(signer.private_key, packet)

    connection = audit.FakeConnection(
        json.dumps({"scp1": packet}).encode("utf-8")
    )

    # Упрощаем проверку ответа, не меняя логику обработки запроса.
    monkeypatch.setattr(
        network,
        "_scp1_wrap",
        lambda payload, message_type="P2P": {
            "test_response": payload
        },
    )

    network._handle_tcp(connection, ("127.0.0.1", 12345))

    assert connection.sent is not None, "Сервер не отправил ответ"
    response = json.loads(connection.sent.decode("utf-8"))
    body = response.get("test_response", response)

    assert body.get("status") != "PONG", (
        "УЯЗВИМОСТЬ ПОДТВЕРЖДЕНА: подписант A с чужим sender "
        "получил успешный ответ PONG"
    )


def _binding_ping_status(tmp_path, monkeypatch, *, wrong_core_fingerprint=False):
    import hashlib

    from tsk import TrustedSecurityKernel

    signer_path = tmp_path / "signer.json"
    signer = audit.NodeIdentity(signer_path)
    local = audit.NodeIdentity(tmp_path / "local.json")

    node = audit.FakeNode()
    node.peers.upsert(
        "core-forged-sender",
        "test-peer-key",
        "127.0.0.1",
        12345,
    )

    tsk_root = tmp_path / "tsk"
    tsk = TrustedSecurityKernel(root=tsk_root)
    core_key = (
        b"different-core-key"
        if wrong_core_fingerprint
        else b"test-peer-key"
    )
    core_fp = hashlib.sha256(core_key).hexdigest()

    tsk.confirm_core_node_binding(
        core_id="core-forged-sender",
        core_public_key_fingerprint=core_fp,
        node_identity_path=signer_path,
        owner_confirmation=(
            f"BIND core-forged-sender TO NODE {signer.node_id}"
        ),
    )

    # Exercise the persisted state, not only the in-memory binding.
    node.tsk = TrustedSecurityKernel(root=tsk_root)

    network = audit.core.P2PNetwork(node, scp_identity=local)
    network.scp1_enabled = True
    network.scp1 = audit.SCP1ZeroTrust(
        trusted_nodes=[signer.node_id],
        replay_guard=audit.SCPReplayGuard(tmp_path / "replay.json"),
    )

    request = {
        "sender": "core-forged-sender",
        "signature": "a" * 64,
        "action": "PING",
    }
    packet = audit.SCP1.build_payload(
        node_id=signer.node_id,
        public_key=signer.public_key,
        payload=request,
        nonce="binding-test-" + tmp_path.name,
        capability="network.send",
        message_type="P2P",
    )
    packet = audit.SCP1.sign(signer.private_key, packet)
    connection = audit.FakeConnection(
        json.dumps({"scp1": packet}).encode("utf-8")
    )

    monkeypatch.setattr(
        network,
        "_scp1_wrap",
        lambda payload, message_type="P2P": {"test_response": payload},
    )
    network._handle_tcp(connection, ("127.0.0.1", 12345))

    assert connection.sent is not None
    response = json.loads(connection.sent.decode("utf-8"))
    return response.get("test_response", response).get("status")


def test_confirmed_binding_allows_ping_after_tsk_reload(tmp_path, monkeypatch):
    assert _binding_ping_status(
        tmp_path, monkeypatch
    ) == "PONG"


def test_binding_rejects_mismatched_core_key_fingerprint(tmp_path, monkeypatch):
    assert _binding_ping_status(
        tmp_path, monkeypatch, wrong_core_fingerprint=True
    ) == "UNAUTHORIZED"


def test_incoming_scp1_rejects_missing_owner_confirmed_binding(
    tmp_path, monkeypatch
):
    signer = audit.NodeIdentity(tmp_path / "signer-no-binding.json")
    local = audit.NodeIdentity(tmp_path / "local-no-binding.json")

    node = audit.FakeNode()
    node.peers.upsert(
        "core-no-binding",
        "test-peer-key",
        "127.0.0.1",
        12345,
    )

    # TSK exists, but there is deliberately no owner-confirmed binding.
    from tsk import TrustedSecurityKernel

    node.tsk = TrustedSecurityKernel(root=tmp_path / "tsk-no-binding")

    network = audit.core.P2PNetwork(node, scp_identity=local)
    network.scp1_enabled = True
    network.scp1 = audit.SCP1ZeroTrust(
        trusted_nodes=[signer.node_id],
        replay_guard=audit.SCPReplayGuard(
            tmp_path / "replay-no-binding.json"
        ),
    )

    request = {
        "sender": "core-no-binding",
        "signature": "a" * 64,
        "action": "PING",
    }
    packet = audit.SCP1.build_payload(
        node_id=signer.node_id,
        public_key=signer.public_key,
        payload=request,
        nonce="missing-owner-binding-" + tmp_path.name,
        capability="network.send",
        message_type="P2P",
    )
    packet = audit.SCP1.sign(signer.private_key, packet)

    connection = audit.FakeConnection(
        json.dumps({"scp1": packet}).encode("utf-8")
    )
    monkeypatch.setattr(
        network,
        "_scp1_wrap",
        lambda payload, message_type="P2P": {
            "test_response": payload
        },
    )

    network._handle_tcp(connection, ("127.0.0.1", 12345))

    assert connection.sent is not None
    response = json.loads(connection.sent.decode("utf-8"))
    body = response.get("test_response", response)
    assert body.get("status") == "UNAUTHORIZED"


def test_incoming_scp1_rejects_replayed_packet(
    tmp_path, monkeypatch
):
    import hashlib

    from tsk import TrustedSecurityKernel

    signer_path = tmp_path / "replay-signer.json"
    signer = audit.NodeIdentity(signer_path)
    local = audit.NodeIdentity(tmp_path / "replay-local.json")

    node = audit.FakeNode()
    core_id = "core-replay-test"
    core_key = "test-peer-key"
    node.peers.upsert(
        core_id, core_key, "127.0.0.1", 12345
    )

    tsk_root = tmp_path / "tsk-replay"
    tsk = TrustedSecurityKernel(root=tsk_root)
    tsk.confirm_core_node_binding(
        core_id=core_id,
        core_public_key_fingerprint=hashlib.sha256(
            core_key.encode("utf-8")
        ).hexdigest(),
        node_identity_path=signer_path,
        owner_confirmation=(
            f"BIND {core_id} TO NODE {signer.node_id}"
        ),
    )
    node.tsk = TrustedSecurityKernel(root=tsk_root)

    replay_path = tmp_path / "replay-guard.json"
    network = audit.core.P2PNetwork(
        node, scp_identity=local
    )
    network.scp1_enabled = True
    network.scp1 = audit.SCP1ZeroTrust(
        trusted_nodes=[signer.node_id],
        replay_guard=audit.SCPReplayGuard(replay_path),
    )

    request = {
        "sender": core_id,
        "signature": "a" * 64,
        "action": "PING",
    }
    packet = audit.SCP1.build_payload(
        node_id=signer.node_id,
        public_key=signer.public_key,
        payload=request,
        nonce="replayed-ping-" + tmp_path.name,
        capability="network.send",
        message_type="P2P",
    )
    packet = audit.SCP1.sign(signer.private_key, packet)
    wire = json.dumps({"scp1": packet}).encode("utf-8")

    monkeypatch.setattr(
        network,
        "_scp1_wrap",
        lambda payload, message_type="P2P": {
            "test_response": payload
        },
    )

    statuses = []
    for _ in range(2):
        connection = audit.FakeConnection(wire)
        network._handle_tcp(connection, ("127.0.0.1", 12345))
        assert connection.sent is not None
        response = json.loads(connection.sent.decode("utf-8"))
        body = response.get("test_response", response)
        statuses.append(body.get("status"))

    assert statuses == ["PONG", "UNAUTHORIZED"]
