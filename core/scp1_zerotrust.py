from .crypto_protocol import SCP1, SCPReplayGuard


class SCP1ZeroTrust:
    """
    Adapter between SCP-1 cryptographic packets
    and the Symbiont Zero-Trust layer.
    """

    VERSION = "SCP1-ZT/1"

    def __init__(self, trusted_nodes=None, replay_guard=None):
        self.trusted_nodes = set(trusted_nodes or [])
        self.replay = replay_guard or SCPReplayGuard()

    def register_node(self, node_id):
        node_id = str(node_id).strip()
        if not node_id:
            return False

        self.trusted_nodes.add(node_id)
        return True

    def remove_node(self, node_id):
        self.trusted_nodes.discard(str(node_id))
        return True

    def is_trusted(self, node_id):
        return str(node_id) in self.trusted_nodes

    def verify(self, packet, max_age=300):
        if not SCP1.verify(packet, max_age=max_age):
            return False

        node_id = str(packet["node_id"])
        nonce = str(packet["nonce"])

        if node_id not in self.trusted_nodes:
            return False

        if not self.replay.check_and_store(node_id, nonce):
            return False

        return True

    def status(self):
        return {
            "protocol": self.VERSION,
            "trusted_nodes": len(self.trusted_nodes),
            "replay_entries": self.replay.count(),
        }


def get_scp1_zerotrust(trusted_nodes=None):
    return SCP1ZeroTrust(trusted_nodes=trusted_nodes)
