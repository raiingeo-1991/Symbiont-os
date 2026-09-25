import base64
import hashlib
import json
import os
import subprocess
import shutil
import tempfile
from pathlib import Path


class NodeIdentity:
    """
    Ed25519 node identity using the system OpenSSL binary.
    No Python cryptography dependency required.
    """

    def __init__(self, path="symbiont_data/node_identity.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.private_key = None
        self.public_key = None
        self.node_id = None

        self._load_or_create()

    @staticmethod
    def _openssl_binary():
        configured = os.environ.get("SYMBIONT_OPENSSL_BIN", "")
        candidates = [configured, shutil.which("openssl"),
                      r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
                      r"C:\Program Files\OpenSSL-Win32\bin\openssl.exe"]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(candidate)
        raise FileNotFoundError("OpenSSL is required for Ed25519 identities. Set SYMBIONT_OPENSSL_BIN to openssl.exe.")

    def _openssl(self, *args, input_data=None):
        return subprocess.run(
            [self._openssl_binary(), *args],
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def _generate(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "key.pem"
            pub_path = Path(tmp) / "pub.pem"

            self._openssl(
                "genpkey",
                "-algorithm",
                "ED25519",
                "-out",
                str(key_path),
            )

            self._openssl(
                "pkey",
                "-in",
                str(key_path),
                "-pubout",
                "-out",
                str(pub_path),
            )

            self.private_key = key_path.read_bytes()
            self.public_key = pub_path.read_bytes()

    def _derive_node_id(self):
        digest = hashlib.sha256(self.public_key).hexdigest()
        return "SYM-" + digest[:32]

    def _save(self):
        data = {
            "version": "1",
            "node_id": self.node_id,
            "private_key": base64.b64encode(
                self.private_key
            ).decode("ascii"),
            "public_key": base64.b64encode(
                self.public_key
            ).decode("ascii"),
            "algorithm": "Ed25519",
        }

        self.path.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )

        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _load_or_create(self):
        if self.path.exists():
            data = json.loads(
                self.path.read_text(encoding="utf-8")
            )

            self.private_key = base64.b64decode(
                data["private_key"]
            )
            self.public_key = base64.b64decode(
                data["public_key"]
            )

            calculated = self._derive_node_id()

            if data.get("node_id") != calculated:
                raise RuntimeError(
                    "Node identity integrity check failed"
                )

            self.node_id = calculated
            return

        self._generate()
        self.node_id = self._derive_node_id()
        self._save()

    def sign(self, payload):
        if not isinstance(payload, bytes):
            payload = str(payload).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "key.pem"
            data_path = Path(tmp) / "data"

            key_path.write_bytes(self.private_key)
            data_path.write_bytes(payload)

            result = self._openssl(
                "pkeyutl",
                "-sign",
                "-inkey",
                str(key_path),
                "-rawin",
                "-in",
                str(data_path),
            )

            return base64.b64encode(
                result.stdout
            ).decode("ascii")

    def verify(self, payload, signature):
        if not isinstance(payload, bytes):
            payload = str(payload).encode("utf-8")

        try:
            with tempfile.TemporaryDirectory() as tmp:
                pub_path = Path(tmp) / "pub.pem"
                data_path = Path(tmp) / "data"
                sig_path = Path(tmp) / "sig"

                pub_path.write_bytes(self.public_key)
                data_path.write_bytes(payload)
                sig_path.write_bytes(
                    base64.b64decode(signature)
                )

                result = subprocess.run(
                    [
                        self._openssl_binary(),
                        "pkeyutl",
                        "-verify",
                        "-pubin",
                        "-inkey",
                        str(pub_path),
                        "-rawin",
                        "-in",
                        str(data_path),
                        "-sigfile",
                        str(sig_path),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                return result.returncode == 0

        except Exception:
            return False

    @staticmethod
    def verify_with_public_key(payload, signature, public_key_b64):
        """Verify an Ed25519 signature against a packet-supplied public key."""
        if not isinstance(payload, bytes):
            payload = str(payload).encode("utf-8")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                pub_path = Path(tmp) / "pub.pem"
                data_path = Path(tmp) / "data"
                sig_path = Path(tmp) / "sig"
                pub_path.write_bytes(base64.b64decode(public_key_b64, validate=True))
                data_path.write_bytes(payload)
                sig_path.write_bytes(base64.b64decode(signature, validate=True))
                result = subprocess.run(
                    [NodeIdentity._openssl_binary(), "pkeyutl", "-verify", "-pubin", "-inkey", str(pub_path),
                     "-rawin", "-in", str(data_path), "-sigfile", str(sig_path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                return result.returncode == 0
        except Exception:
            return False

    def public_key_b64(self):
        return base64.b64encode(
            self.public_key
        ).decode("ascii")

    def identity(self):
        return {
            "node_id": self.node_id,
            "public_key": self.public_key_b64(),
            "algorithm": "Ed25519",
            "version": "1",
        }


def get_node_identity():
    return NodeIdentity()
