import time


class PeerSecurity:
    """
    Binds discovered peers to SCP-1 / ZeroTrust verification.
    """

    def __init__(self, registry, zerotrust):
        self.registry = registry
        self.zerotrust = zerotrust

    def register_trusted(self, node_id, public_key):
        node_id = str(node_id).strip()
        public_key = str(public_key).strip()

        if not node_id or not public_key:
            return False

        ok = self.zerotrust.register_node(node_id)

        if not ok:
            return False

        peer = self.registry.get(node_id)

        if peer is None:
            return False

        peer["public_key"] = public_key
        peer["status"] = "trusted"
        peer["trusted_at"] = time.time()

        self.registry.upsert(
            node_id,
            peer.get("address", ""),
            peer.get("port", 0),
            public_key=public_key,
            status="trusted",
            metadata=peer.get("metadata", {}),
        )

        return True

    def is_trusted(self, node_id):
        node_id = str(node_id).strip()

        if not node_id:
            return False

        peer = self.registry.get(node_id)

        if not peer:
            return False

        return peer.get("status") == "trusted"

    def remove_trusted(self, node_id):
        node_id = str(node_id).strip()

        try:
            self.zerotrust.remove_node(node_id)
        except Exception:
            pass

        peer = self.registry.get(node_id)

        if peer:
            peer["status"] = "discovered"

            self.registry.upsert(
                node_id,
                peer.get("address", ""),
                peer.get("port", 0),
                public_key=peer.get("public_key"),
                status="discovered",
                metadata=peer.get("metadata", {}),
            )

        return True

    def status(self):
        peers = self.registry.all()

        return {
            "known_peers": len(peers),
            "trusted_peers": sum(
                1
                for peer in peers
                if peer.get("status") == "trusted"
            ),
        }


def get_peer_security(registry, zerotrust):
    return PeerSecurity(registry, zerotrust)
