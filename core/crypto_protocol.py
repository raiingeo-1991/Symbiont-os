import base64
import hashlib
import json
import os
import subprocess
import tempfile
import shutil
import threading
import time
import uuid
from pathlib import Path


SCP_VERSION = "SCP-1"
DEFAULT_MAX_AGE = 300
MAX_FUTURE_SKEW = 30


class SCPError(Exception):
    pass



def _openssl_binary():
    configured = os.environ.get("SYMBIONT_OPENSSL_BIN", "")
    candidates = [configured, shutil.which("openssl"),
                  r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
                  r"C:\Program Files\OpenSSL-Win32\bin\openssl.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise SCPError("OpenSSL is required for SCP-1 Ed25519 signatures")

class SCP1:
    """
    Symbiont Cryptographic Protocol v1.

    Uses Ed25519 for signatures and SHA-256 for node identity.
    The protocol defines how cryptographic primitives are combined
    into a Symbiont network packet.
    """

    VERSION = SCP_VERSION

    @staticmethod
    def canonical(data):
        return json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @staticmethod
    def node_id(public_key_pem):
        digest = hashlib.sha256(public_key_pem).hexdigest()
        return "SYM-" + digest[:32]

    @staticmethod
    def nonce():
        return base64.urlsafe_b64encode(os.urandom(24)).decode("ascii")

    @staticmethod
    def fingerprint(public_key_pem):
        return hashlib.sha256(public_key_pem).hexdigest()

    @classmethod
    def build_payload(
        cls,
        node_id,
        public_key,
        payload,
        nonce=None,
        timestamp=None,
        capability=None,
        message_type="DATA",
    ):
        if nonce is None:
            nonce = cls.nonce()

        if timestamp is None:
            timestamp = int(time.time())

        packet_id = "SCP-" + uuid.uuid4().hex

        return {
            "scp": cls.VERSION,
            "packet_id": packet_id,
            "type": str(message_type),
            "node_id": str(node_id),
            "public_key": base64.b64encode(public_key).decode("ascii"),
            "timestamp": int(timestamp),
            "nonce": str(nonce),
            "capability": capability,
            "payload": payload,
        }

    @staticmethod
    def _openssl_sign(private_key_pem, data):
        with tempfile.TemporaryDirectory() as td:
            key_file = Path(td) / "private.pem"
            data_file = Path(td) / "data.bin"

            key_file.write_bytes(private_key_pem)
            data_file.write_bytes(data)

            result = subprocess.run(
                [
                    _openssl_binary(),
                    "pkeyutl",
                    "-sign",
                    "-inkey",
                    str(key_file),
                    "-rawin",
                    "-in",
                    str(data_file),
                ],
                capture_output=True,
                check=False,
            )

            if result.returncode != 0:
                raise SCPError(
                    result.stderr.decode("utf-8", errors="replace")
                )

            return result.stdout

    @staticmethod
    def _openssl_verify(public_key_pem, signature, data):
        with tempfile.TemporaryDirectory() as td:
            key_file = Path(td) / "public.pem"
            sig_file = Path(td) / "signature.bin"
            data_file = Path(td) / "data.bin"

            key_file.write_bytes(public_key_pem)
            sig_file.write_bytes(signature)
            data_file.write_bytes(data)

            result = subprocess.run(
                [
                    _openssl_binary(),
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(key_file),
                    "-rawin",
                    "-in",
                    str(data_file),
                    "-sigfile",
                    str(sig_file),
                ],
                capture_output=True,
                check=False,
            )

            return result.returncode == 0

    @classmethod
    def sign(cls, private_key_pem, packet):
        unsigned = dict(packet)
        unsigned.pop("signature", None)

        data = cls.canonical(unsigned)
        signature = cls._openssl_sign(private_key_pem, data)

        signed = dict(unsigned)
        signed["signature"] = base64.b64encode(signature).decode("ascii")
        return signed

    @classmethod
    def verify_signature(cls, packet):
        try:
            unsigned = dict(packet)
            signature_b64 = unsigned.pop("signature")

            public_key = base64.b64decode(unsigned["public_key"])
            signature = base64.b64decode(signature_b64)

            expected_node = cls.node_id(public_key)

            if unsigned["node_id"] != expected_node:
                return False

            data = cls.canonical(unsigned)

            return cls._openssl_verify(
                public_key,
                signature,
                data,
            )

        except Exception:
            return False

    @classmethod
    def verify_freshness(cls, packet, max_age=DEFAULT_MAX_AGE):
        try:
            timestamp = int(packet["timestamp"])
            now = int(time.time())
            if timestamp > now + MAX_FUTURE_SKEW:
                return False
            return now - timestamp <= int(max_age)
        except Exception:
            return False

    @classmethod
    def verify_structure(cls, packet):
        required = {
            "scp",
            "packet_id",
            "type",
            "node_id",
            "public_key",
            "timestamp",
            "nonce",
            "capability",
            "payload",
            "signature",
        }

        if not isinstance(packet, dict):
            return False

        if not required.issubset(packet.keys()):
            return False

        if packet.get("scp") != cls.VERSION:
            return False

        if not packet.get("node_id"):
            return False

        if not packet.get("packet_id"):
            return False

        if not packet.get("nonce"):
            return False

        return True

    @classmethod
    def verify(cls, packet, max_age=DEFAULT_MAX_AGE):
        if not cls.verify_structure(packet):
            return False

        if not cls.verify_freshness(packet, max_age):
            return False

        if not cls.verify_signature(packet):
            return False

        return True


class SCPReplayGuard:
    """Persistent nonce protection for SCP-1."""

    def __init__(self, path=None, max_entries=100000, max_age=86400):
        self.max_entries = int(max_entries)
        self.max_age = int(max_age)
        self.path = Path(
            path or "symbiont_data/scp_replay.json"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen = {}
        self._load()

    def _load(self):
        try:
            if not self.path.exists():
                return

            data = json.loads(
                self.path.read_text(encoding="utf-8")
            )

            if isinstance(data, dict):
                self._seen = {
                    str(k): int(v)
                    for k, v in data.items()
                    if isinstance(v, (int, float))
                }

            self._cleanup(save=False)

        except Exception:
            self._seen = {}

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                self._seen,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def _cleanup(self, save=True):
        now = int(time.time())
        cutoff = now - self.max_age

        self._seen = {
            key: timestamp
            for key, timestamp in self._seen.items()
            if timestamp >= cutoff
        }

        if len(self._seen) > self.max_entries:
            items = sorted(
                self._seen.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            self._seen = dict(items[:self.max_entries])

        if save:
            self._save()

    def check_and_store(self, node_id, nonce):
        key = f"{node_id}:{nonce}"

        self._cleanup(save=False)

        if key in self._seen:
            return False

        self._seen[key] = int(time.time())
        self._cleanup(save=True)

        return True

    def contains(self, node_id, nonce):
        self._cleanup(save=False)
        return f"{node_id}:{nonce}" in self._seen

    def count(self):
        self._cleanup(save=False)
        return len(self._seen)


def get_scp():
    return SCP1()


def get_replay_guard():
    return SCPReplayGuard()
