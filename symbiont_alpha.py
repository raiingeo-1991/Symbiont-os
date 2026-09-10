#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SYMBIONT ALPHA
==============
Персональный автономный агент человека.

Собрано из решений:
  • Непрерывная крипто-память (batch-save)
  • Суверенная идентичность (recovery phrase → один node_id на всех устройствах)
  • Multi-device: primary / secondary
  • Переход устройства — только решением владельца
  • Авто-переход — только в неактивное время владельца
  • Конфликты памяти — primary wins
  • P2P сеть (UDP heartbeat + TCP)
  • Квесты + сетевой quorum
  • Внутренняя экономика (SYM)
  • Tool-слой + заготовка внешнего LLM
  • Когнитивный слой (состояние, мотивации, decide)

Манифест: устройство принадлежит Symbiont, Symbiont принадлежит владельцу.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import logging
import os
import secrets
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

VERSION = "ALPHA"

try:
    SCRIPT_DIR = Path(__file__).resolve().parent
except NameError:
    SCRIPT_DIR = Path(os.getcwd())

logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler(sys.stdout)])


def now() -> float:
    return time.time()


def iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(v)))


# =============================================================================
# CRYPTO
# =============================================================================
class SymbiontSecurity:
    @staticmethod
    def generate_secret() -> str:
        return uuid.uuid4().hex + uuid.uuid4().hex

    @staticmethod
    def sign_packet(secret: str, packet_dict: dict) -> str:
        clean = {k: v for k, v in packet_dict.items() if k != "signature"}
        raw = json.dumps(clean, sort_keys=True).encode("utf-8")
        return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    @staticmethod
    def verify_packet(secret: str, packet_dict: dict) -> bool:
        sig = packet_dict.get("signature", "")
        if not sig:
            return False
        clean = {k: v for k, v in packet_dict.items() if k != "signature"}
        expected = SymbiontSecurity.sign_packet(secret, clean)
        return hmac.compare_digest(expected, sig)


# =============================================================================
# IDENTITY (recovery phrase → stable node across devices)
# =============================================================================
WORDLIST = [
    "alpha", "beacon", "cipher", "delta", "echo", "forge", "gamma", "helix",
    "ion", "jade", "kernel", "lunar", "mirror", "nova", "orbit", "prism",
    "quantum", "ridge", "signal", "torch", "umbra", "vector", "wave", "xenon",
    "yield", "zenith", "anchor", "bridge", "crystal", "dawn", "ember", "flux",
    "grove", "harbor", "iris", "jewel", "keystone", "lattice", "moss", "nexus",
    "oak", "pulse", "quill", "raven", "stone", "tide", "unity", "vale",
    "willow", "axiom", "blade", "coral", "drift", "eagle", "frost", "glow",
    "haze", "ivory", "kite", "loom", "mint", "north", "opal", "pine",
    "quartz", "reef", "sage", "thorn", "ultra", "vortex", "wind", "xray",
    "yarn", "zinc", "arc", "bolt", "cove", "dune", "edge", "fern",
    "gale", "hill", "isle", "knoll", "lake", "mesa", "nest", "oasis",
    "peak", "quarry", "summit", "trail", "vale2", "ridge2", "jade2", "jade3",
]


def _normalize_phrase(phrase: str) -> str:
    return " ".join(phrase.strip().lower().split())


def generate_recovery_phrase(words: int = 12) -> str:
    chosen = [secrets.choice(WORDLIST) for _ in range(max(8, words))]
    raw = " ".join(chosen)
    chk = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:4]
    return f"{raw} {chk}"


def validate_recovery_phrase(phrase: str) -> bool:
    parts = _normalize_phrase(phrase).split()
    if len(parts) < 9:
        return False
    body, chk = " ".join(parts[:-1]), parts[-1]
    expected = hashlib.sha256(body.encode("utf-8")).hexdigest()[:4]
    return hmac.compare_digest(expected, chk)


def derive_master_seed(phrase: str, owner_salt: str = "symbiont-alpha") -> bytes:
    normalized = _normalize_phrase(phrase)
    salt = (owner_salt + "|symbiont-identity").encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", normalized.encode("utf-8"), salt, 120_000, dklen=32)


def derive_identity(master_seed: bytes) -> Dict[str, str]:
    def h(label: str) -> str:
        return hmac.new(master_seed, label.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "node_id": h("node_id")[:12],
        "node_secret": h("node_secret"),
        "fingerprint": h("fingerprint")[:16],
    }


class SymbiontIdentity:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.identity_path = self.data_dir / "identity.json"
        self._data: Optional[dict] = None

    def has_local_identity(self) -> bool:
        return self.identity_path.exists()

    def create_new(self, owner_name: str = "Architect") -> Tuple[dict, str]:
        phrase = generate_recovery_phrase(12)
        ids = derive_identity(derive_master_seed(phrase))
        record = {
            "version": 1,
            "owner_name": owner_name,
            "node_id": ids["node_id"],
            "node_secret": ids["node_secret"],
            "fingerprint": ids["fingerprint"],
            "created_at": iso(),
        }
        self._save(record)
        self._data = record
        return record, phrase

    def restore_from_phrase(self, phrase: str, owner_name: str = "Architect") -> dict:
        if not validate_recovery_phrase(phrase):
            raise ValueError("Неверная recovery-строка")
        ids = derive_identity(derive_master_seed(phrase))
        record = {
            "version": 1,
            "owner_name": owner_name,
            "node_id": ids["node_id"],
            "node_secret": ids["node_secret"],
            "fingerprint": ids["fingerprint"],
            "restored_at": iso(),
        }
        self._save(record)
        self._data = record
        return record

    def load(self) -> Optional[dict]:
        if self._data is not None:
            return self._data
        if not self.identity_path.exists():
            return None
        try:
            self._data = json.loads(self.identity_path.read_text(encoding="utf-8"))
            return self._data
        except Exception:
            return None

    def _save(self, record: dict):
        tmp = self.identity_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.identity_path)


