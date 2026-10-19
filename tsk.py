#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TSK — Trusted Security Kernel for Symbiont

Единственный корень доверия.
Решает проблему нескольких идентичностей.
Обеспечивает непрерывность при смене устройств.

Совместим с:
  - SCP-1 (network_view)
  - SCA-1 / ContinuityIdentity (continuity_view)
  - SMSA / CapabilityGate (capability authority)
  - SecureSettlement
  - существующим NodeIdentity (может импортировать ключи)

Зависимости: только стандартная библиотека + системный OpenSSL.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# Exceptions
# ============================================================

class TSKError(Exception):
    """Base TSK error."""


class TSKIntegrityError(TSKError):
    """State integrity check failed."""


class TSKCapabilityError(TSKError):
    """Capability denied."""


class TSKRecoveryError(TSKError):
    """Recovery from phrase failed."""


# ============================================================
# Helpers
# ============================================================

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _canonical(data: Any) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# ============================================================
# Crypto (Ed25519 via OpenSSL — same style as NodeIdentity)
# ============================================================

class _Ed25519:
    """Minimal Ed25519 helper using system OpenSSL."""

    @staticmethod
    def _openssl(*args, input_data: Optional[bytes] = None) -> bytes:
        result = subprocess.run(
            ["openssl", *args],
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return result.stdout

    @classmethod
    def generate(cls) -> Tuple[bytes, bytes]:
        """Returns (private_pem, public_pem)."""
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "key.pem"
            pub_path = Path(tmp) / "pub.pem"

            cls._openssl(
                "genpkey", "-algorithm", "ED25519",
                "-out", str(key_path),
            )
            cls._openssl(
                "pkey", "-in", str(key_path),
                "-pubout", "-out", str(pub_path),
            )
            return key_path.read_bytes(), pub_path.read_bytes()

    @classmethod
    def from_seed(cls, seed: bytes) -> Tuple[bytes, bytes]:
        """Derive a stable Ed25519 keypair from exactly 32 bytes of seed."""
        if not isinstance(seed, bytes) or len(seed) != 32:
            raise TSKRecoveryError("Ed25519 seed must be exactly 32 bytes")
        # RFC 8410 PKCS#8 wrapper around the raw 32-byte Ed25519 seed.
        private_der = bytes.fromhex("302e020100300506032b657004220420") + seed
        with tempfile.TemporaryDirectory() as tmp:
            der_path = Path(tmp) / "key.der"
            key_path = Path(tmp) / "key.pem"
            pub_path = Path(tmp) / "pub.pem"
            der_path.write_bytes(private_der)
            cls._openssl("pkey", "-inform", "DER", "-in", str(der_path), "-out", str(key_path))
            cls._openssl("pkey", "-in", str(key_path), "-pubout", "-out", str(pub_path))
            return key_path.read_bytes(), pub_path.read_bytes()

    @classmethod
    def sign(cls, private_pem: bytes, data: bytes) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "key.pem"
            data_path = Path(tmp) / "data"
            key_path.write_bytes(private_pem)
            data_path.write_bytes(data)

            sig = cls._openssl(
                "pkeyutl", "-sign",
                "-inkey", str(key_path),
                "-rawin", "-in", str(data_path),
            )
            return base64.b64encode(sig).decode("ascii")

    @classmethod
    def verify(cls, public_pem: bytes, data: bytes, signature_b64: str) -> bool:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                pub_path = Path(tmp) / "pub.pem"
                data_path = Path(tmp) / "data"
                sig_path = Path(tmp) / "sig"

                pub_path.write_bytes(public_pem)
                data_path.write_bytes(data)
                sig_path.write_bytes(base64.b64decode(signature_b64))

                result = subprocess.run(
                    [
                        "openssl", "pkeyutl", "-verify",
                        "-pubin", "-inkey", str(pub_path),
                        "-rawin", "-in", str(data_path),
                        "-sigfile", str(sig_path),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def node_id_from_public(public_pem: bytes) -> str:
        digest = hashlib.sha256(public_pem).hexdigest()
        return "SYM-" + digest[:32]


# ============================================================
# Recovery phrase → deterministic seed (compatible style)
# ============================================================

def derive_seed_from_phrase(phrase: str, salt: str = "symbiont-tsk-v1") -> bytes:
    normalized = " ".join(phrase.strip().lower().split())
    return hashlib.pbkdf2_hmac(
        "sha256",
        normalized.encode("utf-8"),
        (salt + "|tsk-root").encode("utf-8"),
        120_000,
        dklen=32,
    )


# ============================================================
# Data structures
# ============================================================

@dataclass
class TrustEntry:
    node_id: str
    trust_level: float = 0.0          # 0.0 .. 1.0
    capabilities: List[str] = field(default_factory=list)
    added_at: str = field(default_factory=_now_iso)
    last_seen: Optional[str] = None
    notes: str = ""


@dataclass
class ExperienceDigest:
    """Compact experience for SSS (immune system)."""
    version: str = "1"
    critical_ops_ok: int = 0
    critical_ops_fail: int = 0
    integrity_failures: int = 0
    last_events: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: str = field(default_factory=_now_iso)

    def add_event(self, kind: str, detail: Optional[Dict] = None, keep: int = 20):
        self.last_events.append({
            "ts": _now_iso(),
            "kind": kind,
            "detail": detail or {},
        })
        self.last_events = self.last_events[-keep:]
        self.updated_at = _now_iso()


# ============================================================
# TSK Core
# ============================================================

class TrustedSecurityKernel:
    """
    Trusted Security Kernel.

    Единственный корень доверия Symbiont.
    """

    VERSION = "TSK/1"
    STATE_VERSION = "1"

    # Default capabilities that exist in the project
    DEFAULT_CAPABILITIES = {
        "memory.read": False,
        "memory.write": False,
        "microphone.listen": False,
        "camera.read": False,
        "location.read": False,
        "sensor.read": False,
        "network.send": False,
        "network.receive": False,
        "file.write": False,
        "payment.execute": False,
        "task.execute": False,
        "external_ai.call": False,
    }

    def __init__(
        self,
        root: str | Path = "symbiont_data",
        state_filename: str = "tsk_state.json",
        auto_create: bool = True,
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / state_filename

        self._lock = threading.RLock()

        # Root identity
        self._private_key: Optional[bytes] = None
        self._public_key: Optional[bytes] = None
        self._node_id: Optional[str] = None

        # Trust + policy + experience
        self._trust: Dict[str, TrustEntry] = {}
        self._capabilities: Dict[str, bool] = dict(self.DEFAULT_CAPABILITIES)
        self._experience = ExperienceDigest()
        # Keep identities from different subsystems as separate, non-destructive records.
        self._identity_bindings: List[Dict[str, Any]] = []

        # Runtime (not persisted)
        self._loaded = False

        if auto_create:
            self._load_or_create()

    # ----------------------------------------------------------
    # Internal crypto helpers
    # ----------------------------------------------------------

    def _derive_node_id(self) -> str:
        assert self._public_key is not None
        return _Ed25519.node_id_from_public(self._public_key)

    def _sign_raw(self, data: bytes) -> str:
        if self._private_key is None:
            raise TSKError("TSK not initialized")
        return _Ed25519.sign(self._private_key, data)

    def _verify_raw(self, public_pem: bytes, data: bytes, signature: str) -> bool:
        return _Ed25519.verify(public_pem, data, signature)

    # ----------------------------------------------------------
    # Load / Create / Save
    # ----------------------------------------------------------

    def _load_or_create(self) -> None:
        with self._lock:
            if self.state_path.exists():
                self._load_state()
            else:
                self._create_new()

    def _create_new(self) -> None:
        private, public = _Ed25519.generate()
        self._private_key = private
        self._public_key = public
        self._node_id = self._derive_node_id()
        self._trust = {}
        self._capabilities = dict(self.DEFAULT_CAPABILITIES)
        self._experience = ExperienceDigest()
        self._experience.add_event("tsk.created", {"node_id": self._node_id})
        self._save_state()
        self._loaded = True

    def _build_state_dict(self) -> Dict[str, Any]:
        """Build unsigned state dictionary."""
        return {
            "tsk_version": self.VERSION,
            "state_version": self.STATE_VERSION,
            "node_id": self._node_id,
            "public_key": base64.b64encode(self._public_key).decode("ascii") if self._public_key else "",
            "private_key": base64.b64encode(self._private_key).decode("ascii") if self._private_key else "",
            "algorithm": "Ed25519",
            "trust": {
                nid: asdict(entry) for nid, entry in self._trust.items()
            },
            "capabilities": dict(self._capabilities),
            "experience": asdict(self._experience),
            "identity_bindings": list(self._identity_bindings),
            "created_or_updated": _now_iso(),
        }

    def _save_state(self) -> None:
        state = self._build_state_dict()
        # Sign the state (without the signature field itself)
        to_sign = {k: v for k, v in state.items() if k != "signature"}
        # Do not include private_key in the signed payload for safety of verification
        to_sign_safe = {k: v for k, v in to_sign.items() if k != "private_key"}
        signature = self._sign_raw(_canonical(to_sign_safe))
        state["signature"] = signature
        _atomic_write(self.state_path, json.dumps(state, ensure_ascii=False, indent=2))

    def _load_state(self) -> None:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise TSKError(f"Cannot read TSK state: {exc}") from exc

        public_b64 = raw.get("public_key", "")
        private_b64 = raw.get("private_key", "")
        if not public_b64 or not private_b64:
            raise TSKError("TSK state missing keys")

        try:
            public_pem = base64.b64decode(public_b64, validate=True)
            private_pem = base64.b64decode(private_b64, validate=True)
        except Exception as exc:
            raise TSKIntegrityError("TSK state contains invalid base64 key material") from exc

        node_id = raw.get("node_id")
        self._validate_key_material(private_pem, public_pem, node_id)

        # A persisted state without a signature is not trusted.
        signature = raw.get("signature", "")
        if not signature:
            raise TSKIntegrityError("TSK state signature missing")
        to_verify = {k: v for k, v in raw.items() if k not in ("signature", "private_key")}
        if not self._verify_raw(public_pem, _canonical(to_verify), signature):
            raise TSKIntegrityError("TSK state signature invalid")

        self._public_key = public_pem
        self._private_key = private_pem
        self._node_id = node_id

        # Trust
        self._trust = {}
        for nid, entry in (raw.get("trust") or {}).items():
            self._trust[nid] = TrustEntry(
                node_id=entry.get("node_id", nid),
                trust_level=float(entry.get("trust_level", 0)),
                capabilities=list(entry.get("capabilities") or []),
                added_at=entry.get("added_at") or _now_iso(),
                last_seen=entry.get("last_seen"),
                notes=entry.get("notes") or "",
            )

        # Capabilities
        caps = raw.get("capabilities") or {}
        self._capabilities = dict(self.DEFAULT_CAPABILITIES)
        self._capabilities.update({k: bool(v) for k, v in caps.items()})

        # Experience
        exp = raw.get("experience") or {}
        self._experience = ExperienceDigest(
            version=exp.get("version", "1"),
            critical_ops_ok=int(exp.get("critical_ops_ok", 0)),
            critical_ops_fail=int(exp.get("critical_ops_fail", 0)),
            integrity_failures=int(exp.get("integrity_failures", 0)),
            last_events=list(exp.get("last_events") or []),
            updated_at=exp.get("updated_at") or _now_iso(),
        )

        # Older signed states predate identity_bindings; keep them readable.
        bindings = raw.get("identity_bindings", [])
        self._identity_bindings = list(bindings) if isinstance(bindings, list) else []
        self._loaded = True

    @staticmethod
    def _validate_key_material(private_pem: bytes, public_pem: bytes, node_id: Optional[str]) -> None:
        """Reject mismatched keys and IDs before changing any live TSK state."""
        if not private_pem or not public_pem:
            raise TSKIntegrityError("TSK key material is empty")
        try:
            challenge = b"TSK-KEY-PAIR-CHECK-v1"
            signature = _Ed25519.sign(private_pem, challenge)
        except Exception as exc:
            raise TSKIntegrityError("TSK private key is invalid") from exc
        if not _Ed25519.verify(public_pem, challenge, signature):
            raise TSKIntegrityError("TSK private/public key mismatch")
        expected_id = _Ed25519.node_id_from_public(public_pem)
        if not node_id or node_id != expected_id:
            raise TSKIntegrityError("TSK node_id does not match public key")

    # ----------------------------------------------------------
    # Public Identity API
    # ----------------------------------------------------------

    def get_root_identity(self) -> Dict[str, str]:
        with self._lock:
            return {
                "node_id": self._node_id or "",
                "public_key": base64.b64encode(self._public_key).decode("ascii") if self._public_key else "",
                "algorithm": "Ed25519",
                "version": self.VERSION,
            }

    def node_id(self) -> str:
        return self._node_id or ""

    def public_key_pem(self) -> bytes:
        if self._public_key is None:
            raise TSKError("TSK not initialized")
        return self._public_key

    def public_key_b64(self) -> str:
        return base64.b64encode(self.public_key_pem()).decode("ascii")

    def sign(self, data: Any) -> str:
        """Sign arbitrary data (dict or bytes)."""
        with self._lock:
            if isinstance(data, dict):
                raw = _canonical(data)
            elif isinstance(data, str):
                raw = data.encode("utf-8")
            else:
                raw = bytes(data)
            return self._sign_raw(raw)

    def verify(self, data: Any, signature: str, public_key_b64: Optional[str] = None) -> bool:
        with self._lock:
            if isinstance(data, dict):
                raw = _canonical(data)
            elif isinstance(data, str):
                raw = data.encode("utf-8")
            else:
                raw = bytes(data)

            if public_key_b64:
                pub = base64.b64decode(public_key_b64)
            else:
                pub = self._public_key
            if pub is None:
                return False
            return self._verify_raw(pub, raw, signature)

    # ----------------------------------------------------------
    # Views (for integration with existing systems)
    # ----------------------------------------------------------

    def get_view(self, name: str) -> Dict[str, Any]:
        """
        name: "continuity" | "network" | "legacy"
        """
        with self._lock:
            root = self.get_root_identity()

            if name == "continuity":
                # For SCA-1 ContinuityIdentity
                return {
                    "symbiont_id": root["node_id"],
                    "public_key": root["public_key"],
                    "algorithm": "Ed25519",
                    "version": "SCA-1",
                }

            if name == "network":
                # For SCP-1 / P2P
                return {
                    "node_id": root["node_id"],
                    "public_key": root["public_key"],
                    "algorithm": "Ed25519",
                    "version": "SCP-1",
                }

            if name == "legacy":
                # Temporary bridge for old Core Identity style
                # Uses same node_id but marks as legacy view
                short_id = "sym-" + (root["node_id"] or "")[-16:]
                return {
                    "symbiont_id": short_id,
                    "public_key": root["public_key"],
                    "source": "tsk-legacy-view",
                    "version": "1",
                }

            raise TSKError(f"Unknown view: {name}")

    # ----------------------------------------------------------
    # Non-destructive identity reconciliation
    # ----------------------------------------------------------

    def list_identity_bindings(self) -> List[Dict[str, Any]]:
        """Return a copy of recorded identity observations/bindings for SSS/audit."""
        with self._lock:
            return [dict(item) for item in self._identity_bindings]

    def _record_identity_binding(self, record: Dict[str, Any]) -> bool:
        # Return whether a new binding was added; repeated observations are no-ops.
        for existing in self._identity_bindings:
            if all(existing.get(k) == record.get(k) for k in (
                "identity_type", "identity_id", "public_key_fingerprint", "status"
            )):
                return False
        self._identity_bindings.append(record)
        return True

    def record_identity_observation(
        self,
        *,
        identity_type: str,
        identity_id: str,
        public_key_fingerprint: str,
        source: str,
        reason: str,
    ) -> bool:
        """Record a legacy identity without claiming cryptographic equivalence."""
        if not all(str(value).strip() for value in (
            identity_type, identity_id, public_key_fingerprint, source, reason
        )):
            raise TSKError("Identity observation fields must be non-empty")
        record = {
            "identity_type": str(identity_type),
            "identity_id": str(identity_id),
            "public_key_fingerprint": str(public_key_fingerprint),
            "status": "unverified",
            "root_node_id_at_observation": self._node_id or "",
            "source": str(source),
            "observed_at": _now_iso(),
            "reason": str(reason),
        }
        with self._lock:
            added = self._record_identity_binding(record)
            if added:
                self._experience.add_event(
                    "tsk.identity_binding_recorded",
                    {"identity_type": record["identity_type"],
                     "identity_id": record["identity_id"], "status": "unverified"},
                )
                self._save_state()
        return True

    # ----------------------------------------------------------
    # Trust Graph
    # ----------------------------------------------------------

    def is_trusted(self, node_id: str, min_level: float = 1.0) -> bool:
        with self._lock:
            entry = self._trust.get(str(node_id))
            if not entry:
                return False
            return entry.trust_level >= min_level

    def get_trust(self, node_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._trust.get(str(node_id))
            return asdict(entry) if entry else None

    def register_trust(
        self,
        node_id: str,
        trust_level: float = 1.0,
        capabilities: Optional[List[str]] = None,
        notes: str = "",
    ) -> bool:
        node_id = str(node_id).strip()
        if not node_id:
            return False
        trust_level = max(0.0, min(1.0, float(trust_level)))

        with self._lock:
            existing = self._trust.get(node_id)
            self._trust[node_id] = TrustEntry(
                node_id=node_id,
                trust_level=trust_level,
                capabilities=list(capabilities or (existing.capabilities if existing else [])),
                added_at=existing.added_at if existing else _now_iso(),
                last_seen=_now_iso(),
                notes=notes or (existing.notes if existing else ""),
            )
            self._experience.add_event(
                "trust.registered",
                {"node_id": node_id, "level": trust_level},
            )
            self._save_state()
            return True

    def revoke_trust(self, node_id: str) -> bool:
        node_id = str(node_id).strip()
        with self._lock:
            if node_id not in self._trust:
                return False
            del self._trust[node_id]
            self._experience.add_event("trust.revoked", {"node_id": node_id})
            self._save_state()
            return True

    def list_trusted(self, min_level: float = 1.0) -> List[str]:
        with self._lock:
            return [
                nid for nid, e in self._trust.items()
                if e.trust_level >= min_level
            ]

    def touch_peer(self, node_id: str) -> None:
        """Update last_seen for a known peer."""
        with self._lock:
            entry = self._trust.get(str(node_id))
            if entry:
                entry.last_seen = _now_iso()
                # no save on every touch to avoid IO storm; call save explicitly if needed

    # ----------------------------------------------------------
    # Capability Authority
    # ----------------------------------------------------------

    def is_allowed(self, capability: str) -> bool:
        with self._lock:
            return bool(self._capabilities.get(str(capability), False))

    def require(self, capability: str) -> bool:
        if not self.is_allowed(capability):
            self._experience.critical_ops_fail += 1
            self._experience.add_event(
                "capability.denied",
                {"capability": capability},
            )
            raise TSKCapabilityError(f"Capability denied: {capability}")
        self._experience.critical_ops_ok += 1
        return True

    def set_capability(self, capability: str, value: bool) -> bool:
        """Owner-level change of capability."""
        with self._lock:
            self._capabilities[str(capability)] = bool(value)
            self._experience.add_event(
                "capability.changed",
                {"capability": capability, "value": bool(value)},
            )
            self._save_state()
            return True

    def grant(self, capability: str) -> bool:
        return self.set_capability(capability, True)

    def revoke(self, capability: str) -> bool:
        return self.set_capability(capability, False)

    def snapshot_capabilities(self) -> Dict[str, bool]:
        with self._lock:
            return dict(self._capabilities)

    # ----------------------------------------------------------
    # Integrity
    # ----------------------------------------------------------

    def get_integrity_status(self) -> Dict[str, Any]:
        with self._lock:
            try:
                ok = self.verify_state()
                status = "ok" if ok else "failed"
            except Exception:
                status = "failed"
                ok = False

            return {
                "status": status,
                "node_id": self._node_id,
                "state_path": str(self.state_path),
                "loaded": self._loaded,
                "integrity_failures": self._experience.integrity_failures,
            }

    def verify_state(self) -> bool:
        """Re-read and verify signature of current state file."""
        with self._lock:
            if not self.state_path.exists():
                return False
            try:
                raw = json.loads(self.state_path.read_text(encoding="utf-8"))
                signature = raw.get("signature", "")
                to_verify = {
                    k: v for k, v in raw.items()
                    if k not in ("signature", "private_key")
                }
                pub = base64.b64decode(raw.get("public_key", ""), validate=True)
                private = base64.b64decode(raw.get("private_key", ""), validate=True)
                if raw.get("node_id") != _Ed25519.node_id_from_public(pub):
                    raise TSKIntegrityError("TSK state node_id does not match public key")
                self._validate_key_material(private, pub, raw.get("node_id"))
                ok = bool(signature) and self._verify_raw(pub, _canonical(to_verify), signature)
                if not ok:
                    self._experience.integrity_failures += 1
                    self._experience.add_event("integrity.failed", {})
                return ok
            except Exception:
                self._experience.integrity_failures += 1
                return False

    # ----------------------------------------------------------
    # Continuity: export / import
    # ----------------------------------------------------------

    def export_state(self) -> Dict[str, Any]:
        """
        Export signed TSK-State for handoff to another device.
        Private key is included (encrypted storage is caller's responsibility
        during transfer). For production later we can add passphrase encryption.
        """
        with self._lock:
            state = self._build_state_dict()
            to_sign_safe = {k: v for k, v in state.items() if k != "private_key"}
            state["signature"] = self._sign_raw(_canonical(to_sign_safe))
            state["export_id"] = "exp-" + uuid.uuid4().hex[:12]
            state["exported_at"] = _now_iso()
            self._experience.add_event("state.exported", {"export_id": state["export_id"]})
            self._save_state()
            return state

    def import_state(self, state: Dict[str, Any]) -> bool:
        """
        Import TSK-State on a new device.
        Verifies signature before accepting.
        """
        with self._lock:
            if not isinstance(state, dict):
                raise TSKError("Invalid state type")

            public_b64 = state.get("public_key", "")
            private_b64 = state.get("private_key", "")
            signature = state.get("signature", "")

            if not public_b64 or not private_b64 or not signature:
                raise TSKError("Incomplete TSK state")

            try:
                public_pem = base64.b64decode(public_b64, validate=True)
                private_pem = base64.b64decode(private_b64, validate=True)
            except Exception as exc:
                raise TSKIntegrityError("Imported state contains invalid base64 key material") from exc
            self._validate_key_material(private_pem, public_pem, state.get("node_id"))
            to_verify = {
                k: v for k, v in state.items()
                if k not in ("signature", "private_key", "export_id", "exported_at")
            }

            if not self._verify_raw(public_pem, _canonical(to_verify), signature):
                self._experience.integrity_failures += 1
                self._experience.add_event("state.import_rejected", {"reason": "bad_signature"})
                raise TSKIntegrityError("Imported state signature invalid")

            # Accept
            self._public_key = public_pem
            self._private_key = private_pem
            self._node_id = state["node_id"]

            self._trust = {}
            for nid, entry in (state.get("trust") or {}).items():
                self._trust[nid] = TrustEntry(
                    node_id=entry.get("node_id", nid),
                    trust_level=float(entry.get("trust_level", 0)),
                    capabilities=list(entry.get("capabilities") or []),
                    added_at=entry.get("added_at") or _now_iso(),
                    last_seen=entry.get("last_seen"),
                    notes=entry.get("notes") or "",
                )

            caps = state.get("capabilities") or {}
            self._capabilities = dict(self.DEFAULT_CAPABILITIES)
            self._capabilities.update({k: bool(v) for k, v in caps.items()})

            exp = state.get("experience") or {}
            self._experience = ExperienceDigest(
                version=exp.get("version", "1"),
                critical_ops_ok=int(exp.get("critical_ops_ok", 0)),
                critical_ops_fail=int(exp.get("critical_ops_fail", 0)),
                integrity_failures=int(exp.get("integrity_failures", 0)),
                last_events=list(exp.get("last_events") or []),
                updated_at=exp.get("updated_at") or _now_iso(),
            )
            self._experience.add_event(
                "state.imported",
                {"export_id": state.get("export_id"), "from_node": self._node_id},
            )
            bindings = state.get("identity_bindings", [])
            self._identity_bindings = list(bindings) if isinstance(bindings, list) else []

            self._save_state()
            self._loaded = True
            return True

    @classmethod
    def from_recovery_phrase(
        cls, phrase: str, root: str | Path = "symbiont_data"
    ) -> "TrustedSecurityKernel":
        """Restore a TSK identity from a phrase, without auto-creating a random key."""
        instance = cls(root=root, auto_create=False)
        if instance.state_path.exists():
            instance._load_state()
            instance._loaded = True
        instance.recover_from_phrase(phrase)
        return instance

    def recover_from_phrase(self, phrase: str, *, allow_rekey: bool = False) -> bool:
        """Restore a TSK identity, safely resuming an interrupted recovery."""
        normalized = " ".join((phrase or "").strip().lower().split())
        if len(normalized.split()) < 8:
            raise TSKRecoveryError("Recovery phrase too short")

        seed = derive_seed_from_phrase(normalized)
        binding = _sha256(seed + b"|tsk-binding")
        private, public = _Ed25519.from_seed(seed)
        expected_id = _Ed25519.node_id_from_public(public)
        marker_path = self.root / "tsk_recovery_marker.json"

        def marker_payload() -> str:
            return json.dumps({
                "version": 1,
                "node_id": expected_id,
                "binding": binding,
                "algorithm": "Ed25519",
                "recovered_at": _now_iso(),
            }, indent=2)

        with self._lock:
            marker = None
            if marker_path.exists():
                try:
                    marker = json.loads(
                        marker_path.read_text(encoding="utf-8")
                    )
                except Exception as exc:
                    raise TSKIntegrityError(
                        "TSK recovery marker is invalid"
                    ) from exc

                if not hmac.compare_digest(
                    str(marker.get("binding", "")), binding
                ):
                    raise TSKRecoveryError(
                        "Recovery phrase does not match the bound TSK identity"
                    )

            has_identity = bool(
                self._loaded
                and self._node_id
                and self._private_key
                and self._public_key
            )

            if marker is None and has_identity and not allow_rekey:
                # Resume only if the loaded identity matches the phrase-derived
                # key pair AND the persisted state independently verifies.
                if (
                    self._node_id != expected_id
                    or self._public_key != public
                    or self._private_key != private
                ):
                    raise TSKRecoveryError(
                        "Existing TSK identity is not recovery-bound; refusing implicit re-key. "
                        "Use an empty root for recovery or explicitly authorize allow_rekey=True."
                    )

                if not self.state_path.exists():
                    raise TSKIntegrityError(
                        "Cannot resume recovery: persisted TSK state is missing"
                    )

                try:
                    raw = json.loads(
                        self.state_path.read_text(encoding="utf-8")
                    )
                    persisted_public = base64.b64decode(
                        raw.get("public_key", ""), validate=True
                    )
                    persisted_private = base64.b64decode(
                        raw.get("private_key", ""), validate=True
                    )
                    persisted_id = raw.get("node_id")

                    self._validate_key_material(
                        persisted_private, persisted_public, persisted_id
                    )

                    signature = raw.get("signature", "")
                    to_verify = {
                        key: value
                        for key, value in raw.items()
                        if key not in ("signature", "private_key")
                    }
                    if (
                        persisted_id != expected_id
                        or persisted_public != public
                        or persisted_private != private
                        or not signature
                        or not self._verify_raw(
                            public, _canonical(to_verify), signature
                        )
                    ):
                        raise TSKIntegrityError(
                            "Persisted TSK state does not match interrupted recovery"
                        )
                except TSKIntegrityError:
                    raise
                except Exception as exc:
                    raise TSKIntegrityError(
                        "Cannot validate persisted TSK state for recovery resume"
                    ) from exc

                # Complete only the missing marker; preserve persisted state.
                _atomic_write(marker_path, marker_payload())
                self._loaded = True
                return True

            if marker is not None:
                if marker.get("node_id") != expected_id:
                    raise TSKIntegrityError(
                        "Recovery marker node_id does not match derived identity"
                    )
                if self._loaded and self._node_id and self._node_id != expected_id:
                    raise TSKIntegrityError(
                        "Recovery marker and TSK state identity disagree"
                    )

                # Idempotency: preserve an already-loaded matching identity and its state.
                if has_identity:
                    if (
                        self._public_key != public
                        or self._private_key != private
                        or self._node_id != expected_id
                    ):
                        raise TSKIntegrityError(
                            "Recovery marker and loaded TSK key material disagree"
                        )
                    return True

            self._private_key = private
            self._public_key = public
            self._node_id = expected_id
            self._trust = {}
            self._identity_bindings = []
            self._capabilities = dict(self.DEFAULT_CAPABILITIES)
            self._experience = ExperienceDigest()
            self._experience.add_event(
                "tsk.recovered_from_phrase",
                {"binding": binding[:16], "node_id": self._node_id},
            )
            self._save_state()
            _atomic_write(marker_path, marker_payload())
            self._loaded = True
            return True

    # ----------------------------------------------------------
    # Experience (for future SSS)
    # ----------------------------------------------------------

    def get_experience_digest(self) -> Dict[str, Any]:
        with self._lock:
            return asdict(self._experience)

    def record_critical(self, success: bool, kind: str, detail: Optional[Dict] = None) -> None:
        with self._lock:
            if success:
                self._experience.critical_ops_ok += 1
            else:
                self._experience.critical_ops_fail += 1
            self._experience.add_event(kind, detail)
            # periodic save could be optimized; for now save on critical
            self._save_state()

    # ----------------------------------------------------------
    # Import existing NodeIdentity (migration helper)
    # ----------------------------------------------------------

    def adopt_node_identity(self, node_identity_path: str | Path) -> bool:
        """
        Safely reconcile an existing NodeIdentity without replacing a different TSK root.

        A matching key is recorded as verified. A distinct key is preserved as an
        unverified identity observation; mere co-location in a file is not proof that
        two keys belong to the same owner. Returns True when the observation is recorded.
        """
        path = Path(node_identity_path)
        if not path.exists():
            raise TSKError(f"NodeIdentity file not found: {path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            private_b64 = data.get("private_key")
            public_b64 = data.get("public_key")
            if not private_b64 or not public_b64:
                raise TSKError("NodeIdentity missing keys")
            private_pem = base64.b64decode(private_b64, validate=True)
            public_pem = base64.b64decode(public_b64, validate=True)
            derived_id = _Ed25519.node_id_from_public(public_pem)
            supplied_id = data.get("node_id")
            if supplied_id and supplied_id != derived_id:
                raise TSKIntegrityError("NodeIdentity node_id does not match public key")
            self._validate_key_material(private_pem, public_pem, derived_id)
        except TSKError:
            raise
        except Exception as exc:
            raise TSKIntegrityError(f"Invalid NodeIdentity file: {exc}") from exc

        fingerprint = hashlib.sha256(public_pem).hexdigest()
        with self._lock:
            root_id = self._node_id or ""
            root_public = self._public_key or b""
            same_key = bool(root_public) and root_public == public_pem
            status = "verified" if same_key else "unverified"
            record = {
                "identity_type": "NodeIdentity",
                "identity_id": derived_id,
                "public_key_fingerprint": fingerprint,
                "status": status,
                "root_node_id_at_observation": root_id,
                "source": path.name,
                "observed_at": _now_iso(),
                "reason": (
                    "same_public_key_as_tsk_root" if same_key
                    else "distinct_key_requires_explicit_owner_binding"
                ),
            }
            added = self._record_identity_binding(record)
            if added:
                self._experience.add_event(
                    "tsk.identity_binding_recorded",
                    {"identity_id": derived_id, "status": status, "source": path.name},
                )
                self._save_state()
            self._loaded = True
            return True

    # ----------------------------------------------------------
    # Status
    # ----------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": self.VERSION,
                "loaded": self._loaded,
                "node_id": self._node_id,
                "trusted_peers": len(self.list_trusted(0.5)),
                "fully_trusted": len(self.list_trusted(1.0)),
                "capabilities_enabled": [
                    k for k, v in self._capabilities.items() if v
                ],
                "integrity": self.get_integrity_status()["status"],
                "experience": {
                    "ok": self._experience.critical_ops_ok,
                    "fail": self._experience.critical_ops_fail,
                    "integrity_failures": self._experience.integrity_failures,
                },
            }


# ============================================================
# Factory
# ============================================================

def get_tsk(root: str | Path = "symbiont_data", **kwargs) -> TrustedSecurityKernel:
    return TrustedSecurityKernel(root=root, **kwargs)


# ============================================================
# Quick self-test when run directly
# ============================================================

if __name__ == "__main__":
    import tempfile as tf

    print("=== TSK self-test ===")
    with tf.TemporaryDirectory() as tmp:
        tsk = TrustedSecurityKernel(root=tmp)
        print("Created:", tsk.node_id())
        print("Status:", json.dumps(tsk.status(), indent=2, ensure_ascii=False))

        # Views
        print("\nContinuity view:", tsk.get_view("continuity"))
        print("Network view:", tsk.get_view("network"))

        # Trust
        tsk.register_trust("SYM-peer-test-001", trust_level=1.0, notes="test peer")
        print("Trusted:", tsk.list_trusted())

        # Capability
        tsk.grant("payment.execute")
        assert tsk.is_allowed("payment.execute")
        tsk.require("payment.execute")
        print("payment.execute: OK")

        # Sign / verify
        payload = {"action": "QUEST_OFFER", "reward": 10}
        sig = tsk.sign(payload)
        assert tsk.verify(payload, sig)
        print("Sign/verify: OK")

        # Export / Import (continuity)
        exported = tsk.export_state()
        print("Exported, export_id:", exported.get("export_id"))

        tsk2 = TrustedSecurityKernel(root=tmp + "/device_b", auto_create=False)
        tsk2.import_state(exported)
        print("Imported on device B, node_id:", tsk2.node_id())
        assert tsk2.node_id() == tsk.node_id()
        assert tsk2.is_trusted("SYM-peer-test-001")
        print("Continuity across devices: OK")

        print("\nAll checks passed.")
