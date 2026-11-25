import hashlib


class PeerSecurity:
    """
    Validates Core <-> Node identity bindings before granting SCP-1 trust.

    PeerDirectory is indexed by Core ID.
    SCP1ZeroTrust is indexed by Node ID.
    TSK is the authority for owner-confirmed bindings and trust level.
    """

    def __init__(self, registry, zerotrust, tsk=None):
        self.registry = registry
        self.zerotrust = zerotrust
        self.tsk = tsk

    def _binding_matches(self, core_id, peer, node_id, node_fingerprint):
        if peer is None or self.tsk is None:
            return False

        try:
            core_fingerprint = hashlib.sha256(
                str(peer.public_key).encode("utf-8")
            ).hexdigest()

            return any(
                item.get("identity_type") == "CoreNodeBinding"
                and item.get("status") == "owner_confirmed"
                and item.get("core_id") == str(core_id)
                and item.get("core_public_key_fingerprint") == core_fingerprint
                and item.get("node_id") == str(node_id)
                and item.get("node_public_key_fingerprint") == str(node_fingerprint)
                for item in self.tsk.list_identity_bindings()
            )
        except Exception:
            return False

    def register_trusted(self, core_id, node_id, node_fingerprint):
        core_id = str(core_id).strip()
        node_id = str(node_id).strip()
        node_fingerprint = str(node_fingerprint).strip()

        if not core_id or not node_id or not node_fingerprint:
            return False

        try:
            peer = self.registry.get(core_id)
            if peer is None:
                return False

            if str(getattr(peer, "node_id", "")) != node_id:
                return False

            if str(getattr(peer, "node_public_key_fingerprint", "")) != node_fingerprint:
                return False

            if not self._binding_matches(
                core_id, peer, node_id, node_fingerprint
            ):
                return False

            if not self.tsk.is_trusted(node_id, min_level=1.0):
                return False

            return bool(self.zerotrust.register_node(node_id))
        except Exception:
            return False

    def is_trusted(self, core_id, node_id):
        core_id = str(core_id).strip()
        node_id = str(node_id).strip()

        if not core_id or not node_id:
            return False

        try:
            peer = self.registry.get(core_id)
            if peer is None:
                return False

            if str(getattr(peer, "node_id", "")) != node_id:
                return False

            if not self._binding_matches(
                core_id,
                peer,
                node_id,
                getattr(peer, "node_public_key_fingerprint", ""),
            ):
                return False

            if not self.tsk.is_trusted(node_id, min_level=1.0):
                return False

            return bool(self.zerotrust.is_trusted(node_id))
        except Exception:
            return False

    def remove_trusted(self, node_id):
        node_id = str(node_id).strip()
        if not node_id:
            return False

        try:
            return bool(self.zerotrust.remove_node(node_id))
        except Exception:
            return False

    def status(self):
        peers = self.registry.list_all()
        trusted = 0

        for peer in peers:
            node_id = getattr(peer, "node_id", "")
            if node_id and self.is_trusted(peer.peer_id, node_id):
                trusted += 1

        return {
            "known_peers": len(peers),
            "trusted_peers": trusted,
        }


def get_peer_security(registry, zerotrust, tsk=None):
    return PeerSecurity(registry, zerotrust, tsk=tsk)
