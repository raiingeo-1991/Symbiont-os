import os
import json
import time
import hmac
import hashlib
import secrets
import threading
from pathlib import Path


class SecurityError(Exception):
    pass


class CapabilityGate:
    """Explicit capability authorization layer."""

    DEFAULTS = {
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

    def __init__(self):
        self._permissions = dict(self.DEFAULTS)
        self._lock = threading.RLock()

    def grant(self, capability):
        with self._lock:
            if capability not in self._permissions:
                self._permissions[capability] = False
            self._permissions[capability] = True
            return True

    def revoke(self, capability):
        with self._lock:
            if capability in self._permissions:
                self._permissions[capability] = False
            return True

    def allowed(self, capability):
        with self._lock:
            return bool(self._permissions.get(capability, False))

    def require(self, capability):
        if not self.allowed(capability):
            raise SecurityError("Capability denied: " + str(capability))
        return True

    def snapshot(self):
        with self._lock:
            return dict(self._permissions)


class ReplayGuard:
    """Rejects repeated or stale network operations."""

    def __init__(self, ttl=300):
        self.ttl = int(ttl)
        self._seen = {}
        self._lock = threading.RLock()

    def check(self, nonce, timestamp=None):
        nonce = str(nonce)
        now = time.time()

        if timestamp is not None:
            try:
                if abs(now - float(timestamp)) > self.ttl:
                    return False
            except (TypeError, ValueError):
                return False

        with self._lock:
            self._cleanup(now)

            if nonce in self._seen:
                return False

            self._seen[nonce] = now
            return True

    def _cleanup(self, now):
        expired = [
            nonce for nonce, created in self._seen.items()
            if now - created > self.ttl
        ]
        for nonce in expired:
            self._seen.pop(nonce, None)


class MessageSigner:
    """HMAC signing for local/prototype authenticated operations."""

    def __init__(self, key_path="symbiont_data/security.key"):
        self.key_path = Path(key_path)
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.key = self._load_or_create()

    def _load_or_create(self):
        with self._lock:
            if self.key_path.exists():
                data = self.key_path.read_bytes()
                if len(data) >= 32:
                    return data

            key = secrets.token_bytes(32)
            self.key_path.write_bytes(key)

            try:
                os.chmod(self.key_path, 0o600)
            except OSError:
                pass

            return key

    def sign(self, payload):
        if not isinstance(payload, bytes):
            payload = str(payload).encode("utf-8")
        return hmac.new(self.key, payload, hashlib.sha256).hexdigest()

    def verify(self, payload, signature):
        expected = self.sign(payload)
        return hmac.compare_digest(expected, str(signature))


class AuditLog:
    """Append-only security event journal."""

    def __init__(self, path="symbiont_data/security_audit.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def record(self, event, **data):
        entry = {
            "timestamp": time.time(),
            "event": str(event),
            "data": data,
        }

        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return True


class IntegrityMonitor:
    """Tracks hashes of protected files."""

    def __init__(self):
        self._baseline = {}
        self._lock = threading.RLock()

    def fingerprint(self, path):
        path = Path(path)

        if not path.exists() or not path.is_file():
            return None

        digest = hashlib.sha256()

        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)

        return digest.hexdigest()

    def register(self, path):
        value = self.fingerprint(path)

        if value is None:
            return False

        with self._lock:
            self._baseline[str(Path(path))] = value

        return True

    def verify(self, path):
        path = str(Path(path))

        with self._lock:
            expected = self._baseline.get(path)

        if expected is None:
            return False

        return hmac.compare_digest(
            expected,
            self.fingerprint(path) or ""
        )

    def snapshot(self):
        with self._lock:
            return dict(self._baseline)


class SecurityManager:
    """Unified SMSA v1 security facade."""

    VERSION = "SMSA/1"

    def __init__(self):
        self.capabilities = CapabilityGate()
        self.replay = ReplayGuard()
        self.signer = MessageSigner()
        self.audit = AuditLog()
        self.integrity = IntegrityMonitor()

    def authorize(self, capability):
        self.capabilities.require(capability)
        self.audit.record(
            "capability.authorized",
            capability=capability,
        )
        return True

    def signed_packet(self, payload):
        nonce = secrets.token_hex(16)
        timestamp = time.time()

        body = {
            "version": self.VERSION,
            "nonce": nonce,
            "timestamp": timestamp,
            "payload": payload,
        }

        raw = json.dumps(
            body,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")

        body["signature"] = self.signer.sign(raw)
        return body

    def verify_packet(self, packet):
        try:
            signature = packet["signature"]

            unsigned = {
                "version": packet["version"],
                "nonce": packet["nonce"],
                "timestamp": packet["timestamp"],
                "payload": packet["payload"],
            }

            raw = json.dumps(
                unsigned,
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")

            if not self.signer.verify(raw, signature):
                return False

            if not self.replay.check(
                packet["nonce"],
                packet["timestamp"],
            ):
                return False

            return True

        except (KeyError, TypeError, ValueError):
            return False


def get_security():
    return SecurityManager()

# ============================================================
# SMSA — Persistent Owner Policy
# ============================================================

class OwnerPolicy:
    def __init__(self, path="symbiont_data/security_policy.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        with self._lock:
            try:
                self.policy = json.loads(
                    self.path.read_text(encoding="utf-8")
                )
            except (FileNotFoundError, json.JSONDecodeError):
                self.policy = {}

    def _save(self):
        self.path.write_text(
            json.dumps(self.policy, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def grant(self, capability):
        with self._lock:
            self.policy[str(capability)] = True
            self._save()
            return True

    def revoke(self, capability):
        with self._lock:
            self.policy[str(capability)] = False
            self._save()
            return True

    def allowed(self, capability):
        with self._lock:
            return bool(self.policy.get(str(capability), False))

    def snapshot(self):
        with self._lock:
            return dict(self.policy)


class SecurePolicy:
    def __init__(self):
        self.gate = CapabilityGate()
        self.owner = OwnerPolicy()

        for capability, value in self.owner.snapshot().items():
            if value:
                self.gate.grant(capability)

    def grant(self, capability):
        self.owner.grant(capability)
        return self.gate.grant(capability)

    def revoke(self, capability):
        self.owner.revoke(capability)
        return self.gate.revoke(capability)

    def allowed(self, capability):
        return self.gate.allowed(capability)

    def require(self, capability):
        return self.gate.require(capability)

    def snapshot(self):
        return self.gate.snapshot()

# ============================================================
# SMSA — Zero Trust Network
# ============================================================

class ZeroTrustNetwork:
    def __init__(self, security=None):
        self.security = security or get_security()
        self.trusted_nodes = set()
        self._lock = threading.RLock()

    def register_node(self, node_id):
        node_id = str(node_id).strip()
        if not node_id:
            return False
        with self._lock:
            self.trusted_nodes.add(node_id)
        self.security.audit.record(
            "network.node_registered",
            node_id=node_id,
        )
        return True

    def remove_node(self, node_id):
        with self._lock:
            self.trusted_nodes.discard(str(node_id))
        return True

    def create_packet(self, sender, payload):
        packet = self.security.signed_packet({
            "sender": str(sender),
            "payload": payload,
        })
        return packet

    def verify_packet(self, packet):
        if not self.security.verify_packet(packet):
            self.security.audit.record(
                "network.packet_rejected",
                reason="signature_or_replay",
            )
            return False

        try:
            sender = str(packet["payload"]["sender"])
        except (KeyError, TypeError):
            return False

        with self._lock:
            trusted = sender in self.trusted_nodes

        if not trusted:
            self.security.audit.record(
                "network.packet_rejected",
                reason="unknown_node",
                node_id=sender,
            )
            return False

        self.security.audit.record(
            "network.packet_accepted",
            node_id=sender,
        )
        return True

    def status(self):
        with self._lock:
            return {
                "protocol": "SMSA/1",
                "zero_trust": True,
                "trusted_nodes": list(self.trusted_nodes),
            }


def get_zero_trust_network(security=None):
    return ZeroTrustNetwork(security)

# ============================================================
# SMSA — Module Registry
# ============================================================

class ModuleRegistry:
    """Controlled registry for modular Symbiont components."""

    def __init__(self, security=None, path="symbiont_data/modules.json"):
        self.security = security or get_security()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        with self._lock:
            try:
                self.modules = json.loads(
                    self.path.read_text(encoding="utf-8")
                )
            except (FileNotFoundError, json.JSONDecodeError):
                self.modules = {}

    def _save(self):
        self.path.write_text(
            json.dumps(
                self.modules,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def register(self, module_id, version="1.0", capabilities=None):
        module_id = str(module_id).strip()

        if not module_id:
            return False

        capabilities = list(capabilities or [])

        with self._lock:
            self.modules[module_id] = {
                "id": module_id,
                "version": str(version),
                "capabilities": capabilities,
                "enabled": False,
                "registered_at": time.time(),
            }
            self._save()

        self.security.audit.record(
            "module.registered",
            module_id=module_id,
            version=str(version),
            capabilities=capabilities,
        )

        return True

    def enable(self, module_id):
        with self._lock:
            module = self.modules.get(str(module_id))

            if not module:
                return False

            module["enabled"] = True
            self._save()

        self.security.audit.record(
            "module.enabled",
            module_id=str(module_id),
        )

        return True

    def disable(self, module_id):
        with self._lock:
            module = self.modules.get(str(module_id))

            if not module:
                return False

            module["enabled"] = False
            self._save()

        self.security.audit.record(
            "module.disabled",
            module_id=str(module_id),
        )

        return True

    def remove(self, module_id):
        with self._lock:
            if str(module_id) not in self.modules:
                return False

            del self.modules[str(module_id)]
            self._save()

        self.security.audit.record(
            "module.removed",
            module_id=str(module_id),
        )

        return True

    def get(self, module_id):
        with self._lock:
            module = self.modules.get(str(module_id))

            if not module:
                return None

            return dict(module)

    def list(self):
        with self._lock:
            return {
                key: dict(value)
                for key, value in self.modules.items()
            }

    def allowed(self, module_id, capability):
        module = self.get(module_id)

        if not module or not module.get("enabled"):
            return False

        return capability in module.get("capabilities", [])


def get_module_registry(security=None):
    return ModuleRegistry(security)

# ============================================================
# SMSA v1 — Unified Security Controller
# ============================================================

class SMSA:
    VERSION = "SMSA/1.0"

    def __init__(self):
        self.security = get_security()
        self.policy = SecurePolicy()

        # SMSA policy and SecurityManager must use the same
        # capability gate. This keeps SecureSettlement,
        # SMSA and OwnerPolicy on one authorization state.
        self.security.capabilities = self.policy.gate

        self.modules = ModuleRegistry(self.security)
        self.network = ZeroTrustNetwork(self.security)
        self.integrity = self.security.integrity
        self.audit = self.security.audit

    def allow(self, capability):
        return self.policy.grant(capability)

    def deny(self, capability):
        return self.policy.revoke(capability)

    def check(self, capability):
        return self.policy.allowed(capability)

    def register_module(self, module_id, version, capabilities):
        return self.modules.register(
            module_id,
            version,
            capabilities,
        )

    def enable_module(self, module_id):
        module = self.modules.get(module_id)

        if not module:
            return False

        for capability in module.get("capabilities", []):
            if not self.policy.allowed(capability):
                return False

        return self.modules.enable(module_id)

    def protect_file(self, path):
        return self.integrity.register(path)

    def verify_file(self, path):
        return self.integrity.verify(path)

    def register_node(self, node_id):
        return self.network.register_node(node_id)

    def create_packet(self, sender, payload):
        return self.network.create_packet(sender, payload)

    def verify_packet(self, packet):
        return self.network.verify_packet(packet)

    def status(self):
        return {
            "version": self.VERSION,
            "capabilities": self.policy.snapshot(),
            "modules": self.modules.list(),
            "network": self.network.status(),
            "integrity_files": len(self.integrity.snapshot()),
        }


def get_smsa():
    return SMSA()

# ============================================================
# SMSA — Economy / Quest Security Adapter
# ============================================================

class SecureSettlement:
    """
    Security boundary for financial quest operations.
    Economy remains responsible for balances and escrow state.
    SMSA authorizes and audits the operation.
    """

    def __init__(self, economy, security=None):
        self.economy = economy
        self.security = security or get_security()
        self._operations = set()
        self._lock = threading.RLock()

    def _operation_id(self, quest_id, action):
        raw = f"{action}:{quest_id}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def reserve(self, quest_id, reward, **kwargs):
        self.security.capabilities.require("payment.execute")

        op_id = self._operation_id(quest_id, "reserve")

        with self._lock:
            if op_id in self._operations:
                return False

            result = self.economy.reserve_quest(
                quest_id,
                reward,
                **kwargs
            )

            if result:
                self._operations.add(op_id)
                self.security.audit.record(
                    "settlement.reserved",
                    quest_id=str(quest_id),
                    reward=float(reward),
                    operation_id=op_id,
                )

            return result

    def release(self, quest_id, worker_node=""):
        self.security.capabilities.require("payment.execute")

        op_id = self._operation_id(quest_id, "release")

        with self._lock:
            if op_id in self._operations:
                return False

            result = self.economy.release_quest(
                quest_id,
                worker_node
            )

            if result is not False:
                self._operations.add(op_id)
                self.security.audit.record(
                    "settlement.released",
                    quest_id=str(quest_id),
                    reward=float(result),
                    worker_node=worker_node,
                    operation_id=op_id,
                )

            return result

    def refund(self, quest_id):
        self.security.capabilities.require("payment.execute")

        op_id = self._operation_id(quest_id, "refund")

        with self._lock:
            if op_id in self._operations:
                return False

            result = self.economy.refund_quest(quest_id)

            if result is not False:
                self._operations.add(op_id)
                self.security.audit.record(
                    "settlement.refunded",
                    quest_id=str(quest_id),
                    reward=float(result),
                    operation_id=op_id,
                )

            return result

    def freeze(self, quest_id, reason=""):
        self.security.capabilities.require("payment.execute")

        result = self.economy.freeze_quest(
            quest_id,
            reason
        )

        if result:
            self.security.audit.record(
                "settlement.frozen",
                quest_id=str(quest_id),
                reason=reason,
            )

        return result


def get_secure_settlement(economy, security=None):
    return SecureSettlement(economy, security)

# ============================================================
# SMSA — Genesis / Test Mint
# ============================================================

class GenesisMint:
    """
    Controlled SYM issuance for genesis/test environments.

    Minting is separate from normal payment execution.
    """

    CAPABILITY = "economy.mint"

    def __init__(self, economy, security=None):
        self.economy = economy
        self.security = security or get_security()
        self._minted = set()
        self._lock = threading.RLock()

    def mint(self, amount, recipient="owner", mint_id=None):
        self.security.capabilities.require(self.CAPABILITY)

        amount = float(amount)

        if amount <= 0:
            return False

        mint_id = str(
            mint_id or secrets.token_hex(16)
        )

        with self._lock:
            if mint_id in self._minted:
                return False

            self.economy.wallet.balance += amount
            self.economy.wallet.lifetime_received += amount
            self.economy._save()

            self._minted.add(mint_id)

            self.security.audit.record(
                "economy.mint",
                mint_id=mint_id,
                amount=amount,
                recipient=str(recipient),
            )

            return True

    def status(self):
        with self._lock:
            return {
                "capability": self.CAPABILITY,
                "enabled": self.security.capabilities.allowed(
                    self.CAPABILITY
                ),
                "operations": len(self._minted),
            }


def get_genesis_mint(economy, security=None):
    return GenesisMint(economy, security)