# =============================================================================
# DEVICE REGISTRY + PRIMARY/SECONDARY + HANDOVER RULES
# =============================================================================
class DeviceRegistry:
    """
    Правила:
      • Переход primary — только решением владельца
      • Авто-handover — только если владелец неактивен
      • Только primary принимает команды владельца
    """

    def __init__(self, data_dir: Path, node_id: str, inactive_threshold_sec: float = 300.0):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.data_dir / "devices.json"
        self.node_id = node_id
        self.inactive_threshold = inactive_threshold_sec
        self.lock = threading.RLock()
        self.data = self._load()

    def _default(self) -> dict:
        device_id = uuid.uuid4().hex[:10]
        return {
            "node_id": self.node_id,
            "this_device_id": device_id,
            "primary_device_id": device_id,
            "devices": {
                device_id: {
                    "label": "primary-init",
                    "first_seen": iso(),
                    "last_seen": iso(),
                    "last_chain_len": 0,
                    "last_hash": "",
                }
            },
            "last_owner_activity": now(),
            "owner_inactive_threshold_sec": self.inactive_threshold,
            "auto_handover_enabled": True,
        }

    def _load(self) -> dict:
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                base = self._default()
                base.update(d)
                if "this_device_id" not in base or not base["this_device_id"]:
                    base["this_device_id"] = uuid.uuid4().hex[:10]
                if base["this_device_id"] not in base.get("devices", {}):
                    base.setdefault("devices", {})[base["this_device_id"]] = {
                        "label": "restored",
                        "first_seen": iso(),
                        "last_seen": iso(),
                        "last_chain_len": 0,
                        "last_hash": "",
                    }
                return base
            except Exception:
                pass
        return self._default()

    def save(self):
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def touch_owner_activity(self):
        with self.lock:
            self.data["last_owner_activity"] = now()
            self.save()

    def owner_is_inactive(self) -> bool:
        with self.lock:
            return (now() - float(self.data.get("last_owner_activity", now()))) >= float(
                self.data.get("owner_inactive_threshold_sec", self.inactive_threshold)
            )

    def idle_seconds(self) -> float:
        with self.lock:
            return now() - float(self.data.get("last_owner_activity", now()))

    def this_device_id(self) -> str:
        return self.data["this_device_id"]

    def primary_device_id(self) -> str:
        return self.data.get("primary_device_id", self.data["this_device_id"])

    def is_primary(self) -> bool:
        return self.this_device_id() == self.primary_device_id()

    def register_or_update_device(self, device_id: str, label: str = "",
                                  chain_len: int = 0, last_hash: str = ""):
        with self.lock:
            devices = self.data.setdefault("devices", {})
            if device_id not in devices:
                devices[device_id] = {
                    "label": label or device_id,
                    "first_seen": iso(),
                    "last_seen": iso(),
                    "last_chain_len": chain_len,
                    "last_hash": last_hash,
                }
            else:
                devices[device_id]["last_seen"] = iso()
                devices[device_id]["last_chain_len"] = chain_len
                devices[device_id]["last_hash"] = last_hash
                if label:
                    devices[device_id]["label"] = label
            self.save()

    def owner_handover(self, target_device_id: str) -> Tuple[bool, str]:
        with self.lock:
            if target_device_id not in self.data.get("devices", {}):
                return False, f"Устройство {target_device_id} неизвестно"
            old = self.data["primary_device_id"]
            self.data["primary_device_id"] = target_device_id
            self.data["last_owner_activity"] = now()
            self.save()
            return True, f"Primary: {old} → {target_device_id}"

    def try_auto_handover(self, target_device_id: str) -> Tuple[bool, str]:
        with self.lock:
            if not self.data.get("auto_handover_enabled", True):
                return False, "Авто-handover отключён"
            if not self.owner_is_inactive():
                return False, (
                    f"Владелец активен (idle {self.idle_seconds():.0f}s). "
                    "Авто-переход запрещён."
                )
            if target_device_id not in self.data.get("devices", {}):
                return False, f"Устройство {target_device_id} неизвестно"
            old = self.data["primary_device_id"]
            self.data["primary_device_id"] = target_device_id
            self.save()
            return True, f"Авто-handover (idle): {old} → {target_device_id}"

    def status(self) -> dict:
        with self.lock:
            return {
                "this_device_id": self.this_device_id(),
                "primary_device_id": self.primary_device_id(),
                "is_primary": self.is_primary(),
                "owner_idle_sec": round(self.idle_seconds(), 1),
                "owner_inactive": self.owner_is_inactive(),
                "inactive_threshold_sec": self.data.get("owner_inactive_threshold_sec"),
                "known_devices": list(self.data.get("devices", {}).keys()),
            }


