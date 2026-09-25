import tempfile
import time
import unittest
from pathlib import Path

from core.crypto_protocol import SCP1, SCPReplayGuard
from core.node_identity import NodeIdentity
from core.scp1_zerotrust import SCP1ZeroTrust


class SCP1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.identity = NodeIdentity(Path(self.tmp.name) / "node.json")
        self.node_id = self.identity.node_id
        raw = SCP1.build_payload(self.node_id, self.identity.public_key, {"action": "ping"}, nonce="nonce-1")
        self.packet = SCP1.sign(self.identity.private_key, raw)

    def tearDown(self):
        self.tmp.cleanup()

    def adapter(self, trusted=True):
        guard = SCPReplayGuard(path=Path(self.tmp.name) / "replay.json")
        return SCP1ZeroTrust(trusted_nodes=[self.node_id] if trusted else [], replay_guard=guard)

    def test_signed_packet_is_accepted_once_for_trusted_node(self):
        adapter = self.adapter()
        self.assertTrue(adapter.verify(self.packet))
        self.assertFalse(adapter.verify(self.packet))

    def test_tampered_payload_is_rejected(self):
        self.packet["payload"] = {"action": "payment"}
        self.assertFalse(SCP1.verify(self.packet))

    def test_expired_and_future_packets_are_rejected(self):
        old = SCP1.sign(self.identity.private_key, SCP1.build_payload(self.node_id, self.identity.public_key, {}, timestamp=time.time() - 301))
        future = SCP1.sign(self.identity.private_key, SCP1.build_payload(self.node_id, self.identity.public_key, {}, timestamp=time.time() + 31))
        self.assertFalse(SCP1.verify(old, max_age=300))
        self.assertFalse(SCP1.verify(future, max_age=300))

    def test_forged_node_id_and_extra_field_are_rejected(self):
        forged = dict(self.packet); forged["node_id"] = "SYM-" + "0" * 32
        extra = dict(self.packet); extra["extra"] = "unsigned"
        self.assertFalse(SCP1.verify(forged))
        self.assertFalse(SCP1.verify(extra))

    def test_unknown_node_is_rejected_after_valid_signature(self):
        self.assertFalse(self.adapter(trusted=False).verify(self.packet))

    def test_replay_guard_is_scoped_to_node(self):
        guard = SCPReplayGuard(path=Path(self.tmp.name) / "scope.json")
        self.assertTrue(guard.check_and_store("node-a", "same"))
        self.assertTrue(guard.check_and_store("node-b", "same"))
        self.assertFalse(guard.check_and_store("node-a", "same"))


if __name__ == "__main__":
    unittest.main()
