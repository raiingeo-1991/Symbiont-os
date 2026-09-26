import time


class PeerSecurity:
    """
    Binds discovered peers to SCP-1/ZeroTrust verification.

    PeerDirectory is the discovery/registry layer.
    SCP1ZeroTrust is the source of trust state.

    This adapter intentionally does not assume that Peer is a dict.
    """

    def __init__(self, registry, zerotrust):
        self.registry = registry
        self.zerotrust = zerotrust

    def register_trusted(self, node_id, public_key):
        node_id = str(node_id).strip()
        public_key = str(public_key).strip()

        if not node_id or not public_key:
            return False

        peer = self.registry.get(node_id)
        if peer is None:
            return False

        # Trust state belongs to SCP-1 / ZeroTrust.
        ok = self.zerotrust.register_node(node_id)
        if not ok:
            return False

        # PeerDirectory uses a Peer dataclass, not a dict.
        # Refresh the existing registry entry through its public API.
        self.registry.upsert(
            node_id,
            public_key,
            peer.address,
            peer.tcp_port,
            peer.name,
            peer.role,
        )

        return True

    def is_trusted(self, node_id):
        node_id = str(node_id).strip()

        if not node_id:
            return False

        peer = self.registry.get(node_id)
        if peer is None:
            return False

        return bool(self.zerotrust.is_trusted(node_id))

    def remove_trusted(self, node_id):
        node_id = str(node_id).strip()

        if not node_id:
            return False

        try:
            self.zerotrust.remove_node(node_id)
        except Exception:
            pass

        return True

    def status(self):
        peers = self.registry.list_all()

        trusted = 0
        for peer in peers:
            try:
                if self.zerotrust.is_trusted(peer.peer_id):
                    trusted += 1
            except Exception:
                pass

        return {
            "known_peers": len(peers),
            "trusted_peers": trusted,
        }


def get_peer_security(registry, zerotrust):
    return PeerSecurity(registry, zerotrust)
