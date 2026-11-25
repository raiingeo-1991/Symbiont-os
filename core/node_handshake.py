import secrets

from core.crypto_protocol import SCP1


class NodeHandshake:
    """
    Mutual SCP-1 handshake state machine.

    Transport and ZeroTrust verification are deliberately external:
    each incoming packet must pass SCP1ZeroTrust exactly once before
    its payload is passed to this state machine.
    """

    VERSION = "HANDSHAKE/1"

    IDLE = "IDLE"
    HELLO_SENT = "HELLO_SENT"
    CHALLENGE_SENT = "CHALLENGE_SENT"
    CHALLENGE_RECEIVED = "CHALLENGE_RECEIVED"
    FINISH_SENT = "FINISH_SENT"
    ESTABLISHED = "ESTABLISHED"
    REJECTED = "REJECTED"

    def __init__(self, node_identity, zerotrust=None, scp=None, expected_peer_node_id=None):
        self.identity = node_identity
        self.expected_peer_node_id = expected_peer_node_id
        self.zerotrust = zerotrust
        self.scp = scp or SCP1()

        self.state = self.IDLE
        self.peer = None
        self.session_id = None
        self.hello_id = None
        self.challenge_value = None

    def _packet(self, action, fields=None):
        payload = {
            "handshake": self.VERSION,
            "action": action,
            "hello_id": self.hello_id,
            "session_id": self.session_id,
        }
        if fields:
            payload.update(fields)

        packet = self.scp.build_payload(
            node_id=self.identity.node_id,
            public_key=self.identity.public_key,
            payload=payload,
            capability="network.send",
            message_type="HANDSHAKE",
        )
        return self.scp.sign(self.identity.private_key, packet)

    @staticmethod
    def _valid_payload(payload, action):
        return (
            isinstance(payload, dict)
            and payload.get("handshake") == NodeHandshake.VERSION
            and payload.get("action") == action
        )

    def hello(self, core_id=None, core_signature=None):
        if self.state != self.IDLE:
            raise RuntimeError("Handshake is not idle")

        self.hello_id = secrets.token_urlsafe(24)
        self.session_id = "SES-" + secrets.token_hex(24)
        self.state = self.HELLO_SENT

        return self._packet(
            "HELLO",
            {
                "core_id": core_id,
                "core_signature": core_signature,
            },
        )

    def create_challenge(self, payload, peer_node_id):
        if self.state != self.IDLE:
            self.state = self.REJECTED
            return None

        if not self._valid_payload(payload, "HELLO"):
            self.state = self.REJECTED
            return None

        hello_id = payload.get("hello_id")
        if not isinstance(hello_id, str) or not hello_id:
            self.state = self.REJECTED
            return None

        client_session_id = payload.get("session_id")
        if (
            not isinstance(client_session_id, str)
            or not client_session_id.startswith("SES-")
            or len(client_session_id) != 52
        ):
            self.state = self.REJECTED
            return None

        if not isinstance(peer_node_id, str) or not peer_node_id:
            self.state = self.REJECTED
            return None

        self.peer = peer_node_id
        self.hello_id = hello_id
        self.session_id = client_session_id
        self.challenge_value = secrets.token_urlsafe(32)
        self.state = self.CHALLENGE_SENT

        return self._packet(
            "CHALLENGE",
            {"challenge": self.challenge_value},
        )

    def accept_challenge(self, payload, peer_node_id):
        if self.state != self.HELLO_SENT:
            self.state = self.REJECTED
            return False

        if not self._valid_payload(payload, "CHALLENGE"):
            self.state = self.REJECTED
            return False

        if payload.get("hello_id") != self.hello_id:
            self.state = self.REJECTED
            return False

        challenge = payload.get("challenge")
        session_id = payload.get("session_id")

        if not isinstance(challenge, str) or len(challenge) < 32:
            self.state = self.REJECTED
            return False

        # The server must echo the exact session ID created by this client.
        # A syntactically valid but different ID is a session substitution.
        if (
            not isinstance(session_id, str)
            or session_id != self.session_id
        ):
            self.state = self.REJECTED
            return False

        if not isinstance(peer_node_id, str) or not peer_node_id:
            self.state = self.REJECTED
            return False

        if (
            self.expected_peer_node_id is not None
            and peer_node_id != self.expected_peer_node_id
        ):
            self.state = self.REJECTED
            return False

        self.peer = peer_node_id
        self.challenge_value = challenge
        self.state = self.CHALLENGE_RECEIVED
        return True

    def finish(self, core_id=None, core_signature=None):
        if self.state != self.CHALLENGE_RECEIVED:
            raise RuntimeError("Challenge has not been accepted")

        packet = self._packet(
            "FINISH",
            {
                "challenge": self.challenge_value,
                "core_id": core_id,
                "core_signature": core_signature,
            },
        )
        self.state = self.FINISH_SENT
        return packet

    def accept_finish(self, payload, peer_node_id):
        if self.state != self.CHALLENGE_SENT:
            self.state = self.REJECTED
            return False

        if not self._valid_payload(payload, "FINISH"):
            self.state = self.REJECTED
            return False

        if payload.get("hello_id") != self.hello_id:
            self.state = self.REJECTED
            return False

        if payload.get("session_id") != self.session_id:
            self.state = self.REJECTED
            return False

        if payload.get("challenge") != self.challenge_value:
            self.state = self.REJECTED
            return False

        if peer_node_id != self.peer:
            self.state = self.REJECTED
            return False

        self.state = self.ESTABLISHED
        return True

    def established(self):
        if self.state != self.ESTABLISHED:
            raise RuntimeError("Handshake is not established")

        return self._packet("ESTABLISHED")

    def accept_established(self, payload, peer_node_id):
        if self.state != self.FINISH_SENT:
            self.state = self.REJECTED
            return False

        if not self._valid_payload(payload, "ESTABLISHED"):
            self.state = self.REJECTED
            return False

        if payload.get("hello_id") != self.hello_id:
            self.state = self.REJECTED
            return False

        if payload.get("session_id") != self.session_id:
            self.state = self.REJECTED
            return False

        if peer_node_id != self.peer:
            self.state = self.REJECTED
            return False

        self.state = self.ESTABLISHED
        return True

    def status(self):
        return {
            "protocol": self.VERSION,
            "state": self.state,
            "peer": self.peer,
            "session_id": self.session_id,
        }


def get_node_handshake(node_identity, zerotrust=None, scp=None):
    return NodeHandshake(node_identity, zerotrust, scp)