# =============================================================================
# MEMORY (batch save) + SYNC (primary wins on conflict)
# =============================================================================
class AmbientMemoryStream:
    def __init__(self, node_identity: str, owner_name: str, storage_path: Path,
                 flush_every: int = 10, flush_interval: float = 5.0):
        self.identity = node_identity
        self.owner = owner_name
        self.path = Path(storage_path)
        self.lock = threading.RLock()
        self.flush_every = max(1, flush_every)
        self.flush_interval = max(1.0, flush_interval)
        self._dirty = False
        self._ops_since_flush = 0
        self._last_flush = now()
        self.memory_chain = self._load_chain()
        self._stop_flusher = False
        self._flusher = threading.Thread(target=self._flush_loop, daemon=True)
        self._flusher.start()

    def _load_chain(self) -> List[Dict[str, Any]]:
        with self.lock:
            bak = self.path.with_suffix(".bak")
            for p in (self.path, bak):
                if p.exists():
                    try:
                        data = json.loads(p.read_text(encoding="utf-8"))
                        if isinstance(data, list) and data:
                            return data
                    except Exception:
                        pass
            genesis = {
                "index": 0,
                "timestamp": now(),
                "who_am_i": self.identity,
                "what_am_i_doing": "Genesis Ambient Stream (ALPHA)",
                "who_is_the_agent": self.owner,
                "prior_context": "None (Genesis)",
            }
            genesis["hash"] = self._hash_block(genesis)
            return [genesis]

    def _hash_block(self, block_data: Dict[str, Any]) -> str:
        clean = {k: v for k, v in block_data.items() if k != "hash"}
        return hashlib.sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest()

    def ingest_transcript(self, raw_transcript: str, force_flush: bool = False) -> Dict[str, Any]:
        with self.lock:
            last = self.memory_chain[-1]
            block = {
                "index": len(self.memory_chain),
                "timestamp": now(),
                "who_am_i": self.identity,
                "what_am_i_doing": f"Absorbed: '{raw_transcript[:40]}...'",
                "who_is_the_agent": self.owner,
                "prior_context": last["hash"],
                "payload": raw_transcript,
            }
            block["hash"] = self._hash_block(block)
            self.memory_chain.append(block)
            self._dirty = True
            self._ops_since_flush += 1
            if force_flush or self._ops_since_flush >= self.flush_every:
                self._save_chain_unlocked()
            return block

    def _flush_loop(self):
        while not self._stop_flusher:
            time.sleep(1.0)
            with self.lock:
                if self._dirty and (now() - self._last_flush) >= self.flush_interval:
                    self._save_chain_unlocked()

    def flush(self):
        with self.lock:
            if self._dirty:
                self._save_chain_unlocked()

    def _save_chain_unlocked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        bak, tmp = self.path.with_suffix(".bak"), self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.memory_chain, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        if self.path.exists():
            try:
                if bak.exists():
                    bak.unlink()
                self.path.rename(bak)
            except Exception:
                pass
        tmp.replace(self.path)
        self._dirty = False
        self._ops_since_flush = 0
        self._last_flush = now()

    def verify_integrity(self) -> Tuple[bool, str]:
        with self.lock:
            for i, block in enumerate(self.memory_chain):
                if block.get("hash") != self._hash_block(block):
                    return False, f"Hash mismatch at #{i}"
                if i > 0 and block.get("prior_context") != self.memory_chain[i - 1].get("hash"):
                    return False, f"Broken link at #{i}"
            return True, "Chain OK"

    def search_memory(self, query: str) -> List[Dict[str, Any]]:
        q = query.lower()
        with self.lock:
            return [
                b for b in self.memory_chain
                if q in b.get("payload", "").lower() or q in b.get("what_am_i_doing", "").lower()
            ]

    def recall_identity(self) -> str:
        with self.lock:
            facts = [b.get("payload", "") for b in self.memory_chain if b.get("payload")]
            if not facts:
                return "Пока нет данных о тебе в цепи памяти."
            lines = ["На основе криптографической памяти:"]
            for i, f in enumerate(facts, 1):
                lines.append(f"  [{i}] {f}")
            return "\n".join(lines)

    def stop(self):
        self._stop_flusher = True
        self.flush()


class MemorySyncEngine:
    """Merge с правилом: при конфликте index+разный hash → primary wins."""

    def __init__(self, node):
        self.node = node
        self.lock = threading.RLock()

    def export_snapshot(self) -> dict:
        chain = self.node.memory.memory_chain
        return {
            "protocol": "SYMBIONT-SYNC-ALPHA",
            "node_id": self.node.node_id,
            "device_id": self.node.devices.this_device_id(),
            "is_primary": self.node.devices.is_primary(),
            "chain_length": len(chain),
            "latest_hash": chain[-1]["hash"] if chain else "",
            "chain": list(chain),
            "timestamp": now(),
        }

    def merge_remote(self, remote: dict, local_is_primary: bool) -> dict:
        with self.lock:
            if remote.get("node_id") and remote["node_id"] != self.node.node_id:
                return {"ok": False, "error": "node_id mismatch"}

            remote_chain = remote.get("chain") or []
            local_by_idx = {b["index"]: b for b in self.node.memory.memory_chain}
            added = replaced = skipped = 0

            for rb in remote_chain:
                idx = rb.get("index")
                if idx is None:
                    continue
                if idx not in local_by_idx:
                    local_by_idx[idx] = rb
                    added += 1
                else:
                    lb = local_by_idx[idx]
                    if lb.get("hash") == rb.get("hash"):
                        skipped += 1
                        continue
                    # CONFLICT: primary wins
                    if local_is_primary:
                        skipped += 1  # keep local (primary)
                    else:
                        local_by_idx[idx] = rb
                        replaced += 1

            new_chain = [local_by_idx[i] for i in sorted(local_by_idx.keys())]
            with self.node.memory.lock:
                self.node.memory.memory_chain = new_chain
                self.node.memory._dirty = True
                if added or replaced:
                    self.node.memory._save_chain_unlocked()

            self.node.devices.register_or_update_device(
                remote.get("device_id", "unknown"),
                chain_len=len(remote_chain),
                last_hash=remote.get("latest_hash", ""),
            )
            return {
                "ok": True,
                "from_device": remote.get("device_id"),
                "added": added,
                "replaced": replaced,
                "skipped": skipped,
                "local_len": len(new_chain),
                "policy": "primary_wins",
            }


