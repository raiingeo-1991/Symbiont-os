import uuid

from core.crypto_protocol import SCP1
from core.scp1_zerotrust import SCP1ZeroTrust


class NodeHandshake:
    """
    Establishes a trusted session between two Symbiont nodes.

    Flow:
        HELLO
          ↓
        SCP-1 verification
          ↓
        Zero-Trust check
          ↓
        session established
    """

    VERSION = "HANDSHAKE/1"

    def __init__(self, node_identity, zerotrust=None, scp=None):
        self.identity = node_identity
        self.zerotrust = zerotrust or SCP1ZeroTrust()
        self.scp = scp or SCP1()

        self.state = "IDLE"
        self.peer = None
        self.session_id = None

    def hello(self):
        packet_id = str(uuid.uuid4())

        payload = self.scp.build_payload(
            self.identity.node_id,
            self.identity.public_key,
            {
                "handshake": self.VERSION,
                "action": "HELLO",
                "hello_id": packet_id,
            },
            message_type="HANDSHAKE",
        )

        signed = self.scp.sign(
            self.identity.private_key,
            payload,
        )

        return signed

    def accept(self, packet):
        self.state = "VERIFYING"

        try:
            if not self.scp.verify(packet):
                self.state = "REJECTED"
                return False

            peer_node_id = packet.get("node_id")

            if not peer_node_id:
                self.state = "REJECTED"
                return False

            if not self.zerotrust.is_trusted(peer_node_id):
                self.state = "REJECTED"
                return False

            payload = packet.get("payload", {})

            if payload.get("action") != "HELLO":
                self.state = "REJECTED"
                return False

            self.peer = peer_node_id
            self.session_id = "SES-" + uuid.uuid4().hex
            self.state = "ESTABLISHED"

            return True

        except Exception:
            self.state = "REJECTED"
            return False

    def status(self):
        return {
            "protocol": self.VERSION,
            "state": self.state,
            "peer": self.peer,
            "session_id": self.session_id,
        }


def get_node_handshake(
    node_identity,
    zerotrust=None,
    scp=None,
):
    return NodeHandshake(
        node_identity,
        zerotrust,
        scp,
    )
