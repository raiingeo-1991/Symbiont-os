import base64
from contextlib import contextmanager
import fcntl
import threading
import hashlib
import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


SCP_VERSION = "SCP-1"
DEFAULT_MAX_AGE = 300


class SCPError(Exception):
    pass


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
                    "openssl",
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
                    "openssl",
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
            return abs(now - timestamp) <= int(max_age)
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
    """Persistent, concurrency-safe nonce protection for SCP-1."""

    def __init__(self, path=None, max_entries=100000, max_age=86400):
        self.max_entries = int(max_entries)
        self.max_age = int(max_age)
        if self.max_entries < 1 or self.max_age < 0:
            raise ValueError("Invalid SCP replay limits")

        self.path = Path(path or "symbiont_data/scp_replay.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.path.with_name(self.path.name + ".lock")
        self._thread_lock = threading.RLock()
        self._seen = {}

        with self._locked():
            self._load()

    @contextmanager
    def _locked(self):
        """Lock this instance and all cooperating processes."""
        with self._thread_lock:
            fd = os.open(
                str(self._lock_path),
                os.O_CREAT | os.O_RDWR,
                0o600,
            )
            with os.fdopen(fd, "a+b") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _load(self):
        """Load strictly; never turn damaged storage into an empty store."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._seen = {}
            return
        except OSError as exc:
            raise RuntimeError(
                f"SCP replay storage cannot be read: {self.path}"
            ) from exc

        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("replay root must be an object")

            loaded = {}
            for key, timestamp in data.items():
                if (
                    not isinstance(key, str)
                    or not key
                    or type(timestamp) is not int
                    or timestamp < 0
                ):
                    raise ValueError("invalid replay entry")
                loaded[key] = timestamp

            self._seen = loaded
            self._cleanup(save=False)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"SCP replay storage is corrupted: {self.path}"
            ) from exc

    def _save(self):
        """Write through a unique temporary file and atomically replace."""
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(
                    self._seen,
                    stream,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                stream.flush()
                os.fsync(stream.fileno())

            os.replace(tmp_name, self.path)

            dir_fd = os.open(str(self.path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

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

        with self._locked():
            self._load()
            previous = self._seen.copy()

            if key in self._seen:
                return False

            self._seen[key] = int(time.time())
            self._cleanup(save=False)

            try:
                self._save()
            except BaseException:
                self._seen = previous
                raise

            return True

    def contains(self, node_id, nonce):
        with self._locked():
            self._load()
            return f"{node_id}:{nonce}" in self._seen

    def count(self):
        with self._locked():
            self._load()
            return len(self._seen)


def get_scp():
    return SCP1()


def get_replay_guard():
    return SCPReplayGuard()