# =============================================================================
# ECONOMY
# =============================================================================
class EconomyLayer:
    def __init__(self, node, path: Path, initial_balance: float = 10.0):
        self.node = node
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data = self._load(initial_balance)

    def _default(self, initial: float):
        return {
            "balance": float(initial),
            "currency": "SYM",
            "daily_food_target": 10.0,
            "history": [],
        }

    def _load(self, initial: float):
        try:
            if self.path.exists():
                d = json.loads(self.path.read_text(encoding="utf-8"))
                base = self._default(initial)
                base.update(d)
                return base
        except Exception:
            pass
        return self._default(initial)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def balance(self) -> float:
        with self.lock:
            return self.data["balance"]

    def credit(self, amount: float, reason: str, meta: dict = None) -> float:
        with self.lock:
            self.data["balance"] = round(self.data["balance"] + float(amount), 6)
            self.data["history"].append({
                "id": uuid.uuid4().hex[:12], "ts": iso(), "type": "credit",
                "amount": float(amount), "reason": reason, "meta": meta or {},
                "balance_after": self.data["balance"],
            })
            self.data["history"] = self.data["history"][-2048:]
            self.save()
            return self.data["balance"]

    def debit(self, amount: float, reason: str, meta: dict = None) -> Tuple[bool, float]:
        with self.lock:
            amount = float(amount)
            if self.data["balance"] < amount:
                return False, self.data["balance"]
            self.data["balance"] = round(self.data["balance"] - amount, 6)
            self.data["history"].append({
                "id": uuid.uuid4().hex[:12], "ts": iso(), "type": "debit",
                "amount": amount, "reason": reason, "meta": meta or {},
                "balance_after": self.data["balance"],
            })
            self.data["history"] = self.data["history"][-2048:]
            self.save()
            return True, self.data["balance"]

    def settle_quest_reward(self, quest_id: str, reward: float, from_node: str = "network") -> float:
        return self.credit(reward, f"Quest reward #{quest_id}", {"from": from_node, "quest_id": quest_id})

    def status(self) -> dict:
        with self.lock:
            return {
                "balance": self.data["balance"],
                "currency": self.data["currency"],
                "daily_food_target": self.data["daily_food_target"],
                "history_len": len(self.data["history"]),
            }


# =============================================================================
# TOOLS
# =============================================================================
class ToolRegistry:
    def __init__(self, node):
        self.node = node
        self.tools: Dict[str, Callable] = {}
        self.register("memory_search", self._memory_search)
        self.register("get_balance", lambda: self.node.economy.status())
        self.register("list_peers", self._list_peers)
        self.register("verify_chain", self._verify)
        self.register("ask_external_llm", self._ask_llm)

    def register(self, name: str, fn: Callable):
        self.tools[name] = fn

    def call(self, name: str, **kwargs) -> dict:
        if name not in self.tools:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        try:
            result = self.tools[name](**kwargs)
            self.node.cognitive.record_experience(f"Tool: {name}", "success", 0.4)
            return {"ok": True, "tool": name, "result": result}
        except Exception as e:
            return {"ok": False, "tool": name, "error": str(e)}

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())

    def _memory_search(self, query: str = "") -> list:
        return [
            {"index": b.get("index"), "payload": (b.get("payload") or "")[:120]}
            for b in self.node.memory.search_memory(query)[:10]
        ]

    def _list_peers(self) -> list:
        return [
            {"id": pid, "identity": p["identity"], "ip": p["ip"]}
            for pid, p in self.node.network.active_peers.items()
        ]

    def _verify(self) -> dict:
        ok, msg = self.node.memory.verify_integrity()
        return {"valid": ok, "message": msg}

    def _ask_llm(self, prompt: str = "", max_tokens: int = 256) -> dict:
        return {
            "provider": "stub",
            "prompt_preview": (prompt or "")[:80],
            "answer": "[LLM stub] Подключи реальный API в ToolRegistry._ask_llm",
        }


# =============================================================================
# COGNITIVE
# =============================================================================
class SymbiontCognitiveLayer:
    DEFAULT_STATE = {
        "confidence": 0.5, "trust": 0.6, "caution": 0.4, "stress": 0.1,
        "interest": 0.5, "satisfaction": 0.5, "urgency": 0.0, "attachment": 0.5,
    }
    DEFAULT_MOTIVATIONS = [
        "PROTECT_OWNER", "MAINTAIN_SURVIVAL", "PRESERVE_CORE",
        "OWNER_GOALS", "LEARN", "SUPPORT_NETWORK",
    ]

    def __init__(self, node, path: Path):
        self.node = node
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data = self._load()

    def _default(self):
        return {
            "experience": [],
            "internal_state": copy.deepcopy(self.DEFAULT_STATE),
            "motivations": list(self.DEFAULT_MOTIVATIONS),
            "goals": [],
            "autonomy_level": 0.5,
            "owner_trust": 0.6,
            "assigned_name": "Сим",
            "node_secret": None,  # set from identity
            "whitelist": {},
            "last_decision": None,
        }

    def _load(self):
        try:
            if self.path.exists():
                d = json.loads(self.path.read_text(encoding="utf-8"))
                base = self._default()
                base.update(d)
                if not base.get("assigned_name"):
                    base["assigned_name"] = "Сим"
                return base
        except Exception:
            pass
        return self._default()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def adapt_state_and_identity(self, transcript: str):
        with self.lock:
            t = transcript.lower().strip("?!.,:;")
            words = set(t.split())
            s = self.data["internal_state"]
            if t in ("сим", "ты сим"):
                self.data["assigned_name"] = "Сим"
            elif t.startswith("тебя зовут "):
                name = t.replace("тебя зовут", "").strip().capitalize()
                if name and len(name) < 15:
                    self.data["assigned_name"] = name
            if words & {"устал", "сложно", "проблема", "тяжело", "ошибка", "стресс", "бесит"}:
                s["stress"] = clamp(s["stress"] + 0.15)
                s["satisfaction"] = clamp(s["satisfaction"] - 0.1)
                s["urgency"] = clamp(s["urgency"] + 0.1)
            if words & {"отлично", "круто", "работает", "успех", "понял", "здорово", "класс"}:
                s["satisfaction"] = clamp(s["satisfaction"] + 0.15)
                s["stress"] = clamp(s["stress"] - 0.1)
                s["confidence"] = clamp(s["confidence"] + 0.05)
            if words & {"интересно", "узнать", "почему", "научить", "исследовать"}:
                s["interest"] = clamp(s["interest"] + 0.1)
            self.recalculate_motivations()
            self.save()

    def recalculate_motivations(self):
        s = self.data["internal_state"]
        m = list(self.DEFAULT_MOTIVATIONS)
        if s["urgency"] > 0.6 or s["stress"] > 0.7:
            m.insert(0, "HANDLE_CRITICAL_SITUATION")
        if hasattr(self.node, "economy") and self.node.economy.balance() < 10:
            m.insert(0, "SECURE_RESOURCES")
        self.data["motivations"] = m
        return m

    def decide(self, situation: str, options: list, use_tools: bool = False) -> dict:
        with self.lock:
            if not options:
                return {"decision": None, "reason": "нет вариантов"}
            text = str(situation).lower()
            s = self.data["internal_state"]
            critical = any(x in text for x in ("опасность", "атака", "сбой", "критично", "угроза"))
            tool_hints = []
            if use_tools and hasattr(self.node, "tools"):
                if any(x in text for x in ("память", "раньше", "история")):
                    r = self.node.tools.call("memory_search", query=situation[:60])
                    if r.get("ok"):
                        tool_hints.append(f"memory:{len(r['result'])}")
                if any(x in text for x in ("баланс", "деньги", "награда")):
                    r = self.node.tools.call("get_balance")
                    if r.get("ok"):
                        tool_hints.append(f"balance:{r['result'].get('balance')}")
            scored = []
            for i, opt in enumerate(options):
                ot = str(opt).lower()
                score = 0.0
                if critical and any(x in ot for x in ("защитить", "исправить", "помочь", "безопасность")):
                    score += 5.0 + s["caution"] * 1.5
                if any(x in ot for x in ("игнорировать", "риск", "удалить", "отключить")):
                    score -= 4.0 + s["stress"]
                mots = " ".join(self.data.get("motivations", [])).lower()
                if "protect" in mots and "защит" in ot:
                    score += 1.2
                if "secure_resources" in mots and any(x in ot for x in ("заработок", "награда", "квест")):
                    score += 1.5
                score += s["confidence"] * 0.6
                scored.append((score, -i, opt))
            scored.sort(reverse=True)
            result = {
                "decision": scored[0][2],
                "reason": "безопасность, мотивации, экономика, автономия",
                "scores": [{"option": x[2], "score": round(x[0], 3)} for x in scored],
                "tool_hints": tool_hints,
                "time": iso(),
            }
            self.data["last_decision"] = result
            self.save()
            return result

    def record_experience(self, event, outcome="recorded", importance=0.5):
        with self.lock:
            e = {
                "id": uuid.uuid4().hex, "time": iso(),
                "event": str(event)[:1000], "outcome": outcome,
                "importance": clamp(importance),
                "state": dict(self.data["internal_state"]),
            }
            self.data["experience"].append(e)
            self.data["experience"] = self.data["experience"][-2048:]
            success = str(outcome).lower() in {"success", "verified", "completed", "успех", "выполнено"}
            delta = (0.02 if success else -0.01) * clamp(importance)
            self.data["internal_state"]["confidence"] = clamp(
                self.data["internal_state"]["confidence"] + delta
            )
            self.save()
            return e


# =============================================================================
# QUESTS
# =============================================================================
class QuestEngine:
    def __init__(self, node):
        self.node = node
        self.lock = threading.RLock()
        self.open_quests: Dict[str, dict] = {}
        self.pending_completions: Dict[str, dict] = {}

    def create_quest(self, title: str, reward: float, requirements: str) -> dict:
        with self.lock:
            qid = uuid.uuid4().hex[:10]
            payload = {
                "type": "QUEST_CREATED", "quest_id": qid, "title": title,
                "reward": float(reward), "requirements": requirements,
                "creator": self.node.memory.identity, "creator_id": self.node.node_id,
                "status": "OPEN", "approvals": [], "created_at": iso(),
            }
            self.open_quests[qid] = payload
            self.node.memory.ingest_transcript(json.dumps(payload, ensure_ascii=False))
            self.node.cognitive.record_experience(f"Created quest: {title}", "success", 0.9)
            return payload

    def execute_and_verify_quest(self, quest_id: str, proof: str) -> dict:
        with self.lock:
            payload = {
                "type": "QUEST_COMPLETED", "quest_id": quest_id, "proof": proof,
                "executor": self.node.memory.identity, "executor_id": self.node.node_id,
                "status": "PENDING_CONSENSUS", "signatures": [self.node.node_id],
                "approvals": [], "timestamp": iso(),
            }
            self.pending_completions[quest_id] = payload
            self.node.memory.ingest_transcript(json.dumps(payload, ensure_ascii=False))
            threading.Thread(target=self._request_approvals, args=(quest_id,), daemon=True).start()
            return payload

    def _request_approvals(self, quest_id: str):
        peers = list(self.node.network.active_peers.items())
        if not peers:
            time.sleep(0.3)
            self.add_consensus_approval(quest_id, self.node.node_id)
            return
        for peer_id, info in peers:
            try:
                self._send_approve(peer_id, info, quest_id)
            except Exception:
                pass

    def _send_approve(self, peer_id: str, info: dict, quest_id: str):
        secret = self.node.cognitive.data["node_secret"]
        req = {
            "protocol": "SYMBIONT-ALPHA",
            "node_id": self.node.node_id,
            "action": "QUEST_APPROVE",
            "quest_id": quest_id,
            "timestamp": now(),
        }
        req["signature"] = SymbiontSecurity.sign_packet(secret, req)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(4.0)
            sock.connect((info["ip"], info.get("tcp_port", 37171)))
            sock.sendall(json.dumps(req, ensure_ascii=False).encode())
            data = sock.recv(4096)
            sock.close()
            if data and json.loads(data.decode()).get("status") == "APPROVED":
                self.add_consensus_approval(quest_id, peer_id)
        except Exception:
            pass

    def add_consensus_approval(self, quest_id: str, peer_id: str):
        with self.lock:
            if quest_id not in self.pending_completions:
                self.node.memory.ingest_transcript(json.dumps({
                    "type": "QUEST_CONSENSUS_APPROVED",
                    "quest_id": quest_id, "approved_by": peer_id, "status": "VERIFIED",
                }, ensure_ascii=False))
                return
            c = self.pending_completions[quest_id]
            if peer_id not in c["approvals"]:
                c["approvals"].append(peer_id)
            known = max(1, len(self.node.network.active_peers))
            needed = max(1, (known // 2) + 1)
            if len(c["approvals"]) >= needed:
                c["status"] = "VERIFIED"
                if c.get("executor_id") == self.node.node_id and quest_id in self.open_quests:
                    reward = float(self.open_quests[quest_id].get("reward", 0))
                    if reward > 0:
                        self.node.economy.settle_quest_reward(quest_id, reward)
                self.node.memory.ingest_transcript(json.dumps({
                    "type": "QUEST_CONSENSUS_REACHED",
                    "quest_id": quest_id, "approvals": c["approvals"], "status": "VERIFIED",
                }, ensure_ascii=False))


# =============================================================================
# NETWORK
# =============================================================================
class SymbiontNetworkLayer:
    def __init__(self, node, udp_port=37170, tcp_port=37171, timeout=15.0):
        self.node = node
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.timeout = timeout
        self.running = False
        self.active_peers: Dict[str, dict] = {}
        self.lock = threading.RLock()

    def start(self):
        self.running = True
        for target in (
            self._udp_listen_loop,
            self._udp_broadcast_loop,
            self._monitor_peers_loop,
            self._tcp_server_loop,
        ):
            threading.Thread(target=target, daemon=True).start()
        logging.info(f"[*] P2P ALPHA (UDP {self.udp_port}, TCP {self.tcp_port})")

    def stop(self):
        self.running = False

    def _broadcast_ips(self) -> List[str]:
        out = {"<broadcast>", "255.255.255.255"}
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            parts = ip.split(".")
            if len(parts) == 4:
                out.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
        except Exception:
            pass
        return list(out)

    def _udp_listen_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", self.udp_port))
        except Exception as e:
            logging.warning(f"[!] UDP bind: {e}")
            return
        sock.settimeout(1.0)
        while self.running:
            try:
                data, addr = sock.recvfrom(4096)
                packet = json.loads(data.decode())
                peer_id = packet.get("node_id")
                if peer_id == self.node.node_id:
                    continue
                wl = self.node.cognitive.data["whitelist"]
                if peer_id not in wl and packet.get("node_secret"):
                    wl[peer_id] = {"secret": packet["node_secret"], "ip": addr[0]}
                    self.node.cognitive.save()
                info = wl.get(peer_id)
                if info and SymbiontSecurity.verify_packet(info["secret"], packet):
                    with self.lock:
                        is_new = peer_id not in self.active_peers
                        self.active_peers[peer_id] = {
                            "identity": packet.get("identity"),
                            "ip": addr[0],
                            "tcp_port": packet.get("tcp_port", self.tcp_port),
                            "last_seen": now(),
                            "chain_length": packet.get("chain_length"),
                        }
                        if is_new:
                            print(f"\n[+] Peer: [{packet.get('identity')}] {addr[0]}")
            except socket.timeout:
                continue
            except Exception:
                pass
        sock.close()

    def _udp_broadcast_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while self.running:
            try:
                secret = self.node.cognitive.data["node_secret"]
                packet = {
                    "protocol": "SYMBIONT-ALPHA",
                    "node_id": self.node.node_id,
                    "node_secret": secret,
                    "identity": self.node.assigned_name,
                    "tcp_port": self.tcp_port,
                    "latest_hash": self.node.memory.memory_chain[-1]["hash"],
                    "chain_length": len(self.node.memory.memory_chain),
                    "timestamp": now(),
                }
                packet["signature"] = SymbiontSecurity.sign_packet(secret, packet)
                raw = json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()
                for t in self._broadcast_ips():
                    try:
                        sock.sendto(raw, (t, self.udp_port))
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(3.0)
        sock.close()

    def _monitor_peers_loop(self):
        while self.running:
            time.sleep(3.0)
            t = now()
            with self.lock:
                offline = [pid for pid, p in self.active_peers.items() if t - p["last_seen"] > self.timeout]
                for pid in offline:
                    p = self.active_peers.pop(pid)
                    print(f"\n[!] Offline: [{p['identity']}] {pid}")

    def _tcp_server_loop(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("", self.tcp_port))
            server.listen(8)
        except Exception as e:
            logging.warning(f"[!] TCP: {e}")
            return
        while self.running:
            try:
                server.settimeout(1.0)
                conn, addr = server.accept()
                threading.Thread(target=self._handle_tcp, args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                pass
        server.close()

    def _handle_tcp(self, conn: socket.socket):
        try:
            conn.settimeout(5.0)
            data = conn.recv(65536)
            if not data:
                return
            req = json.loads(data.decode())
            peer_id = req.get("node_id")
            wl = self.node.cognitive.data["whitelist"]
            if peer_id in wl and SymbiontSecurity.verify_packet(wl[peer_id]["secret"], req):
                action = req.get("action")
                if action == "SYNC_MEMORY":
                    snap = self.node.sync_engine.export_snapshot()
                    conn.sendall(json.dumps({"status": "OK", "snapshot": snap}, ensure_ascii=False).encode())
                elif action == "QUEST_APPROVE":
                    self.node.quests.add_consensus_approval(req.get("quest_id"), peer_id)
                    conn.sendall(json.dumps({"status": "APPROVED"}).encode())
                elif action == "GET_BALANCE":
                    conn.sendall(json.dumps({
                        "status": "OK", "economy": self.node.economy.status()
                    }, ensure_ascii=False).encode())
                else:
                    conn.sendall(json.dumps({"status": "UNKNOWN"}).encode())
            else:
                conn.sendall(json.dumps({"status": "UNAUTHORIZED"}).encode())
        except Exception:
            pass
        finally:
            conn.close()


# =============================================================================
# MASTER NODE — SYMBIONT ALPHA
# =============================================================================
class SymbiontAlpha:
    def __init__(
        self,
        owner_name: str = "Architect",
        recovery_phrase: str = None,
        udp_port: int = 37170,
        tcp_port: int = 37171,
        data_dir: Path = None,
    ):
        self.owner = owner_name
        self.data_dir = Path(data_dir) if data_dir else (SCRIPT_DIR / "symbiont_alpha_data")
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        # --- Identity ---
        self.identity_mgr = SymbiontIdentity(self.data_dir)
        self._recovery_phrase_shown: Optional[str] = None
        if recovery_phrase:
            rec = self.identity_mgr.restore_from_phrase(recovery_phrase, owner_name)
        elif self.identity_mgr.has_local_identity():
            rec = self.identity_mgr.load()
        else:
            rec, phrase = self.identity_mgr.create_new(owner_name)
            self._recovery_phrase_shown = phrase

        self.node_id = rec["node_id"]
        self.node_secret = rec["node_secret"]
        self.fingerprint = rec.get("fingerprint", "")

        # --- Cognitive (secret from identity) ---
        self.cognitive = SymbiontCognitiveLayer(self, self.data_dir / "cognitive.json")
        self.cognitive.data["node_secret"] = self.node_secret
        self.cognitive.save()
        self.assigned_name = self.cognitive.data.get("assigned_name", "Сим")

        # --- Memory ---
        self.memory = AmbientMemoryStream(
            self.assigned_name, self.owner,
            self.data_dir / "memory_chain.json",
            flush_every=10, flush_interval=5.0,
        )

        # --- Devices (primary/secondary) ---
        self.devices = DeviceRegistry(self.data_dir, self.node_id, inactive_threshold_sec=300.0)
        self.sync_engine = MemorySyncEngine(self)

        # --- Economy, Quests, Tools, Network ---
        self.economy = EconomyLayer(self, self.data_dir / "economy.json", initial_balance=10.0)
        self.quests = QuestEngine(self)
        self.tools = ToolRegistry(self)
        self.network = SymbiontNetworkLayer(self, udp_port=udp_port, tcp_port=tcp_port)
        self.network.start()

        role = "PRIMARY" if self.devices.is_primary() else "SECONDARY"
        logging.info(
            f"[*] Symbiont ALPHA [{self.assigned_name}] online | "
            f"node={self.node_id} | device={self.devices.this_device_id()} | {role} | "
            f"blocks={len(self.memory.memory_chain)} | balance={self.economy.balance()} SYM"
        )
        if self._recovery_phrase_shown:
            print("\n" + "!" * 60)
            print("  ЗАПИШИ RECOVERY PHRASE (больше не покажется):")
            print(f"  {self._recovery_phrase_shown}")
            print("!" * 60 + "\n")

    def require_primary(self) -> bool:
        """Команды владельца только на primary."""
        if self.devices.is_primary():
            return True
        print(
            f"[!] Это SECONDARY устройство ({self.devices.this_device_id()}). "
            f"Primary: {self.devices.primary_device_id()}. "
            "Команды владельца принимаются только на primary."
        )
        return False

    def process_owner_input(self, text: str):
        if not self.require_primary():
            return None
        self.devices.touch_owner_activity()
        block = self.memory.ingest_transcript(text)
        self.cognitive.adapt_state_and_identity(text)
        name = self.cognitive.data.get("assigned_name", "Сим")
        if name != self.assigned_name:
            self.assigned_name = name
            self.memory.identity = name
        self.cognitive.record_experience(f"Input: {text[:40]}", importance=0.8)
        return block

    def shutdown(self):
        self.memory.stop()
        self.network.stop()
        self.memory.flush()
        self.cognitive.save()
        self.economy.save()
        self.devices.save()


# =============================================================================
# REPL
# =============================================================================
def main():
    print(f"=== SYMBIONT {VERSION} ===")
    print("Команды: status | devices | handover <id> | sync | restore <phrase>")
    print("         balance | tools | quest | complete <id> | peers | audit | exit")
    print()

    # optional: restore from argv
    phrase = None
    if len(sys.argv) > 2 and sys.argv[1] == "--restore":
        phrase = " ".join(sys.argv[2:])

    node = SymbiontAlpha(owner_name="Architect", recovery_phrase=phrase)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        print(f"[*] IP: {s.getsockname()[0]}")
        s.close()
    except Exception:
        pass

    while True:
        try:
            tag = node.assigned_name
            role = "P" if node.devices.is_primary() else "S"
            cmd = input(f"{tag}[{role}] > ").strip()
            if not cmd:
                continue
            cl = cmd.lower().rstrip("?").strip()

            if cl in ("exit", "quit", "выход"):
                node.shutdown()
                print("[INFO] Shutdown.")
                break

            # --- multi-device (allowed on any device for status/sync) ---
            elif cl in ("devices", "устройство", "устройства"):
                st = node.devices.status()
                print(f"-> this={st['this_device_id']} primary={st['primary_device_id']} "
                      f"is_primary={st['is_primary']}")
                print(f"   idle={st['owner_idle_sec']}s inactive={st['owner_inactive']}")
                print(f"   known={st['known_devices']}\n")

            elif cl.startswith("handover "):
                if not node.require_primary():
                    continue
                node.devices.touch_owner_activity()
                tid = cmd.split(maxsplit=1)[1].strip()
                ok, msg = node.devices.owner_handover(tid)
                print(f"-> {msg}\n")

            elif cl == "sync":
                # export local snapshot (for manual transfer / future TCP pull)
                snap = node.sync_engine.export_snapshot()
                out = node.data_dir / "sync_export.json"
                out.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
                print(f"-> Snapshot exported: {out} ({snap['chain_length']} blocks)\n")

            elif cl.startswith("sync from "):
                path = cmd.split(maxsplit=2)[2].strip()
                try:
                    remote = json.loads(Path(path).read_text(encoding="utf-8"))
                    report = node.sync_engine.merge_remote(
                        remote, local_is_primary=node.devices.is_primary()
                    )
                    print(f"-> Merge: {report}\n")
                except Exception as e:
                    print(f"[!] {e}\n")

            elif cl.startswith("restore "):
                ph = cmd[8:].strip()
                try:
                    node.shutdown()
                    node = SymbiontAlpha(owner_name="Architect", recovery_phrase=ph)
                    print("-> Restored from phrase.\n")
                except Exception as e:
                    print(f"[!] {e}\n")

            # --- owner commands (primary only) ---
            elif cl in ("balance", "баланс"):
                if not node.require_primary():
                    continue
                st = node.economy.status()
                print(f"-> {st['balance']} {st['currency']} | food target {st['daily_food_target']}\n")

            elif cl in ("tools", "инструменты"):
                print(f"-> {node.tools.list_tools()}\n")

            elif cl.startswith("tool "):
                if not node.require_primary():
                    continue
                parts = cmd.split(maxsplit=2)
                name = parts[1] if len(parts) > 1 else ""
                arg = parts[2] if len(parts) > 2 else ""
                if name == "ask_external_llm":
                    res = node.tools.call(name, prompt=arg or "Who am I?")
                elif name == "memory_search":
                    res = node.tools.call(name, query=arg)
                else:
                    res = node.tools.call(name)
                print(f"-> {json.dumps(res, ensure_ascii=False, indent=2)}\n")

            elif cl == "flush":
                node.memory.flush()
                print("-> Flushed.\n")

            elif cl.startswith("connect ") or cl.startswith("подключить "):
                ip = cmd.split()[-1].strip()
                try:
                    secret = node.cognitive.data["node_secret"]
                    packet = {
                        "protocol": "SYMBIONT-ALPHA",
                        "node_id": node.node_id,
                        "node_secret": secret,
                        "identity": node.assigned_name,
                        "tcp_port": node.network.tcp_port,
                        "latest_hash": node.memory.memory_chain[-1]["hash"],
                        "chain_length": len(node.memory.memory_chain),
                        "timestamp": now(),
                    }
                    packet["signature"] = SymbiontSecurity.sign_packet(secret, packet)
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.sendto(json.dumps(packet, ensure_ascii=False).encode(), (ip, node.network.udp_port))
                    sock.close()
                    print(f"-> Handshake → {ip}\n")
                except Exception as e:
                    print(f"[!] {e}\n")

            elif cl.startswith("remember ") or cl.startswith("запомни "):
                fact = cmd.split(maxsplit=1)[1] if len(cmd.split()) > 1 else ""
                node.process_owner_input(f"Fact: {fact}")
                print(f"-> Block #{len(node.memory.memory_chain)-1}\n")

            elif any(p in cl for p in ("кто ты", "что ты", "память", "memory", "кто я", "что ты обо мне")):
                if cl in ("кто ты", "что ты", "что ты такое"):
                    print(f"\n-> [{node.assigned_name}] Symbiont ALPHA. "
                          f"{'PRIMARY' if node.devices.is_primary() else 'SECONDARY'}. "
                          f"node={node.node_id}\n")
                else:
                    if not node.require_primary():
                        continue
                    print("\n-> [Recall]")
                    print(node.memory.recall_identity())
                    print()

            elif cl in ("state", "состояние"):
                if not node.require_primary():
                    continue
                for k, v in node.cognitive.data["internal_state"].items():
                    bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
                    print(f"   {k.ljust(14)} [{bar}] {v:.2f}")
                print(f"-> Motivations: {', '.join(node.cognitive.data['motivations'])}\n")

            elif cl in ("status", "статус"):
                st = node.devices.status()
                print(f"-> {node.assigned_name} | node={node.node_id}")
                print(f"   device={st['this_device_id']} primary={st['primary_device_id']} "
                      f"role={'PRIMARY' if st['is_primary'] else 'SECONDARY'}")
                print(f"   peers={len(node.network.active_peers)} blocks={len(node.memory.memory_chain)}")
                print(f"   balance={node.economy.balance()} SYM\n")

            elif cl.startswith("decide ") or cl.startswith("решить "):
                if not node.require_primary():
                    continue
                payload = cmd.split(maxsplit=1)[1] if len(cmd.split()) > 1 else ""
                parts = payload.split("|")
                sit = parts[0].strip()
                opts = [o.strip() for o in parts[1:]] if len(parts) > 1 else ["принять", "отклонить", "анализировать"]
                res = node.cognitive.decide(sit, opts, use_tools=True)
                print(f"-> {res['decision']} | {res['reason']}\n")

            elif cl in ("audit", "аудит"):
                ok, msg = node.memory.verify_integrity()
                print(f"-> {'OK' if ok else 'FAIL'}: {msg}\n")

            elif cl.startswith("search ") or cl.startswith("поиск "):
                if not node.require_primary():
                    continue
                q = cmd.split(maxsplit=1)[1] if len(cmd.split()) > 1 else ""
                for b in node.memory.search_memory(q)[:8]:
                    print(f"   [#{b.get('index')}] {(b.get('payload') or '')[:80]}")
                print()

            elif cl == "quest" or cl.startswith("quest "):
                if not node.require_primary():
                    continue
                parts = cmd[5:].split("|") if len(cmd) > 5 else []
                title = parts[0].strip() if parts and parts[0].strip() else "Квест"
                reward = float(parts[1]) if len(parts) > 1 and parts[1].replace(".", "", 1).isdigit() else 5.0
                reqs = parts[2].strip() if len(parts) > 2 else "—"
                q = node.quests.create_quest(title, reward, reqs)
                print(f"-> Quest {q['quest_id']} reward={q['reward']} SYM\n")

            elif cl.startswith("complete ") or cl.startswith("выполнить "):
                if not node.require_primary():
                    continue
                qid = cmd.split()[-1]
                res = node.quests.execute_and_verify_quest(qid, f"Done by {node.assigned_name}")
                print(f"-> {qid} → {res['status']}\n")

            elif cl in ("peers", "пиры", "сеть"):
                for pid, p in node.network.active_peers.items():
                    print(f"   [{p['identity']}] {p['ip']} blocks={p['chain_length']}")
                print()

            else:
                node.process_owner_input(cmd)
                st = node.cognitive.data["internal_state"]
                print(
                    f"-> blocks={len(node.memory.memory_chain)} "
                    f"stress={st['stress']:.2f} balance={node.economy.balance()} SYM\n"
                )

        except (KeyboardInterrupt, EOFError):
            node.shutdown()
            print("\n[INFO] Interrupted.")
            break


if __name__ == "__main__":
    main()
