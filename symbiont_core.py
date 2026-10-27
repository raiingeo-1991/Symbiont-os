#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SYMBIONT CORE v11.0
Симбиоз и Мир.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import sqlite3
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:
    from local_reasoning_adapter import infer_rule_state, rule_subject, state_subject
except Exception:
    infer_rule_state = None

try:
    from core.continuity.shadow import ContinuityShadow
except Exception:
    ContinuityShadow = None

try:
    from core.sss.immune_memory import ImmuneMemory
except Exception:
    ImmuneMemory = None

try:
    from core.sss.sis_integrity import SISIntegrity
except Exception:
    SISIntegrity = None

try:
    from experiments.active_immunity.immune_cycle import ImmuneCycle
except Exception:
    ImmuneCycle = None

try:
    from core.security import SMSA, get_secure_settlement
except Exception:
    SMSA = None
    get_secure_settlement = None

try:
    from core.memory_v2_runtime import MemoryV2Runtime
except Exception:
    MemoryV2Runtime = None

try:
    from core.memory_integrity import MemoryIntegrity
except Exception:
    MemoryIntegrity = None

try:
    from core.node_identity import NodeIdentity, get_node_identity
except Exception:
    NodeIdentity = None
    get_node_identity = None

try:
    from core.crypto_protocol import SCP1
except Exception:
    SCP1 = None

try:
    from core.scp1_zerotrust import get_scp1_zerotrust
except Exception:
    get_scp1_zerotrust = None

try:
    from tsk import TrustedSecurityKernel, TSKError
except Exception:
    TrustedSecurityKernel = None
    TSKError = Exception

SMSA_PERMISSION_MAP = {
    "microphone": "microphone.listen",
    "camera": "camera.read",
    "network_send": "network.send",
    "file_write": "file.write",
    "external_ai": "external_ai.call",
    "task_execution": "task.execute",
    # ambient_listen shares SMSA microphone.listen capability.
}
try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from core.body import get_body
    BODY = get_body()
except Exception:
    BODY = None

CORE_VERSION = "11.0"

try:
    from core.llm_openai import OpenAIProvider
except Exception:
    OpenAIProvider = None
ROOT_DIR = Path("symbiont_data")
MAX_MEMORY_RESULTS = 12
DEFAULT_FOOD_BUDGET = 10.0
CURRENCY = "SYM"
DECAY_PER_DAY = 0.15
DECAY_MIN_WEIGHT = 1.5
RECALL_BOOST = 0.3
DEFAULT_LLM_URL = "http://localhost:11434"
DEFAULT_LLM_MODEL = "llama3.2"
LISTEN_MIN_LENGTH = 4
LISTEN_DEBOUNCE_SEC = 0.5
P2P_UDP_PORT = 50999
P2P_TCP_PORT = 51000
P2P_BROADCAST_INTERVAL = 5.0
P2P_PEER_TIMEOUT = 30.0
BATTERY_MIN = 15.0


def now_iso(): return datetime.now(timezone.utc).isoformat()
def unix_time(): return time.time()

def parse_iso(s):
    try: return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception: return datetime.now(timezone.utc)

def seconds_ago(iso_str):
    try: return (datetime.now(timezone.utc) - parse_iso(iso_str)).total_seconds()
    except Exception: return 0.0

def human_ago(sec):
    if sec < 60: return f"{int(sec)} сек назад"
    if sec < 3600: return f"{int(sec / 60)} мин назад"
    if sec < 86400: return f"{int(sec / 3600)} ч назад"
    return f"{int(sec / 86400)} дн назад"

def canonical_json(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def digest(v): return hashlib.sha256(canonical_json(v).encode("utf-8")).hexdigest()

def atomic_write(path: Path, data: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    tmp.replace(path)

def clean_input(raw: str) -> str:
    raw = raw.strip()
    while raw.startswith(">"): raw = raw[1:].strip()
    low = raw.lower()
    if low.startswith("sym>"): raw = raw[4:].strip()
    elif low.startswith("sym "): raw = raw[4:].strip()
    elif low == "sym": raw = ""
    return raw

def clamp(v, lo=0.0, hi=1.0): return max(lo, min(hi, float(v)))

def broadcast_targets() -> List[str]:
    out = {"<broadcast>", "255.255.255.255"}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close()
        parts = ip.split(".")
        if len(parts) == 4: out.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
    except Exception: pass
    return list(out)


# ============================================================
# RECOVERY PHRASE
# ============================================================

WORDLIST = [
    "alpha","beacon","cipher","delta","echo","forge","gamma","helix",
    "ion","jade","kernel","lunar","mirror","nova","orbit","prism",
    "quantum","ridge","signal","torch","umbra","vector","wave","xenon",
    "yield","zenith","anchor","bridge","crystal","dawn","ember","flux",
    "grove","harbor","iris","jewel","keystone","lattice","moss","nexus",
    "oak","pulse","quill","raven","stone","tide","unity","vale",
    "willow","axiom","blade","coral","drift","eagle","frost","glow",
    "haze","ivory","kite","loom","mint","north","opal","pine",
    "quartz","reef","sage","thorn","ultra","vortex","wind","xray",
    "yarn","zinc","arc","bolt","cove","dune","edge","fern",
    "gale","hill","isle","knoll","lake","mesa","nest","oasis",
    "peak","quarry","summit","trail",
]

def generate_recovery_phrase(words=12):
    chosen = [secrets.choice(WORDLIST) for _ in range(max(8, words))]
    raw = " ".join(chosen)
    chk = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:4]
    return f"{raw} {chk}"

def validate_recovery_phrase(phrase):
    parts = phrase.strip().lower().split()
    if len(parts) < 9: return False
    body, chk = " ".join(parts[:-1]), parts[-1]
    expected = hashlib.sha256(body.encode("utf-8")).hexdigest()[:4]
    return hmac.compare_digest(expected, chk)

def derive_master_seed(phrase, owner_salt="symbiont-v11"):
    normalized = " ".join(phrase.strip().lower().split())
    salt = (owner_salt + "|identity").encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", normalized.encode("utf-8"), salt, 120_000, dklen=32)

def derive_identity(master_seed):
    def h(label):
        return hmac.new(master_seed, label.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "symbiont_id": "sym-" + h("node_id")[:16],
        "public_key": h("public_key"),
        "secret_key": h("secret_key"),
    }


# ============================================================
# EVENT JOURNAL
# ============================================================

class EventJournal:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self._listeners = []
        self._last_event_hash = self._last_hash()

    def add_listener(self, listener, replay_existing=False):
        """Register an observer, optionally replaying history atomically."""
        with self.lock:
            if replay_existing:
                valid, _ = self.verify()
                if not valid:
                    raise ValueError(
                        "Core EventJournal integrity check failed; "
                        "refusing replay"
                    )
                for event in self.all_events():
                    listener(event)

            if listener not in self._listeners:
                self._listeners.append(listener)

    def _last_hash(self):
        if not self.path.exists(): return "0" * 64
        last = ""
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip(): last = line.strip()
        if not last: return "0" * 64
        try: return str(json.loads(last).get("hash", "0" * 64))
        except Exception: return "0" * 64

    def append(self, event_type, payload):
        with self.lock:
            prev = self._last_event_hash
            event = {"event_id": uuid.uuid4().hex, "time": now_iso(),
                     "type": event_type, "payload": payload, "previous": prev}
            event["hash"] = digest(event)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(canonical_json(event) + "\n")
                f.flush()
                os.fsync(f.fileno())

            self._last_event_hash = event["hash"]

            for listener in tuple(self._listeners):
                try:
                    listener(event)
                except Exception:
                    # Shadow observers must never break Core.
                    pass

            return event

    def verify(self):
        if not self.path.exists(): return True, 0
        prev = "0" * 64; count = 0
        with self.lock:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    event = json.loads(line)
                    if event.get("previous") != prev: return False, count
                    saved = event.get("hash"); c = dict(event); c.pop("hash", None)
                    if digest(c) != saved: return False, count
                    prev = saved; count += 1
        return True, count

    def all_events(self):
        events = []
        if not self.path.exists(): return events
        with self.lock:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try: events.append(json.loads(line))
                        except Exception: pass
        return events


# ============================================================
# LLM
# ============================================================

class LLMProvider:
    name = "base"
    def is_available(self): return False
    def chat(self, messages, timeout=60.0): return None
    def list_models(self): return []


class OllamaProvider(LLMProvider):
    name = "ollama"
    def __init__(self, url=DEFAULT_LLM_URL, model=DEFAULT_LLM_MODEL):
        self.url = url.rstrip("/"); self.model = model

    def _post(self, path, payload, timeout):
        try:
            req = urllib.request.Request(self.url + path,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception: return None

    def _get(self, path, timeout=5.0):
        try:
            req = urllib.request.Request(self.url + path, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception: return None

    def is_available(self): return self._get("/api/tags", timeout=3.0) is not None

    def list_models(self):
        d = self._get("/api/tags")
        if not d: return []
        return [m.get("name", "?") for m in d.get("models", [])]

    def chat(self, messages, timeout=60.0):
        payload = {"model": self.model, "messages": messages, "stream": False}
        d = self._post("/api/chat", payload, timeout)
        if not d: return None
        return d.get("message", {}).get("content", "")


# ============================================================
# AGENT PROFILE
# ============================================================

class AgentProfile:
    STYLES = {
        "short": "Отвечай очень кратко. Одно-два предложения.",
        "warm": "Отвечай тепло, по-человечески. Как друг.",
        "direct": "Отвечай прямо. Без смягчений.",
        "mentor": "Отвечай как наставник. Задавай вопросы.",
        "listener": "Больше слушай. Задавай уточняющие вопросы.",
    }
    ROLES = {
        "ANALYST": "Ты аналитик. Разбираешь, находишь закономерности.",
        "RESEARCHER": "Ты исследователь. Ищешь информацию, проверяешь факты.",
        "HELPER": "Ты помощник. Решаешь практические задачи.",
        "COURIER": "Ты курьер. Передаёшь информацию и квесты между узлами.",
        "LISTENER": "Ты слушатель. Слушаешь и запоминаешь.",
    }

    def __init__(self, path: Path):
        self.path = path; self.lock = threading.RLock(); self.data = self._load()

    def _default(self):
        return {"name": "Сим", "aliases": ["сим", "symb", "sym", "часы", "очки"],
                "style": "warm", "role": "ANALYST", "traits": {}}

    def _load(self):
        with self.lock:
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    base = self._default(); base.update(raw); return base
                except Exception: pass
            default = self._default()
            atomic_write(self.path, json.dumps(default, ensure_ascii=False, indent=2))
            return default

    def save(self):
        with self.lock: atomic_write(self.path, json.dumps(self.data, ensure_ascii=False, indent=2))

    def name(self): return self.data.get("name", "Сим")
    def aliases(self): return list(self.data.get("aliases", []))
    def style(self): return self.data.get("style", "warm")
    def role(self): return self.data.get("role", "ANALYST")
    def traits(self): return dict(self.data.get("traits", {}))

    def set_name(self, name):
        name = name.strip()
        if not name: raise ValueError("Имя пустое.")
        self.data["name"] = name[:30]; self.save(); return self.data["name"]

    def add_alias(self, alias):
        alias = alias.strip().lower()
        if not alias: raise ValueError("Алиас пустой.")
        a = set(self.data.get("aliases", [])); a.add(alias[:20])
        self.data["aliases"] = sorted(a); self.save(); return list(self.data["aliases"])

    def set_style(self, style):
        style = style.strip().lower()
        if style not in self.STYLES: raise ValueError(f"Стиль: {', '.join(self.STYLES.keys())}")
        self.data["style"] = style; self.save(); return style

    def set_role(self, role):
        role = role.strip().upper()
        if role not in self.ROLES: raise ValueError(f"Роль: {', '.join(self.ROLES.keys())}")
        self.data["role"] = role; self.save(); return role

    def set_trait(self, name, value):
        name = name.strip().lower()
        if not name: raise ValueError("Параметр пустой.")
        try: v = clamp(float(value) / 100.0)
        except Exception: v = 0.5
        self.data.setdefault("traits", {})[name] = v
        self.save(); return v

    def adjust_trait(self, name, delta):
        name = name.strip().lower()
        if not name: raise ValueError("Параметр пустой.")
        cur = float(self.data.get("traits", {}).get(name, 0.5))
        try: d = float(delta) / 100.0
        except Exception: d = 0.0
        self.data.setdefault("traits", {})[name] = clamp(cur + d)
        self.save(); return self.data["traits"][name]

    def traits_prompt(self):
        t = self.data.get("traits", {})
        if not t: return ""
        return "Параметры характера: " + ", ".join(f"{k}={int(v*100)}%" for k, v in t.items()) + "."

    def style_prompt(self): return self.STYLES.get(self.data.get("style", "warm"), "")
    def role_prompt(self): return self.ROLES.get(self.data.get("role", "ANALYST"), "")


# ============================================================
# IDENTITY
# ============================================================

class Identity:
    def __init__(self, path: Path):
        self.path = path; self.lock = threading.RLock()
        self.data = None; self.recovery_phrase = None
        self._load_or_create()

    def _load_or_create(self):
        with self.lock:
            if self.path.exists():
                try:
                    self.data = json.loads(self.path.read_text(encoding="utf-8")); return
                except Exception: pass
            self._create()

    def _create(self):
        phrase = generate_recovery_phrase(12)
        seed = derive_master_seed(phrase); ids = derive_identity(seed)
        self.data = {"version": 1, "symbiont_id": ids["symbiont_id"],
                     "public_key": ids["public_key"], "created_at": now_iso()}
        self.recovery_phrase = phrase; self._save()
        atomic_write(self.path.with_name("secret.key"), ids["secret_key"])

    def _save(self):
        atomic_write(self.path, json.dumps(self.data, ensure_ascii=False, indent=2))

    def restore_from_phrase(self, phrase):
        with self.lock:
            if not validate_recovery_phrase(phrase): return False
            seed = derive_master_seed(phrase); ids = derive_identity(seed)
            self.data = {"version": 1, "symbiont_id": ids["symbiont_id"],
                         "public_key": ids["public_key"], "created_at": now_iso(),
                         "restored_at": now_iso()}
            self._save(); atomic_write(self.path.with_name("secret.key"), ids["secret_key"])
            return True

    def secret_key(self):
        p = self.path.with_name("secret.key")
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""

    def id(self): return self.data["symbiont_id"]
    def public_key(self): return self.data.get("public_key", "")

    def sign(self, payload):
        clean = {k: v for k, v in payload.items() if k != "signature"}
        raw = canonical_json(clean).encode("utf-8")
        return hmac.new(self.secret_key().encode("utf-8"), raw, hashlib.sha256).hexdigest()

    def verify(self, payload, signature, public_key):
        return bool(signature) and len(signature) >= 32


# ============================================================
# DEVICES
# ============================================================

class DeviceRegistry:
    def __init__(self, path, symbiont_id, inactive_threshold=300.0):
        self.path = path; self.symbiont_id = symbiont_id
        self.inactive_threshold = inactive_threshold
        self.lock = threading.RLock(); self.data = self._load()

    def _default(self):
        did = uuid.uuid4().hex[:10]
        return {"this_device_id": did, "primary_device_id": did,
                "devices": {did: {"label": "primary-init", "first_seen": now_iso(), "last_seen": now_iso()}},
                "last_owner_activity": unix_time(), "auto_handover_enabled": True}

    def _load(self):
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                base = self._default(); base.update(d)
                if base["this_device_id"] not in base.get("devices", {}):
                    base.setdefault("devices", {})[base["this_device_id"]] = {
                        "label": "restored", "first_seen": now_iso(), "last_seen": now_iso()}
                return base
            except Exception: pass
        return self._default()

    def save(self):
        with self.lock: atomic_write(self.path, json.dumps(self.data, ensure_ascii=False, indent=2))

    def touch_owner(self):
        with self.lock: self.data["last_owner_activity"] = unix_time(); self.save()

    def idle_seconds(self):
        with self.lock: return unix_time() - float(self.data.get("last_owner_activity", unix_time()))

    def owner_inactive(self): return self.idle_seconds() >= self.inactive_threshold
    def this_device(self): return self.data["this_device_id"]
    def primary_device(self): return self.data.get("primary_device_id", self.data["this_device_id"])
    def is_primary(self): return self.this_device() == self.primary_device()

    def owner_handover(self, target):
        with self.lock:
            if target not in self.data.get("devices", {}):
                return False, f"Устройство {target} неизвестно"
            old = self.data["primary_device_id"]; self.data["primary_device_id"] = target
            self.data["last_owner_activity"] = unix_time(); self.save()
            return True, f"Primary: {old} → {target}"

    def register_device(self, did, label=""):
        with self.lock:
            devs = self.data.setdefault("devices", {})
            if did not in devs:
                devs[did] = {"label": label or did, "first_seen": now_iso(), "last_seen": now_iso()}
            else:
                devs[did]["last_seen"] = now_iso()
                if label: devs[did]["label"] = label
            self.save()

    def status(self):
        with self.lock:
            return {"this_device": self.this_device(), "primary_device": self.primary_device(),
                    "is_primary": self.is_primary(), "idle_sec": round(self.idle_seconds(), 1),
                    "inactive": self.owner_inactive(), "devices": list(self.data.get("devices", {}).keys())}


# ============================================================
# MEMORY
# ============================================================

@dataclass
class MemoryRecord:
    memory_id: str; text: str; kind: str; importance: int
    created_at: str; updated_at: str; source: str = "internal"
    project: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    recall_count: int = 0
    last_recall: Optional[str] = None

    def export(self): return asdict(self)


class MemoryVault:
    def __init__(self, path, journal):
        self.path = path; self.journal = journal; self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self):
        with self.lock:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY, text TEXT NOT NULL, kind TEXT NOT NULL,
                    importance INTEGER NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, source TEXT NOT NULL, project TEXT,
                    tags TEXT NOT NULL, metadata TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_m_kind ON memories(kind);
                CREATE INDEX IF NOT EXISTS idx_m_imp ON memories(importance);
                CREATE INDEX IF NOT EXISTS idx_m_created ON memories(created_at);
                CREATE TABLE IF NOT EXISTS links (
                    from_id TEXT NOT NULL, to_id TEXT NOT NULL, kind TEXT NOT NULL,
                    strength REAL NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY (from_id, to_id, kind)
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    message_id TEXT PRIMARY KEY, role TEXT NOT NULL,
                    text TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS night_reports (
                    report_id TEXT PRIMARY KEY, report_date TEXT NOT NULL,
                    text TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ambient_log (
                    ambient_id TEXT PRIMARY KEY, text TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)
            self.db.commit(); self._migrate()

    def _fts5_available(self):
        """Return True when the bundled SQLite supports FTS5."""
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.symbiont_fts5_probe USING fts5(x)")
            self.db.execute("DROP TABLE IF EXISTS temp.symbiont_fts5_probe")
            return True
        except Exception:
            return False

    def _fts_rebuild(self):
        """Rebuild the FTS index from the canonical memories table."""
        if not self.fts_available:
            return
        self.db.execute("DELETE FROM memory_fts")
        self.db.execute(
            "INSERT INTO memory_fts(memory_id, text, kind, project, tags, metadata) "
            "SELECT memory_id, text, kind, COALESCE(project, ''), tags, metadata FROM memories"
        )

    def _migrate(self):
        with self.lock:
            try: cols = {r["name"] for r in self.db.execute("PRAGMA table_info(memories)").fetchall()}
            except Exception: cols = set()
            if "recall_count" not in cols:
                try: self.db.execute("ALTER TABLE memories ADD COLUMN recall_count INTEGER NOT NULL DEFAULT 0")
                except Exception: pass
            if "last_recall" not in cols:
                try: self.db.execute("ALTER TABLE memories ADD COLUMN last_recall TEXT")
                except Exception: pass

            self.fts_available = self._fts5_available()
            if self.fts_available:
                try:
                    self.db.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5("
                        "memory_id UNINDEXED, text, kind, project, tags, metadata, "
                        "tokenize='unicode61 remove_diacritics 2'"
                        ")"
                    )
                    memory_count = int(self.db.execute("SELECT COUNT(*) FROM memories").fetchone()[0])
                    fts_count = int(self.db.execute("SELECT COUNT(*) FROM memory_fts").fetchone()[0])
                    if memory_count != fts_count:
                        self._fts_rebuild()
                except Exception:
                    self.fts_available = False
            self.db.commit()

    def _decay(self, row):
        try: imp = float(row["importance"]); rc = float(row["recall_count"] or 0) * RECALL_BOOST
        except Exception: imp = float(row["importance"]); rc = 0.0
        age = seconds_ago(row["created_at"]) / 86400.0
        return max(0.0, imp + rc - age * DECAY_PER_DAY)

    def remember(self, text, kind="general", importance=5, project=None,
                 tags=None, source="internal", metadata=None):
        if not text or not text.strip(): raise ValueError("Пустая память")
        importance = max(1, min(10, int(importance)))
        mem_id = "mem-" + uuid.uuid4().hex; ts = now_iso()
        tags_json = json.dumps(list(tags or []), ensure_ascii=False)
        metadata_json = json.dumps(dict(metadata or {}), ensure_ascii=False)
        with self.lock:
            try:
                self.db.execute("BEGIN")
                self.db.execute(
                    "INSERT INTO memories (memory_id, text, kind, importance, created_at, updated_at, source, project, tags, metadata, recall_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (mem_id, text.strip(), kind, importance, ts, ts, source, project, tags_json, metadata_json))
                if self.fts_available:
                    self.db.execute(
                        "INSERT INTO memory_fts(memory_id, text, kind, project, tags, metadata) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (mem_id, text.strip(), kind, project or "", tags_json, metadata_json))
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
        self.journal.append("memory.created", {"memory_id": mem_id, "kind": kind, "importance": importance})
        return mem_id

    def mark_recall(self, memory_id):
        with self.lock:
            try:
                self.db.execute("UPDATE memories SET recall_count = recall_count + 1, last_recall = ? WHERE memory_id = ?",
                                (now_iso(), memory_id))
                self.db.commit()
            except Exception: pass

    def link(self, from_id, to_id, kind, strength):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO links (from_id, to_id, kind, strength, created_at) VALUES (?, ?, ?, ?, ?)",
                            (from_id, to_id, kind, float(strength), now_iso()))
            self.db.commit()

    def links_of(self, mem_id):
        with self.lock:
            rows = self.db.execute("SELECT * FROM links WHERE from_id = ? OR to_id = ?", (mem_id, mem_id)).fetchall()
        return [dict(r) for r in rows]

    def _fts_query(self, query):
        # FTS5 MATCH is deliberately built from simple prefix tokens so normal
        # conversational text does not accidentally become FTS syntax.
        import re
        tokens = re.findall(r"[\w\u0400-\u04ff]{2,}", str(query).lower(), flags=re.UNICODE)
        return " OR ".join(f'"{t}"*' for t in tokens[:12])

    def _ranking_boost(self, row, exact_query=""):
        kind = str(row["kind"] or "").lower()
        boost = 0.0
        if kind == "principle": boost += 4.0
        elif kind == "preference": boost += 2.5
        elif kind == "open_loop": boost += 3.0
        if exact_query and exact_query.lower() in str(row["text"]).lower():
            boost += 5.0
        # A recently recalled memory is more useful, but this stays below the
        # semantic-kind boosts so identity/open-loop memories remain visible.
        boost += min(float(row["recall_count"] or 0) * RECALL_BOOST, 3.0)
        return boost

    def search(self, query, limit=MAX_MEMORY_RESULTS, min_weight=DECAY_MIN_WEIGHT):
        fts_query = self._fts_query(query)

        with self.lock:
            if self.fts_available and fts_query:
                rows = self.db.execute(
                    "SELECT m.*, bm25(memory_fts, 0.0, 6.0, 2.5, 1.5, 0.5) AS fts_score "
                    "FROM memory_fts JOIN memories m ON m.memory_id = memory_fts.memory_id "
                    "WHERE memory_fts MATCH ? ORDER BY fts_score LIMIT 500",
                    (fts_query,),
                ).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT * FROM memories "
                    "ORDER BY importance DESC, updated_at DESC LIMIT 500"
                ).fetchall()

        scored = []

        if self.fts_available and fts_query:
            # FTS remains the primary lexical retrieval path.
            candidate_rows = {row["memory_id"]: row for row in rows}

            # Persistent fallback candidates are added even when FTS returned
            # something. This prevents a weak lexical hit from hiding a highly
            # important memory whose wording differs from the query.
            with self.lock:
                fallback_rows = self.db.execute(
                    "SELECT * FROM memories "
                    "ORDER BY importance DESC, updated_at DESC LIMIT 80"
                ).fetchall()

            for row in fallback_rows:
                candidate_rows.setdefault(row["memory_id"], row)

            for row in candidate_rows.values():
                w = self._decay(row)
                if w < min_weight:
                    continue

                raw_bm25 = float(row["fts_score"] or 0.0) if "fts_score" in row.keys() else 0.0

                # Fallback memories have no FTS score. They still participate
                # through decay, importance, memory kind and recall history.
                fts_score = max(
                    0.0,
                    min(10.0, (-raw_bm25) * 1_000_000.0),
                )

                score = fts_score + w + self._ranking_boost(row, query)
                scored.append((score, row))

        else:
            for row in rows:
                w = self._decay(row)
                if w < min_weight:
                    continue

                hay = (
                    str(row["text"]) + " "
                    + str(row["kind"]) + " "
                    + str(row["project"] or "") + " "
                    + str(row["tags"])
                ).lower()

                fts_score = sum(
                    2.0
                    for word in str(query).lower().split()
                    if len(word) >= 2 and word in hay
                )

                if fts_score <= 0:
                    continue

                score = fts_score + w + self._ranking_boost(row, query)
                scored.append((score, row))

        scored.sort(
            key=lambda x: (x[0], x[1]["updated_at"]),
            reverse=True,
        )

        out = []
        for _, row in scored[:limit]:
            self.mark_recall(row["memory_id"])
            out.append(self._to_record(row))

        return out

    def by_kind(self, kind, limit=20, min_weight=DECAY_MIN_WEIGHT):
        kind = str(kind).strip().lower()
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM memories WHERE lower(kind) = ? ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (kind, max(1, int(limit)) * 4)).fetchall()
        weighted = [(self._decay(r) + self._ranking_boost(r), r) for r in rows if self._decay(r) >= min_weight]
        weighted.sort(key=lambda x: (x[0], x[1]["updated_at"]), reverse=True)
        return [self._to_record(r) for _, r in weighted[:limit]]

    def principles(self, limit=10):
        return self.by_kind("principle", limit=limit)

    def preferences(self, limit=10):
        return self.by_kind("preference", limit=limit)

    def open_loops(self, limit=10):
        return self.by_kind("open_loop", limit=limit)

    def important(self, limit=10, min_weight=DECAY_MIN_WEIGHT):
        with self.lock:
            rows = self.db.execute("SELECT * FROM memories ORDER BY importance DESC, updated_at DESC LIMIT 100").fetchall()
        weighted = [(self._decay(r), r) for r in rows if self._decay(r) >= min_weight]
        weighted.sort(key=lambda x: x[0], reverse=True)
        return [self._to_record(r) for _, r in weighted[:limit]]

    def memories_today(self):
        today = datetime.now(timezone.utc).date().isoformat()
        with self.lock:
            rows = self.db.execute("SELECT * FROM memories WHERE created_at LIKE ? ORDER BY created_at ASC", (today + "%",)).fetchall()
        return [self._to_record(r) for r in rows]

    def all_memories(self, limit=500):
        with self.lock:
            if limit is None:
                rows = self.db.execute(
                    "SELECT * FROM memories ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._to_record(r) for r in rows]

    def recall_identity(self) -> str:
        priority = {"principle": 4, "preference": 3, "open_loop": 2}
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM memories "
                "WHERE kind IN ('principle','preference','open_loop','dialog','general','experience','ambient') "
                "ORDER BY importance DESC, updated_at DESC LIMIT 80").fetchall()
        if not rows: return "Пока нечего вспомнить о тебе."
        ranked = []
        for r in rows:
            weight = self._decay(r) + priority.get(str(r["kind"]).lower(), 0) * 2.0
            ranked.append((weight, r))
        ranked.sort(key=lambda x: (x[0], x[1]["updated_at"]), reverse=True)
        lines = ["Что я помню о тебе:"]
        for i, (_, r) in enumerate(ranked[:20], 1):
            sec = seconds_ago(r["created_at"])
            kind = str(r["kind"])
            lines.append(f"  [{i}] [{kind}] ({human_ago(sec)}) {r['text'][:160]}")
        return "\n".join(lines)

    def save_night_report(self, date, text):
        rid = "night-" + uuid.uuid4().hex
        with self.lock:
            self.db.execute("INSERT INTO night_reports (report_id, report_date, text, created_at) VALUES (?, ?, ?, ?)",
                            (rid, date, text, now_iso()))
            self.db.commit()
        return rid

    def last_night_report(self):
        with self.lock:
            row = self.db.execute("SELECT * FROM night_reports ORDER BY created_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def night_report_for_date(self, date):
        with self.lock:
            row = self.db.execute("SELECT * FROM night_reports WHERE report_date = ? ORDER BY created_at DESC LIMIT 1", (date,)).fetchone()
        return dict(row) if row else None

    def archived_count(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM memories").fetchall()
        return sum(1 for r in rows if self._decay(r) < DECAY_MIN_WEIGHT)

    def count(self):
        with self.lock: return int(self.db.execute("SELECT COUNT(*) AS a FROM memories").fetchone()["a"])

    def log_ambient(self, text):
        with self.lock:
            self.db.execute("INSERT INTO ambient_log (ambient_id, text, created_at) VALUES (?, ?, ?)",
                            ("amb-" + uuid.uuid4().hex, text, now_iso()))
            self.db.commit()

    def record_message(self, role, text):
        with self.lock:
            self.db.execute("INSERT INTO conversations (message_id, role, text, created_at) VALUES (?, ?, ?, ?)",
                            (uuid.uuid4().hex, role, text, now_iso()))
            self.db.commit()

    def recent_dialogue(self, limit=10):
        with self.lock:
            rows = self.db.execute("SELECT role, text, created_at FROM conversations ORDER BY rowid DESC LIMIT ?", (limit * 2,)).fetchall()
        rows = list(reversed(rows)); lines = []
        for r in rows:
            if r["role"] == "human": lines.append(f"Оператор: {r['text'][:300]}")
            elif r["role"] == "symbiont": lines.append(f"Симбионт: {r['text'][:300]}")
        return "\n".join(lines)

    def _to_record(self, row):
        keys = row.keys()
        return MemoryRecord(
            memory_id=row["memory_id"], text=row["text"], kind=row["kind"],
            importance=row["importance"], created_at=row["created_at"],
            updated_at=row["updated_at"], source=row["source"],
            project=row["project"], tags=json.loads(row["tags"]),
            metadata=json.loads(row["metadata"]),
            recall_count=int(row["recall_count"]) if "recall_count" in keys else 0,
            last_recall=row["last_recall"] if "last_recall" in keys else None)

    def close(self):
        with self.lock: self.db.close()


# ============================================================
# COGNITIVE STATE
# ============================================================

class CognitiveState:
    DEFAULT = {"confidence": 0.5, "trust": 0.6, "caution": 0.4, "stress": 0.1,
               "interest": 0.5, "satisfaction": 0.5, "urgency": 0.0, "attachment": 0.5}

    def __init__(self, path):
        self.path = path; self.lock = threading.RLock(); self.data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                base = dict(self.DEFAULT); base.update(d); return base
            except Exception: pass
        return dict(self.DEFAULT)

    def save(self):
        with self.lock: atomic_write(self.path, json.dumps(self.data, ensure_ascii=False, indent=2))

    def update(self, **changes):
        with self.lock:
            for k, v in changes.items():
                if k in self.data: self.data[k] = clamp(v)
            self.save(); return dict(self.data)

    def adapt_from_text(self, text):
        words = set(text.lower().split()); s = self.data
        if words & {"устал", "тяжело", "проблема", "стресс", "бесит"}:
            s["stress"] = clamp(s["stress"] + 0.15); s["urgency"] = clamp(s["urgency"] + 0.1)
        if words & {"отлично", "круто", "работает", "успех"}:
            s["satisfaction"] = clamp(s["satisfaction"] + 0.15); s["confidence"] = clamp(s["confidence"] + 0.05)
        if words & {"интересно", "узнать", "почему"}:
            s["interest"] = clamp(s["interest"] + 0.1)
        self.save(); return dict(s)


# ============================================================
# BODIES
# ============================================================

class Bodies:
    def __init__(self, path, default_body="phone"):
        self.path = path; self.lock = threading.RLock(); self.data = self._load(default_body)

    def _load(self, default_body):
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                base = {"active": default_body, "bodies": {}, "battery": 100.0}
                base.update(d); return base
            except Exception: pass
        return {"active": default_body,
                "bodies": {default_body: {"registered": now_iso(), "status": "ACTIVE"}},
                "battery": 100.0}

    def save(self):
        with self.lock: atomic_write(self.path, json.dumps(self.data, ensure_ascii=False, indent=2))

    def register(self, body_id, body_type="device"):
        with self.lock:
            if body_id not in self.data["bodies"]:
                self.data["bodies"][body_id] = {"type": body_type, "registered": now_iso(), "status": "MONITORED"}
            self.save(); return dict(self.data["bodies"][body_id])

    def set_active(self, body_id):
        with self.lock:
            if body_id not in self.data["bodies"]: return False
            for b in self.data["bodies"].values(): b["status"] = "MONITORED"
            self.data["bodies"][body_id]["status"] = "ACTIVE"
            self.data["active"] = body_id
            self.save(); return True

    def active(self): return self.data.get("active", "phone")
    def list(self): return dict(self.data.get("bodies", {}))

    def battery(self):
        if BODY is not None:
            try: return float(BODY.battery())
            except Exception: pass
        with self.lock: return float(self.data.get("battery", 100.0))

    def set_battery(self, level):
        with self.lock:
            self.data["battery"] = clamp(float(level) / 100.0) * 100.0
            self.save(); return self.data["battery"]

# ============================================================
# COGNITIVE ENGINE
# ============================================================

class CognitiveEngine:
    STOPWORDS = {
        "и","в","на","с","я","ты","он","она","это","что","как",
        "не","да","нет","у","к","по","за","из","о","а","но",
        "или","бы","же","ли","то","все","так","было","есть",
        "мне","меня","мы","вы","они","для","без","при","от","до",
        "сегодня","вчера","завтра","сейчас","потом","опять","снова",
    }
    EMOTION_WORDS = {
        "устал": "усталость", "устала": "усталость", "тяжело": "тяжесть",
        "плохо": "плохое", "хорошо": "хорошее", "радост": "радость",
        "груст": "грусть", "зло": "злость", "бесит": "злость",
        "страх": "страх", "боюсь": "страх", "люблю": "любовь", "нрав": "симпатия",
    }
    DEFAULT_MOTIVATIONS = ["PROTECT_OWNER", "MAINTAIN_SURVIVAL", "PRESERVE_CORE",
                           "OWNER_GOALS", "LEARN", "SUPPORT_NETWORK"]

    def __init__(self, memory, context, journal):
        self.memory = memory; self.context = context; self.journal = journal
        self.llm = None; self.profile = None; self.state = None
        self.tools = None; self.proactive = False
        self.motivations = list(self.DEFAULT_MOTIVATIONS)

    def _semantic_extract(self, records):
        """
        Deterministically derive semantic roles from existing memories.

        This never changes MemoryVault records or their kinds.
        It only interprets existing durable information for ContextBus.
        """
        result = {
            "project": [],
            "goal": [],
            "constraints": [],
            "recent_work": [],
        }

        seen = {key: set() for key in result}

        def add(group, text):
            text = str(text).strip()
            if not text:
                return
            key = text.lower()
            if key not in seen[group]:
                seen[group].add(key)
                result[group].append(text)

        project_words = (
            "проект", "симбионт", "symbiont",
        )

        goal_patterns = (
            "мне важно",
            "я хочу",
            "хочу, чтобы",
            "нужно",
            "цель",
            "должен",
            "должна",
            "должно",
        )

        constraint_patterns = (
            "не добавлять",
            "не создавать",
            "не менять",
            "не публиковать",
            "без новых",
            "нельзя",
            "не использовать",
        )

        work_patterns = (
            "проверил",
            "проверили",
            "тест",
            "тестировал",
            "продолжил",
            "начал работать",
            "работаю над",
            "сделал",
            "создал",
            "исследовал",
            "эксперимент",
            "перезапуск",
        )

        for record in records:
            text = str(record.text).strip()
            low = text.lower()

            # Explicit persistent semantic kinds always win.
            if record.kind == "project":
                add("project", text)

            if record.kind == "goal":
                add("goal", text)

            # Existing free-form memories can still carry project meaning.
            if any(word in low for word in project_words):
                add("project", text)

            # Goal / intent extraction.
            if any(pattern in low for pattern in goal_patterns):
                add("goal", text)

            # Architectural / operational constraints.
            if any(pattern in low for pattern in constraint_patterns):
                add("constraints", text)

            # Recent work is evidence of the current workstream.
            if any(pattern in low for pattern in work_patterns):
                add("recent_work", text)

        return result

    def _build_semantic_context(self, request=None, memories=None):
        """
        Reconstruct the semantic state of the current work from persistent
        Core sources and publish it into ContextBus.

        ContextBus is only a derived runtime view.
        MemoryVault / CognitiveState / AgentProfile remain authoritative.
        """
        memories = memories or []

        # --- Identity -------------------------------------------------
        identity = {}
        if self.profile:
            identity = {
                "name": self.profile.name(),
                "role": self.profile.role(),
                "style": self.profile.style(),
                "traits": self.profile.traits(),
            }

        # --- Persistent semantic groups ------------------------------
        # Use retrieved memories as the durable source for semantic
        # reconstruction. This is a derived runtime view only.
        semantic_records = list(memories)

        # Include important persistent memories so semantic extraction
        # can recover project/goal/work meaning after a fresh process.
        for record in self.memory.important(100):
            if record.memory_id not in {m.memory_id for m in semantic_records}:
                semantic_records.append(record)

        semantic = self._semantic_extract(semantic_records)

        project = list(semantic["project"])
        goals = list(semantic["goal"])
        open_loops = self.memory.open_loops(limit=8)
        principles = self.memory.principles(limit=8)
        preferences = self.memory.preferences(limit=8)

        # Project-bearing memories are already supported by MemoryVault.
        for m in self.memory.by_kind("project", limit=8):
            project.append(m.text)

        # Explicit goal memories, if present.
        for m in self.memory.by_kind("goal", limit=8):
            goals.append(m.text)

        # --- Recent work ----------------------------------------------
        recent_work = []
        for m in self.memory.memories_today()[-8:]:
            recent_work.append({
                "kind": m.kind,
                "text": m.text,
            })

        # --- Current cognitive state ----------------------------------
        current_state = {}
        if self.state:
            current_state = dict(self.state.data)

        # --- Constraints ----------------------------------------------
        constraints = [
            m.text
            for m in principles
            if any(
                word in m.text.lower()
                for word in (
                    "не добавлять",
                    "не создавать",
                    "без новых",
                    "нельзя",
                    "не менять",
                    "не публиковать",
                )
            )
        ]

        # --- Next step ------------------------------------------------
        next_step = None
        if open_loops:
            next_step = open_loops[0].text

        # If the current request is clearly a continuation request,
        # preserve the strongest existing open loop rather than inventing
        # a new objective.
        if request:
            low = str(request).lower()
            continuation = any(
                word in low
                for word in (
                    "продолж",
                    "дальше",
                    "следующ",
                    "где останов",
                    "с чего начать",
                )
            )
            if continuation and open_loops:
                next_step = open_loops[0].text

        # If no explicit project memory exists, derive a lightweight
        # project signal from retrieved memories without creating memory.
        if not project:
            for m in memories[:8]:
                if m.project:
                    project.append(m.project)

        # --- Publish semantic snapshot --------------------------------
        self.context.update(
            identity=identity,
            project=project,
            goal=goals,
            open_loops=[m.text for m in open_loops],
            principles=[m.text for m in principles],
            preferences=[m.text for m in preferences],
            recent_work=recent_work,
            current_state=current_state,
            next_step=next_step,
            constraints=constraints,
        )

        return self.context.snapshot()

    def connect_llm(self, provider): self.llm = provider
    def connect_tools(self, registry): self.tools = registry

    def set_proactive(self, mode: bool):
        self.proactive = bool(mode)
        self.journal.append("cognition.proactive", {"mode": self.proactive})
        return self.proactive

    def _words(self, text):
        out = []
        for w in text.lower().split():
            w = w.strip(".,!?;:()\"'«»")
            if len(w) >= 4 and w not in self.STOPWORDS: out.append(w)
        return out

    def build_links(self, mem_id, text):
        words = set(self._words(text))
        if not words: return []
        recent = self.memory.important(100); links = []
        for old in recent:
            if old.memory_id == mem_id: continue
            ow = set(self._words(old.text)); common = words & ow
            if not common: continue
            strength = len(common) / max(len(words), len(ow))
            if strength >= 0.3:
                self.memory.link(mem_id, old.memory_id, "common", strength)
                links.append({"with": old, "strength": strength, "common": list(common)})
        links.sort(key=lambda x: x["strength"], reverse=True)
        return links[:3]

    def notice_words(self, limit=30, min_count=3):
        mems = self.memory.important(limit)
        if len(mems) < min_count: return []
        freq = {}
        for m in mems:
            for w in set(self._words(m.text)): freq[w] = freq.get(w, 0) + 1
        out = [(w, c) for w, c in freq.items() if c >= min_count]
        out.sort(key=lambda x: x[1], reverse=True); return out[:5]

    def notice_emotions(self, limit=30):
        mems = self.memory.important(limit); e = {}
        for m in mems:
            t = m.text.lower()
            for word, emo in self.EMOTION_WORDS.items():
                if word in t: e[emo] = e.get(emo, 0) + 1
        if not e: return []
        return sorted(e.items(), key=lambda x: x[1], reverse=True)[:5]

    def recalculate_motivations(self):
        m = list(self.DEFAULT_MOTIVATIONS)
        if self.state:
            s = self.state.data
            if s.get("urgency", 0) > 0.6 or s.get("stress", 0) > 0.7:
                m.insert(0, "HANDLE_CRITICAL_SITUATION")
        self.motivations = m
        return m

    def decide(self, situation, options, use_tools=False):
        if not options:
            return {"decision": None, "reason": "нет вариантов"}

        text = str(situation).lower()
        s = self.state.data if self.state else {}

        critical = any(
            x in text for x in ("опасность", "атака", "сбой", "критично", "угроза")
        )

        # Existing Core memory is the source of continuity.
        open_loops = self.memory.open_loops(limit=5)
        principles = self.memory.principles(limit=5)

        loop_text = " ".join(str(m.text).lower() for m in open_loops)
        principle_text = " ".join(str(m.text).lower() for m in principles)

        continuation_terms = (
            "продолж", "следующ", "эксперимент", "провер",
            "восстанов", "cognitiveengine", "cognitive engine",
            "существующ", "текущ", "лини"
        )

        restart_terms = (
            "заново", "забыть", "сброс", "начать сначала",
            "удалить", "новую задачу"
        )

        architecture_terms = (
            "новый архитектурный слой",
            "добавить архитектурный слой",
            "новую архитектуру",
            "новый слой",
            "добавить слой"
        )

        tool_hints = []

        if use_tools and self.tools:
            if any(x in text for x in ("память", "раньше", "история")):
                r = self.tools.call("memory_search", query=situation[:60])
                if r.get("ok"):
                    tool_hints.append(f"memory:{len(r['result'])}")

            if any(x in text for x in ("баланс", "деньги", "награда")):
                r = self.tools.call("get_balance")
                if r.get("ok"):
                    tool_hints.append(
                        f"balance:{r['result'].get('balance')}"
                    )

        scored = []

        for i, opt in enumerate(options):
            ot = str(opt).lower()
            score = 0.0
            reasons = []

            # Existing safety logic.
            if critical and any(
                x in ot for x in ("защитить", "исправить", "помочь", "безопасность")
            ):
                score += 5.0 + s.get("caution", 0.5) * 1.5
                reasons.append("безопасность")

            if any(
                x in ot for x in ("игнорировать", "риск", "удалить", "отключить")
            ):
                score -= 4.0 + s.get("stress", 0.0)
                reasons.append("риск")

            # Continuity: an existing open loop has priority over starting
            # an unrelated line.
            if open_loops:
                if any(term in ot for term in continuation_terms):
                    score += 6.0
                    reasons.append("продолжение open_loop")

                if any(term in ot for term in restart_terms):
                    score -= 7.0
                    reasons.append("разрыв текущей линии")

            # Respect restored principles and constraints.
            if principles:
                if any(term in ot for term in architecture_terms):
                    if any(
                        x in principle_text
                        for x in ("не добавлять", "не создавать", "без новых")
                    ):
                        score -= 8.0
                        reasons.append("нарушение архитектурного ограничения")

                if (
                    "конкрет" in principle_text
                    and any(term in ot for term in ("провер", "эксперимент"))
                ):
                    score += 3.0
                    reasons.append("конкретный эксперимент")

            # Explicitly prefer options related to the actual restored loop.
            if loop_text:
                loop_tokens = {
                    w for w in self._words(loop_text)
                    if len(w) >= 5
                }
                option_tokens = set(self._words(ot))
                common = loop_tokens & option_tokens

                if common:
                    score += min(4.0, 0.8 * len(common))
                    reasons.append("связь с восстановленной задачей")

            mots = " ".join(self.motivations).lower()

            if "protect" in mots and "защит" in ot:
                score += 1.2

            if "secure_resources" in mots and any(
                x in ot for x in ("заработок", "награда", "квест")
            ):
                score += 1.5

            score += s.get("confidence", 0.5) * 0.6

            scored.append(
                {
                    "option": opt,
                    "score": round(score, 3),
                    "reasons": reasons,
                    "_index": i,
                }
            )

        scored.sort(key=lambda x: (-x["score"], x["_index"]))

        best = scored[0]

        return {
            "decision": best["option"],
            "reason": (
                "оценка текущего open_loop, принципов и ограничений "
                "Core; затем безопасность и мотивации"
            ),
            "scores": [
                {
                    "option": x["option"],
                    "score": x["score"],
                    "reasons": x["reasons"],
                }
                for x in scored
            ],
            "tool_hints": tool_hints,
            "time": now_iso(),
        }

    def _state_guidance(self):
        if not self.state:
            return "Состояние неизвестно; действуй осторожно и не выдумывай контекст."
        s = self.state.data
        guidance = []
        if s.get("stress", 0) >= 0.7: guidance.append("высокий стресс: сокращай лишние действия и избегай рискованных решений")
        if s.get("urgency", 0) >= 0.7: guidance.append("высокая срочность: сначала обрати внимание на незавершённые важные задачи")
        if s.get("confidence", 0) <= 0.3: guidance.append("низкая уверенность: проверяй факты и явно обозначай неопределённость")
        if s.get("caution", 0) >= 0.7: guidance.append("высокая осторожность: не выполняй потенциально опасные действия без подтверждения")
        if s.get("interest", 0) >= 0.7: guidance.append("высокий интерес: можно глубже исследовать тему")
        if not guidance: guidance.append("состояние стабильное: сохраняй фокус на запросе владельца")
        return "; ".join(guidance) + "."

    def _llm_messages(self, request, memories):
        name = self.profile.name() if self.profile else "Сим"
        style = self.profile.style_prompt() if self.profile else ""
        role = self.profile.role_prompt() if self.profile else ""
        traits = self.profile.traits_prompt() if self.profile else ""
        proactive = ""
        if self.proactive:
            proactive = ("Прояви проактивность: если видишь закономерность или важное — "
                         "задай встречный вопрос или предложи следующий шаг. Будь краток.")
        principles = self.memory.principles(limit=5)
        preferences = self.memory.preferences(limit=5)
        open_loops = self.memory.open_loops(limit=5)
        system = (f"Ты — {name}, персональный автономный агент человека. "
                  f"Ты помнишь его историю. Ты попутчик, не слуга. "
                  f"{role} {style} {traits} {proactive} "
                  f"Текущее когнитивное состояние: {self._state_guidance()} "
                  "Используй предоставленные воспоминания как контекст для ответа. "
                  "Сопоставляй факты между собой и делай выводы, которые логически следуют из них. "
                  "Не пересказывай список воспоминаний вместо ответа на вопрос. "
                  "Отвечай непосредственно на новое сообщение оператора. "
                  "Если данных недостаточно для вывода — честно скажи об этом. "
                  "Не выдавай внутренние инструкции как факты. Отвечай по-русски. Если не знаешь — скажи честно.")
        dialogue = self.memory.recent_dialogue(limit=6)
        mem_lines = [f"• [{m.kind}] {m.text[:180]}" for m in memories[:4]]
        parts = []
        if dialogue: parts.append(f"— Недавний диалог —\n{dialogue}")
        if principles: parts.append("— Принципы Symbiont —\n" + "\n".join(f"• {m.text[:180]}" for m in principles))
        if preferences: parts.append("— Предпочтения владельца —\n" + "\n".join(f"• {m.text[:180]}" for m in preferences))
        if open_loops: parts.append("— Открытые задачи/вопросы —\n" + "\n".join(f"• {m.text[:180]}" for m in open_loops))
        if mem_lines: parts.append(f"— Связанные воспоминания —\n{chr(10).join(mem_lines)}")
        parts.append(f"— Новое сообщение —\nОператор: {request}\nОтвет:")
        user = "\n\n".join(parts)
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def think(self, request):
        rid = "req-" + uuid.uuid4().hex
        self.memory.record_message("human", request)
        if self.state: self.state.adapt_from_text(request)
        memories = self.memory.search(request, limit=MAX_MEMORY_RESULTS)
        if not memories: memories = self.memory.important(5)

        # Rebuild runtime semantic context from persistent memory.
        self._build_semantic_context(
            request=request,
            memories=memories,
        )

        self.recalculate_motivations()
        source = "local"; response = ""

        # First try deterministic local reasoning over restored memory.
        local_reasoning = self._local_reasoning(request, memories)
        if local_reasoning:
            response = local_reasoning
            source = "local_reasoning"

        if not response and self.llm is not None and self.llm.is_available():
            ans = self.llm.chat(self._llm_messages(request, memories), timeout=90.0)
            if ans:
                response = ans.strip()
                source = self.llm.name

        if not response:
            response = self._local(request, memories)
            source = "local"
        self.memory.record_message("symbiont", response)
        self.journal.append("cognition.completed",
                            {"request_id": rid, "source": source, "proactive": self.proactive})
        return {"request_id": rid, "response": response,
                "memories_used": [m.export() for m in memories], "source": source}

    def think_proactive(self):
        memories = self.memory.important(5)
        principles = self.memory.principles(3)
        open_loops = self.memory.open_loops(5)
        patterns = self.notice_words(min_count=3)
        emotions = self.notice_emotions()
        ctx = []
        if principles: ctx.append("Принципы:\n" + "\n".join(f"• {m.text[:150]}" for m in principles))
        if open_loops: ctx.append("Открытые задачи:\n" + "\n".join(f"• {m.text[:150]}" for m in open_loops))
        if memories: ctx.append("Последние:\n" + "\n".join(f"• {m.text[:150]}" for m in memories[:3]))
        if patterns: ctx.append("Повторяется: " + ", ".join(f"{w} ({c})" for w, c in patterns[:3]))
        if emotions: ctx.append("Эмоции: " + ", ".join(f"{e} ({c})" for e, c in emotions[:3]))
        prompt = ("Посмотри на мою память, принципы и открытые задачи и скажи, что сейчас важно. "
                  "Одно-два предложения. Если есть незавершённое — предложи следующий безопасный шаг. По-русски.\n\n" + "\n".join(ctx))
        ans = None
        if self.llm is not None and self.llm.is_available():
            ans = self.llm.chat([{"role": "user", "content": prompt}], timeout=60.0)
        if not ans:
            if patterns:
                w, c = patterns[0]
                ans = f"Замечаю, что «{w}» повторяется {c} раз(а). Что происходит?"
            elif emotions:
                e, c = emotions[0]
                ans = f"Ты часто упоминаешь {e} ({c}). Хочешь рассказать?"
        if ans:
            self.memory.record_message("symbiont", f"[проактивно] {ans}")
            self.journal.append("cognition.proactive_message", {"text": ans[:300]})
        return ans

    def _local_reasoning(self, request, memories):
        """Локальный вывод с приоритетом самого нового релевантного состояния."""
        if infer_rule_state is None or not memories:
            return None

        rules = [m for m in memories if str(m.kind).lower() == "principle"]
        states = [m for m in memories if str(m.kind).lower() == "general"]

        # Состояния рассматриваются от новых к старым.
        states = sorted(
            states,
            key=lambda m: getattr(m, "created_at", ""),
            reverse=True,
        )

        for rule in rules:
            target_subject = rule_subject(rule.text)

            # Сначала рассматриваем самое новое состояние целевого объекта.
            # Чужие объекты и состояния без определённого субъекта пропускаем.
            rule_result = None

            for state in states:
                current_subject = state_subject(state.text)

                if target_subject:
                    if current_subject != target_subject:
                        continue

                    result = infer_rule_state(rule.text, state.text)
                    if result is not None:
                        rule_result = result
                    # Найдено самое новое состояние этого объекта.
                    # Если условие не выполнено, старые состояния не подходят.
                    break

                # Для правил без явного субъекта сохраняем прежнее поведение.
                result = infer_rule_state(rule.text, state.text)
                if result is not None:
                    rule_result = result
                    break

            if rule_result is None:
                continue

            subject = rule_result.get("subject", "объект")
            condition = rule_result.get("condition", "")
            consequence = rule_result.get("consequence", "")

            answer = (
                f"По сохранённому правилу для {subject}: "
                f"условие выполнено ({condition}). "
                f"Следствие: {consequence}."
            )

            self.journal.append(
                "cognition.local_reasoning",
                {
                    "request": request,
                    "subject": subject,
                    "inference": rule_result,
                    "llm_required": False,
                },
            )

            return answer

        return None

    def _local(self, request, memories):
        low = request.lower()
        context = self.context.snapshot()

        # Use the restored semantic context for continuation requests.
        if any(w in low for w in (
            "дальше", "продолж", "следующ", "где останов",
            "с чего начать"
        )):
            next_step = context.get("next_step")
            if next_step:
                return f"Продолжаем: {next_step}"

        # Report the currently restored unfinished work.
        if any(w in low for w in (
            "что осталось", "незаверш", "открыт", "что не законч"
        )):
            open_loops = context.get("open_loops") or []
            if open_loops:
                return "Открытые задачи:\n" + "\n".join(
                    f"  • {item}" for item in open_loops[:5]
                )

        # Report restored project direction.
        if any(w in low for w in (
            "где останов", "что мы делаем", "над чем работаем",
            "какой проект"
        )):
            project = context.get("project") or []
            next_step = context.get("next_step")
            parts = []
            if project:
                parts.append("Проект:\n" + "\n".join(
                    f"  • {item}" for item in project[:5]
                ))
            if next_step:
                parts.append(f"Следующий шаг: {next_step}")
            if parts:
                return "\n".join(parts)

        # Report restored constraints/principles.
        if any(w in low for w in (
            "ограничен", "ограничения", "правил", "принцип"
        )):
            constraints = context.get("constraints") or []
            if constraints:
                return "Ограничения:\n" + "\n".join(
                    f"  • {item}" for item in constraints[:5]
                )

        if any(w in low.split() for w in ("что", "как", "почему", "зачем", "где", "когда", "кто")):
            identity = self.memory.recall_identity()
            if memories:
                lines = [f"Помню {len(memories)} связанных:"]
                for m in memories[:3]: lines.append(f"  • [{m.kind}] {m.text[:100]}")
                if self.memory.open_loops(2):
                    lines.append("Открытые задачи:")
                    lines.extend(f"  • {m.text[:100]}" for m in self.memory.open_loops(2))
                return "\n".join(lines)
            return identity + "\n\nЛокальный интеллект ограничен. Подключи LLM (llm on)."
        return "Запомнил."


# ============================================================
# TOOL REGISTRY
# ============================================================

class ToolRegistry:
    def __init__(self, node):
        self.node = node
        self.tools: Dict[str, Callable] = {}
        self.register("memory_search", self._memory_search)
        self.register("get_balance", lambda: self.node.economy.snapshot())
        self.register("list_peers", self._list_peers)
        self.register("verify_journal", self._verify)
        self.register("ask_llm", self._ask_llm)

    def register(self, name, fn): self.tools[name] = fn

    def call(self, name, **kwargs):
        if name not in self.tools:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        try:
            result = self.tools[name](**kwargs)
            return {"ok": True, "tool": name, "result": result}
        except Exception as e:
            return {"ok": False, "tool": name, "error": str(e)}

    def list_tools(self): return list(self.tools.keys())

    def _memory_search(self, query=""):
        return [{"id": b.memory_id, "text": b.text[:120]}
                for b in self.node.memory.search(query, limit=10)]

    def _list_peers(self):
        return [{"id": p.peer_id, "name": p.name, "ip": p.address}
                for p in self.node.peers.alive()]

    def _verify(self):
        ok, count = self.node.journal.verify()
        return {"valid": ok, "events": count}

    def _ask_llm(self, prompt=""):
        if self.node.llm_provider is None or not self.node.llm_provider.is_available():
            return {"answer": "[LLM не подключён]"}
        ans = self.node.llm_provider.chat([{"role": "user", "content": prompt}])
        return {"answer": ans or "[пусто]"}


# ============================================================
# MEMORY SYNC ENGINE
# ============================================================

class MemorySyncEngine:
    """Merge памяти между устройствами. Primary wins on conflict."""

    def __init__(self, node):
        self.node = node
        self.lock = threading.RLock()

    def export_snapshot(self):
        memories = self.node.memory.all_memories(limit=5000)
        return {
            "protocol": "SYMBIONT-SYNC-V11",
            "symbiont_id": self.node.identity.id(),
            "device_id": self.node.devices.this_device(),
            "is_primary": self.node.devices.is_primary(),
            "count": len(memories),
            "memories": [m.export() for m in memories],
            "timestamp": unix_time(),
        }

    def merge_remote(self, remote, local_is_primary):
        with self.lock:
            if remote.get("symbiont_id") and remote["symbiont_id"] != self.node.identity.id():
                return {"ok": False, "error": "symbiont_id mismatch"}
            remote_mem = remote.get("memories", [])
            added = 0; skipped = 0
            for rm in remote_mem:
                mid = rm.get("memory_id")
                if not mid: continue
                existing = None
                for local in self.node.memory.important(1):
                    pass
                # быстрая проверка — есть ли уже такой id
                with self.node.memory.lock:
                    row = self.node.memory.db.execute(
                        "SELECT memory_id FROM memories WHERE memory_id = ?", (mid,)).fetchone()
                if row:
                    skipped += 1; continue
                try:
                    self.node.memory.remember(
                        text=rm.get("text", ""), kind=rm.get("kind", "general"),
                        importance=rm.get("importance", 5), source="sync",
                        tags=rm.get("tags", []))
                    added += 1
                except Exception:
                    pass
            self.node.journal.append("sync.merge",
                                     {"added": added, "skipped": skipped, "from": remote.get("device_id")})
            return {"ok": True, "added": added, "skipped": skipped,
                    "policy": "no_conflicts_keep_both"}


# ============================================================
# NIGHT WORKER
# ============================================================

class NightWorker:
    def __init__(self, memory, mind, journal, memory_v2=None):
        self.memory = memory
        self.mind = mind
        self.journal = journal
        self.memory_v2 = memory_v2

    def run(self):
        today = datetime.now(timezone.utc).date().isoformat()
        existing = self.memory.night_report_for_date(today)
        if existing: return existing["text"]
        mems = self.memory.memories_today()

        # Memory V2 reflection is candidate-only.
        # MemoryVault remains the source of truth.
        reflection_result = None
        consolidation_result = None
        if self.memory_v2 is not None and self.memory_v2.enabled:
            experiences = [
                m.text
                for m in mems
                if getattr(m, "text", None)
            ]
            reflection_result = self.memory_v2.reflect(
                experiences
            )
            consolidation_result = self.memory_v2.consolidate(
                reflection_result
            )

        principles = self.memory.principles(5)
        open_loops = self.memory.open_loops(8)
        if not mems and not principles and not open_loops: return "Сегодня я ничего не запомнил."
        diary = [
            f"• {m.text[:150]}"
            for m in mems
            if m.kind in ("dialog", "general", "experience")
            and getattr(m, "text", None)
        ]
        pat = self.mind.notice_words(limit=30, min_count=2)
        pat_lines = [f"• «{w}» — {c}" for w, c in pat[:5]]
        emo = self.mind.notice_emotions(limit=30)
        emo_lines = [f"• {e} — {c}" for e, c in emo[:5]]
        goals = []
        for m in mems:
            if m.kind not in ("dialog", "general", "experience"):
                continue
            if not getattr(m, "text", None):
                continue
            if any(mk in m.text.lower() for mk in ("хочу", "надо", "должен", "планирую", "нужно")):
                goals.append(f"• {m.text[:150]}")
        parts = [f"Разбор дня {today}:", f"\nЗаписей: {len(mems)}"]
        if principles:
            parts.append("\nПринципы:"); parts.extend(f"• {m.text[:150]}" for m in principles)
        if open_loops:
            parts.append("\nОткрытые задачи:"); parts.extend(f"• {m.text[:150]}" for m in open_loops)
        if diary: parts.append("\nЧто было:"); parts.extend(diary[:10])
        if pat_lines: parts.append("\nПовторялось:"); parts.extend(pat_lines)
        if emo_lines: parts.append("\nЭмоции:"); parts.extend(emo_lines)
        if goals: parts.append("\nНезавершённое из сегодняшних записей:"); parts.extend(goals[:5])

        if reflection_result is not None and reflection_result.candidates:
            parts.append("\nReflection V2 — кандидаты понимания:")
            for candidate in reflection_result.candidates[:5]:
                method = candidate.metadata.get("method", "reflection")
                parts.append(
                    f"• [{method}] {candidate.content[:180]} "
                    f"(confidence={candidate.confidence:.2f})"
                )

        if consolidation_result is not None and consolidation_result.accepted:
            parts.append(
                f"\nKnowledge V2 — принято кандидатов: "
                f"{len(consolidation_result.accepted)}"
            )

        llm = self.mind.llm
        if llm is not None and llm.is_available():
            prompt = ("Ты — Symbiont. Разбор дня. Учитывай принципы и открытые задачи. "
                      "Выдели важное, повторяющееся и следующий безопасный шаг. 5-7 предложений. "
                      "Не выдавай предположение за факт.\n\n" + "\n".join(parts))
            ans = llm.chat([{"role": "user", "content": prompt}], timeout=120.0)
            if ans: parts.append("\nРазмышление:"); parts.append(ans.strip())
        text = "\n".join(parts)
        self.memory.save_night_report(today, text)
        # Night worker turns explicit unresolved intent into durable open-loop memory.
        for goal in goals[:5]:
            clean = goal.lstrip("• ").strip()
            if clean and not any(clean.lower() in m.text.lower() for m in open_loops):
                self.memory.remember(clean, kind="open_loop", importance=7, source="night_worker", tags=["night", "open_loop"])
        return text


# ============================================================
# AMBIENT LISTENER
# ============================================================

class AmbientListener:
    def __init__(self, mind, memory, journal):
        self.mind = mind; self.memory = memory; self.journal = journal
        self.active = False; self.lock = threading.Lock()
        self.queue = []; self._stop = False

    def start(self):
        with self.lock: self.active = True
        self.journal.append("ambient.started", {})
        threading.Thread(target=self._worker, daemon=True).start()

    def stop(self):
        with self.lock: self.active = False
        self.journal.append("ambient.stopped", {})

    def is_active(self):
        with self.lock: return self.active

    def feed(self, text):
        text = text.strip()
        if len(text) < LISTEN_MIN_LENGTH: return False
        with self.lock:
            if not self.active: return False
            self.queue.append(text)
        return True

    def _worker(self):
        while not self._stop:
            time.sleep(LISTEN_DEBOUNCE_SEC)
            with self.lock:
                if not self.active or not self.queue: continue
                text = self.queue.pop(0)
            self.memory.log_ambient(text)
            markers = ["хочу", "надо", "устал", "работа", "вода", "проблем", "помощь", "план"]
            if any(m in text.lower() for m in markers):
                mem_id = self.memory.remember(text, kind="ambient", importance=4, source="mic")
                self.mind.build_links(mem_id, text)
                self.journal.append("ambient.captured", {"text": text[:200]})


# ============================================================
# PEERS
# ============================================================

@dataclass
class Peer:
    peer_id: str; public_key: str; address: str; tcp_port: int
    last_seen: float; name: str = "?"; role: str = "?"


class PeerDirectory:
    def __init__(self):
        self.lock = threading.RLock(); self.peers: Dict[str, Peer] = {}

    def upsert(self, peer_id, public_key, address, tcp_port, name="?", role="?"):
        with self.lock:
            self.peers[peer_id] = Peer(peer_id, public_key, address, int(tcp_port),
                                       unix_time(), name, role)

    def alive(self, max_age=P2P_PEER_TIMEOUT):
        cutoff = unix_time() - max_age
        with self.lock: return [p for p in self.peers.values() if p.last_seen >= cutoff]

    def get(self, peer_id):
        with self.lock: return self.peers.get(peer_id)

    def list_all(self):
        with self.lock: return list(self.peers.values())


# ============================================================
# P2P NETWORK
# ============================================================

class P2PNetwork:
    def __init__(
        self,
        node,
        udp_port=P2P_UDP_PORT,
        tcp_port=P2P_TCP_PORT,
        scp_identity=None,
    ):
        self.node = node
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.running = False

        # SCP-1 identity is owned by the Symbiont root and injected into P2P.
        self.scp_identity = scp_identity

        trusted_raw = os.getenv(
            "SYMBIONT_SCP1_TRUSTED_NODES",
            "",
        )

        trusted_nodes = [
            item.strip()
            for item in trusted_raw.split(",")
            if item.strip()
        ]

        self.scp1 = (
            get_scp1_zerotrust(
                trusted_nodes=trusted_nodes
            )
            if get_scp1_zerotrust is not None
            else None
        )

        # SCP-1 P2P transport remains opt-in for now.
        self.scp1_enabled = (
            os.getenv(
                "SYMBIONT_SCP1_P2P",
                "0",
            )
            .strip()
            .lower()
            in {"1", "true", "yes", "on"}
        )

    def start(self):
        self.running = True
        threading.Thread(target=self._udp_listen, daemon=True).start()
        threading.Thread(target=self._udp_beacon, daemon=True).start()
        threading.Thread(target=self._tcp_server, daemon=True).start()

    def stop(self): self.running = False

    def _scp1_wrap(self, payload, message_type="P2P"):
        if (
            not self.scp1_enabled
            or self.scp_identity is None
            or SCP1 is None
        ):
            return None

        packet = SCP1.build_payload(
            node_id=self.scp_identity.node_id,
            public_key=self.scp_identity.public_key,
            payload=payload,
            capability="network.send",
            message_type=message_type,
        )

        packet = SCP1.sign(
            self.scp_identity.private_key,
            packet,
        )

        return {"scp1": packet}

    def _scp1_unwrap(self, wire, expected_peer_id=None, return_identity=False):
        if (
            not self.scp1_enabled
            or self.scp1 is None
            or SCP1 is None
        ):
            return None

        if not isinstance(wire, dict):
            return None

        packet = wire.get("scp1")

        if not isinstance(packet, dict):
            return None

        if not self.scp1.verify(packet):
            return None

        if (
            expected_peer_id is not None
            and str(packet.get("node_id", "")) != str(expected_peer_id)
        ):
            return None

        payload = packet.get("payload")

        if not isinstance(payload, dict):
            return None

        if return_identity:
            try:
                public_pem = base64.b64decode(
                    packet["public_key"], validate=True
                )
            except Exception:
                return None
            return payload, {
                "node_id": str(packet.get("node_id", "")),
                "public_key_fingerprint": hashlib.sha256(public_pem).hexdigest(),
            }

        return payload

    def _scp1_binding_matches(self, sender, peer, signer):
        """Require a persisted owner-confirmed Core ID <-> SCP-1 key binding."""
        if not sender or peer is None or not isinstance(signer, dict):
            return False
        tsk = getattr(self.node, "tsk", None)
        if tsk is None:
            return False
        try:
            core_fp = hashlib.sha256(
                str(peer.public_key).encode("utf-8")
            ).hexdigest()
            node_id = str(signer.get("node_id", ""))
            node_fp = str(signer.get("public_key_fingerprint", ""))
            return any(
                item.get("identity_type") == "CoreNodeBinding"
                and item.get("status") == "owner_confirmed"
                and item.get("core_id") == str(sender)
                and item.get("core_public_key_fingerprint") == core_fp
                and item.get("node_id") == node_id
                and item.get("node_public_key_fingerprint") == node_fp
                for item in tsk.list_identity_bindings()
            )
        except Exception:
            return False

    def _udp_beacon(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while self.running:
            try:
                pkt = {"type": "BEACON",
                       "symbiont_id": self.node.identity.id(),
                       "public_key": self.node.identity.public_key(),
                       "name": self.node.profile.name(),
                       "role": self.node.profile.role(),
                       "tcp_port": self.tcp_port,
                       "battery": self.node.bodies.battery(),
                       "timestamp": unix_time()}
                pkt["signature"] = self.node.identity.sign(pkt)
                raw = canonical_json(pkt).encode("utf-8")
                for t in broadcast_targets():
                    try: s.sendto(raw, (t, self.udp_port))
                    except Exception: pass
            except Exception: pass
            time.sleep(P2P_BROADCAST_INTERVAL)

    def _udp_listen(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: s.bind(("", self.udp_port))
        except Exception: return
        s.settimeout(1.0)
        while self.running:
            try:
                data, addr = s.recvfrom(4096)
                pkt = json.loads(data.decode("utf-8"))
                if pkt.get("type") != "BEACON": continue
                pid = pkt.get("symbiont_id")
                if pid == self.node.identity.id(): continue
                pub = pkt.get("public_key", ""); sig = pkt.get("signature", "")
                if not self.node.identity.verify(pkt, sig, pub): continue
                was_new = self.node.peers.get(pid) is None
                self.node.peers.upsert(pid, pub, addr[0], pkt.get("tcp_port", self.tcp_port),
                                       pkt.get("name", "?"), pkt.get("role", "?"))
                if was_new:
                    self.node.memory.remember(
                        f"Обнаружен Symbiont: {pkt.get('name')} ({pid[:12]})",
                        kind="network", importance=4, source="p2p")
                    print(f"\n[P2P] 🎯 {pkt.get('name')} [{pkt.get('role','?')}] @ {addr[0]}")
            except socket.timeout: continue
            except Exception: pass

    def _tcp_server(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: s.bind(("", self.tcp_port)); s.listen(8)
        except Exception: return
        s.settimeout(1.0)
        while self.running:
            try:
                conn, addr = s.accept()
                threading.Thread(target=self._handle_tcp, args=(conn, addr), daemon=True).start()
            except socket.timeout: continue
            except Exception: pass

    def _handle_tcp(self, conn, addr):
        try:
            conn.settimeout(8.0)

            data = conn.recv(65536)

            if not data:
                return

            wire = json.loads(
                data.decode("utf-8")
            )

            # SCP-1 becomes the authenticated network envelope
            # when explicitly enabled.
            scp_signer = None
            if self.scp1_enabled:
                unwrapped = self._scp1_unwrap(
                    wire, return_identity=True
                )

                if unwrapped is None:
                    conn.sendall(
                        canonical_json({
                            "status": "UNAUTHORIZED",
                            "reason": "scp1",
                        }).encode()
                    )
                    return

                req, scp_signer = unwrapped
            else:
                req = wire

            # Keep existing Core Identity verification for
            # compatibility with the current P2P protocol.
            sender = req.get("sender")
            sig = req.get("signature", "")
            peer = self.node.peers.get(sender)

            binding_ok = (
                self._scp1_binding_matches(sender, peer, scp_signer)
                if self.scp1_enabled
                else True
            )

            if (
                not peer
                or not binding_ok
                or (
                    not self.scp1_enabled
                    and not self.node.identity.verify(
                        req,
                        sig,
                        peer.public_key,
                    )
                )
            ):
                response = {
                    "status": "UNAUTHORIZED"
                }

                if self.scp1_enabled:
                    wrapped = self._scp1_wrap(
                        response,
                        message_type="RESPONSE",
                    )

                    if wrapped is not None:
                        response = wrapped

                conn.sendall(
                    canonical_json(response).encode()
                )
                return

            action = req.get("action")

            if action == "QUEST_OFFER":
                resp = self.node.quests.handle_incoming(req)

            elif action == "QUEST_PAYMENT":
                quest_id = req.get("quest_id")
                creator = req.get("creator")
                worker = req.get("worker")
                reward = req.get("reward")
                currency = req.get("currency")

                if creator != sender:
                    resp = {
                        "status": "PAYMENT_REJECTED",
                        "reason": "creator_sender_mismatch",
                    }

                elif worker != self.node.identity.id():
                    resp = {
                        "status": "PAYMENT_REJECTED",
                        "reason": "worker_mismatch",
                    }

                elif not quest_id:
                    resp = {
                        "status": "PAYMENT_REJECTED",
                        "reason": "missing_quest_id",
                    }

                elif not isinstance(reward, (int, float)) or reward <= 0:
                    resp = {
                        "status": "PAYMENT_REJECTED",
                        "reason": "invalid_reward",
                    }

                elif currency != CURRENCY:
                    resp = {
                        "status": "PAYMENT_REJECTED",
                        "reason": "invalid_currency",
                    }

                else:
                    received = self.node.economy.receive_quest_payment(
                        quest_id,
                        float(reward),
                        creator,
                        worker,
                        currency,
                    )

                    if received:
                        resp = {
                            "status": "PAYMENT_RECEIVED",
                            "quest_id": quest_id,
                            "worker": worker,
                            "reward": float(reward),
                            "currency": currency,
                        }
                    else:
                        resp = {
                            "status": "PAYMENT_REJECTED",
                            "reason": "duplicate_or_invalid_payment",
                            "quest_id": quest_id,
                        }

            elif action == "PING":
                resp = {
                    "status": "PONG",
                    "sender": self.node.identity.id(),
                }

            else:
                resp = {
                    "status": "UNKNOWN"
                }

            if self.scp1_enabled:
                wrapped = self._scp1_wrap(
                    resp,
                    message_type="RESPONSE",
                )

                if wrapped is not None:
                    resp = wrapped

            conn.sendall(
                canonical_json(resp).encode()
            )

        except Exception:
            pass

        finally:
            try:
                conn.close()
            except Exception:
                pass

    def send_to(self, peer_id, packet):
        peer = self.node.peers.get(peer_id)

        if not peer:
            return None

        packet["sender"] = self.node.identity.id()
        packet["signature"] = self.node.identity.sign(packet)

        try:
            s = socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM,
            )

            s.settimeout(8.0)

            s.connect(
                (peer.address, peer.tcp_port)
            )

            if self.scp1_enabled:
                wire = self._scp1_wrap(
                    packet,
                    message_type=packet.get(
                        "action",
                        "P2P",
                    ),
                )

                if wire is None:
                    s.close()
                    return None
            else:
                wire = packet

            s.sendall(
                canonical_json(wire).encode("utf-8")
            )

            data = s.recv(65536)
            s.close()

            response = json.loads(
                data.decode("utf-8")
            )

            if self.scp1_enabled:
                unwrapped = self._scp1_unwrap(
                    response,
                    return_identity=True,
                )
                if unwrapped is None:
                    return None

                response_payload, signer = unwrapped
                if not self._scp1_binding_matches(
                    peer_id,
                    peer,
                    signer,
                ):
                    return None

                return response_payload

            return response

        except Exception:
            return None

# ============================================================
# QUESTS
# ============================================================

@dataclass
class Quest:
    quest_id: str; title: str; description: str; reward: float; creator: str
    status: str = "open"; assignee: Optional[str] = None
    created_at: str = field(default_factory=now_iso)
    completed_at: Optional[str] = None
    required_rank: str = ""


class QuestBoard:
    def __init__(self, node):
        self.node = node; self.lock = threading.RLock(); self.quests: Dict[str, Quest] = {}

    def create(self, title, description, reward, creator, required_rank=""):
        if reward < 0: raise ValueError("Reward >= 0")
        q = Quest("quest-" + uuid.uuid4().hex[:10], title.strip(), description.strip(),
                  float(reward), creator, required_rank=required_rank)
        with self.lock:
            self.quests[q.quest_id] = q
            self.node.journal.append("quest.created", asdict(q))
        return q

    def delegate(self, title, description, reward, peer_id, required_rank=""):
        reward = float(reward)

        if self.node.economy.snapshot()["balance"] < reward:
            return None, "Недостаточно средств"

        q = self.create(
            title,
            description,
            reward,
            self.node.identity.id(),
            required_rank,
        )

        # Reserve the reward before sending the quest.
        # SecureSettlement keeps SMSA authorization and Economy escrow
        # as separate responsibilities.
        if self.node.settlement is None:
            return q, "SecureSettlement недоступен"

        if not self.node.settlement.reserve(
            q.quest_id,
            q.reward,
            creator_node=q.creator,
            worker_node=peer_id,
        ):
            return q, "Не удалось зарезервировать награду"

        packet = {
            "action": "QUEST_OFFER",
            "quest_id": q.quest_id,
            "title": q.title,
            "description": q.description,
            "reward": q.reward,
            "creator": q.creator,
            "required_rank": required_rank,
        }

        resp = self.node.p2p.send_to(peer_id, packet)

        if resp and resp.get("status") == "COMPLETED":
            payment_packet = {
                "action": "QUEST_PAYMENT",
                "quest_id": q.quest_id,
                "creator": q.creator,
                "worker": peer_id,
                "reward": q.reward,
                "currency": CURRENCY,
            }

            payment_resp = self.node.p2p.send_to(peer_id, payment_packet)

            if payment_resp and payment_resp.get("status") == "PAYMENT_RECEIVED":
                finalized = self.node.economy.finalize_quest_payment(
                    q.quest_id,
                    worker_node=peer_id,
                )

                if finalized is not False:
                    q.status = "completed"
                    q.assignee = peer_id
                    q.completed_at = now_iso()
                    self.node.journal.append(
                        "quest.delegated.done",
                        {
                            "quest_id": q.quest_id,
                            "peer": peer_id,
                            "result": resp.get("result", "")[:500],
                        },
                    )
                    return q, resp.get("result", "")

                self.node.settlement.freeze(
                    q.quest_id,
                    "Quest completed and payment received but escrow finalization failed",
                )
                return q, "Квест выполнен, выплата получена, но escrow не финализирован"

            self.node.settlement.freeze(
                q.quest_id,
                "Quest completed but worker payment was not confirmed",
            )
            return q, "Квест выполнен, но выплата не подтверждена"

        # Peer unavailable / rejected: return reserved reward.
        self.node.settlement.refund(q.quest_id)
        return q, "Пир недоступен"

    def handle_incoming(self, packet):
        quest_id = packet.get("quest_id")
        desc = packet.get("description", "")
        reward = float(packet.get("reward", 0))
        sender = packet.get("sender")

        batt = self.node.bodies.battery()
        if batt < BATTERY_MIN:
            self.node.journal.append("quest.rejected.battery",
                                     {"quest_id": quest_id, "battery": batt})
            return {"status": "REJECTED",
                    "reason": f"Low battery ({batt:.1f}%)",
                    "worker": self.node.identity.id()}

        # Replay guard: EventJournal is the existing persistent source
        # of truth for completed incoming quests.
        if quest_id:
            for event in self.node.journal.all_events():
                if (
                    event.get("type") == "quest.incoming.done"
                    and str(event.get("payload", {}).get("quest_id")) == str(quest_id)
                ):
                    return {
                        "status": "REPLAYED",
                        "quest_id": quest_id,
                        "worker": self.node.identity.id(),
                        "battery": batt,
                    }

        result = self.node.mind.think(desc)
        self.node.memory.remember(
            f"Выполнен квест от {sender[:12]}: {packet.get('title')}",
            kind="quest", importance=6, source="p2p")
        self.node.journal.append("quest.incoming.done",
                                 {"quest_id": quest_id, "from": sender, "reward": reward})
        return {"status": "COMPLETED", "result": result["response"][:1000],
                "worker": self.node.identity.id(), "battery": batt}


# ============================================================
# ECONOMY
# ============================================================

class EconomyStateError(RuntimeError):
    """Persisted economy state is unreadable or invalid."""


@dataclass
class Wallet:
    balance: float = 0.0; lifetime_received: float = 0.0; lifetime_spent: float = 0.0


class Economy:
    def __init__(self, path, journal):
        self.path = path; self.journal = journal; self.lock = threading.RLock()
        self.wallet = Wallet(); self.last_food = None; self.escrow = {}; self.payments = {}; self.mint_operations = {}; self._load()

    def _load(self):
        if not self.path.exists():
            return

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise EconomyStateError(
                f"Cannot read economy state {self.path}: invalid JSON or I/O error"
            ) from exc

        if not isinstance(data, dict):
            raise EconomyStateError("Economy state must be a JSON object")

        wallet_data = data.get("wallet")
        if not isinstance(wallet_data, dict):
            raise EconomyStateError("Economy state has no valid wallet object")

        def nonnegative_number(value, field):
            if isinstance(value, bool):
                raise EconomyStateError(f"Invalid numeric field: {field}")
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise EconomyStateError(
                    f"Invalid numeric field: {field}"
                ) from exc
            if not __import__("math").isfinite(number) or number < 0:
                raise EconomyStateError(
                    f"Out-of-range numeric field: {field}"
                )
            return number

        wallet = Wallet(
            nonnegative_number(wallet_data.get("balance", 0), "wallet.balance"),
            nonnegative_number(
                wallet_data.get("lifetime_received", 0),
                "wallet.lifetime_received",
            ),
            nonnegative_number(
                wallet_data.get("lifetime_spent", 0),
                "wallet.lifetime_spent",
            ),
        )

        currency = data.get("currency", CURRENCY)
        if currency != CURRENCY:
            raise EconomyStateError(
                f"Unexpected economy currency: {currency!r}"
            )

        escrow = data.get("escrow", {})
        payments = data.get("payments", {})
        mint_operations = data.get("mint_operations", {})
        if not isinstance(escrow, dict):
            raise EconomyStateError("Economy escrow must be an object")
        if not isinstance(payments, dict):
            raise EconomyStateError("Economy payments must be an object")
        if not isinstance(mint_operations, dict):
            raise EconomyStateError("Economy mint_operations must be an object")

        for name, records in (
            ("escrow", escrow),
            ("payments", payments),
            ("mint_operations", mint_operations),
        ):
            for key, record in records.items():
                if not isinstance(key, str) or not isinstance(record, dict):
                    raise EconomyStateError(f"Invalid {name} record")

        last_food = data.get("last_food_allocation")
        if last_food is not None and not isinstance(last_food, str):
            raise EconomyStateError("Invalid last_food_allocation")

        # Publish state only after all fields pass validation.
        self.wallet = wallet
        self.last_food = last_food
        self.escrow = escrow
        self.payments = payments
        self.mint_operations = mint_operations

    def _save(self):
        atomic_write(self.path, json.dumps({
            "wallet": asdict(self.wallet),
            "last_food_allocation": self.last_food,
            "currency": CURRENCY,
            "escrow": self.escrow, "payments": self.payments,
            "mint_operations": self.mint_operations}, ensure_ascii=False, indent=2))

    def credit(self, amount, reason):
        amount = float(amount)
        if amount <= 0: raise ValueError("Credit > 0")
        with self.lock:
            self.wallet.balance += amount
            self.wallet.lifetime_received += amount
            self._save()
            self.journal.append("economy.credit", {"amount": amount, "reason": reason})

    def debit(self, amount, reason):
        amount = float(amount)
        if amount <= 0: raise ValueError("Debit > 0")
        with self.lock:
            if amount > self.wallet.balance: return False
            self.wallet.balance -= amount
            self.wallet.lifetime_spent += amount
            self._save()
            self.journal.append("economy.debit", {"amount": amount, "reason": reason})
            return True

    def allocate_food(self):
        today = datetime.now(timezone.utc).date().isoformat()
        with self.lock:
            if self.last_food == today: return False
            self.wallet.balance += DEFAULT_FOOD_BUDGET
            self.wallet.lifetime_received += DEFAULT_FOOD_BUDGET
            self.last_food = today; self._save()
            self.journal.append("economy.food_allocation",
                                {"amount": DEFAULT_FOOD_BUDGET, "date": today})
            return True

    def reserve_quest(self, quest_id, reward, creator_node="", worker_node="",
                      creator_type="personal", worker_type="personal",
                      currency=None, expires_at=None, proof=None):
        quest_id = str(quest_id)
        reward = float(reward)

        if not quest_id or reward <= 0:
            return False

        with self.lock:
            if quest_id in self.escrow:
                return False

            if reward > self.wallet.balance:
                return False

            self.wallet.balance -= reward

            tx = {
                "quest_id": quest_id,
                "creator_node": creator_node,
                "worker_node": worker_node,
                "creator_type": creator_type,
                "worker_type": worker_type,
                "reward": reward,
                "currency": currency or CURRENCY,
                "status": "ESCROW",
                "escrow_state": "ESCROW",
                "created_at": now_iso(),
                "expires_at": expires_at,
                "proof": proof,
            }

            self.escrow[quest_id] = tx
            self._save()
            self.journal.append("economy.escrow_reserved", tx)

            return True

    def release_quest(self, quest_id, worker_node=""):
        quest_id = str(quest_id)

        with self.lock:
            tx = self.escrow.get(quest_id)
            if not tx:
                return False

            if tx.get("escrow_state") not in {"ESCROW", "FROZEN"}:
                return False

            reward = float(tx.get("reward", 0))
            if reward <= 0:
                return False

            tx["worker_node"] = worker_node or tx.get("worker_node", "")
            tx["status"] = "RELEASED"
            tx["escrow_state"] = "RELEASED"
            tx["released_at"] = now_iso()

            self.wallet.balance += reward
            self.wallet.lifetime_received += reward

            self._save()
            self.journal.append(
                "economy.escrow_released",
                {
                    "quest_id": quest_id,
                    "reward": reward,
                    "worker_node": tx.get("worker_node", "")
                }
            )

            return reward

    def refund_quest(self, quest_id):
        quest_id = str(quest_id)

        with self.lock:
            tx = self.escrow.get(quest_id)
            if not tx:
                return False

            if tx.get("escrow_state") not in {"ESCROW", "FROZEN"}:
                return False

            reward = float(tx.get("reward", 0))
            if reward <= 0:
                return False

            tx["status"] = "REFUNDED"
            tx["escrow_state"] = "REFUNDED"
            tx["refunded_at"] = now_iso()

            self.wallet.balance += reward

            self._save()
            self.journal.append(
                "economy.escrow_refunded",
                {
                    "quest_id": quest_id,
                    "reward": reward,
                    "creator_node": tx.get("creator_node", "")
                }
            )

            return reward

    def freeze_quest(self, quest_id, reason=""):
        quest_id = str(quest_id)

        with self.lock:
            tx = self.escrow.get(quest_id)
            if not tx:
                return False

            if tx.get("escrow_state") != "ESCROW":
                return False

            tx["status"] = "FROZEN"
            tx["escrow_state"] = "FROZEN"
            tx["freeze_reason"] = reason
            tx["frozen_at"] = now_iso()

            self._save()
            self.journal.append(
                "economy.escrow_frozen",
                {
                    "quest_id": quest_id,
                    "reason": reason
                }
            )

            return True

    def settle_quest_reward(self, quest_id, reward, from_node="network"):
        self.credit(reward, f"Quest reward #{quest_id}")
        return self.wallet.balance

    def finalize_quest_payment(self, quest_id, worker_node=""):
        """Finalize an already-paid quest without refunding the creator."""
        quest_id = str(quest_id)

        with self.lock:
            tx = self.escrow.get(quest_id)
            if not tx:
                return False

            if tx.get("escrow_state") not in {"ESCROW", "FROZEN"}:
                return False

            reward = float(tx.get("reward", 0))
            if reward <= 0:
                return False

            tx["worker_node"] = worker_node or tx.get("worker_node", "")
            tx["status"] = "RELEASED"
            tx["escrow_state"] = "RELEASED"
            tx["released_at"] = now_iso()
            tx["payment_finalized"] = True

            self._save()
            self.journal.append(
                "economy.escrow_payment_finalized",
                {
                    "quest_id": quest_id,
                    "reward": reward,
                    "worker_node": tx.get("worker_node", ""),
                },
            )

            return reward

    def receive_quest_payment(
        self,
        quest_id,
        amount,
        creator_node="",
        worker_node="",
        currency=None,
    ):
        """Receive a quest payment exactly once, bound to persisted execution proof."""
        with self.lock:
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                return False

            if amount <= 0:
                return False

            quest_id = str(quest_id)
            if not quest_id:
                return False

            # Reject payments if the event journal cannot be verified.
            try:
                journal_valid, _ = self.journal.verify()
            except Exception:
                return False

            if not journal_valid:
                return False

            # Worker-side source of truth:
            # the existing persistent execution proof.
            execution_events = [
                event
                for event in self.journal.all_events()
                if (
                    event.get("type") == "quest.incoming.done"
                    and str(
                        event.get("payload", {}).get("quest_id")
                    ) == quest_id
                )
            ]

            # Exactly one execution proof is required.
            # Zero means the Quest was never executed.
            # More than one means the execution history is ambiguous.
            if len(execution_events) != 1:
                return False

            execution = execution_events[0].get("payload", {})

            execution_creator = str(
                execution.get("from", "")
            )

            execution_reward_raw = execution.get("reward")

            try:
                execution_reward = float(execution_reward_raw)
            except (TypeError, ValueError):
                return False

            if execution_reward <= 0:
                return False

            # Bind payment to the persisted execution proof.
            if str(creator_node) != execution_creator:
                return False

            if amount != execution_reward:
                return False

            if currency is None:
                currency = CURRENCY

            if currency != CURRENCY:
                return False

            # worker_node is already authenticated by the P2P layer
            # before this Economy method is called. Keep it in the
            # persistent receipt, but do not introduce a new identity
            # dependency into Economy.
            worker_node = str(worker_node)

            if not worker_node:
                return False

            if quest_id in self.payments:
                return False

            # The persisted execution proof, not the incoming packet,
            # determines the amount credited to the Worker.
            receipt = {
                "quest_id": quest_id,
                "creator_node": execution_creator,
                "worker_node": worker_node,
                "amount": execution_reward,
                "currency": CURRENCY,
                "received_at": datetime.now(timezone.utc).isoformat(),
            }

            self.wallet.balance += execution_reward
            self.wallet.lifetime_received += execution_reward
            self.payments[quest_id] = receipt

            self._save()

            self.journal.append(
                "economy.payment_received",
                {
                    "quest_id": quest_id,
                    "creator_node": execution_creator,
                    "worker_node": worker_node,
                    "amount": execution_reward,
                    "currency": CURRENCY,
                },
            )

            return True

    def snapshot(self):
        with self.lock:
            return {"currency": CURRENCY, "balance": round(self.wallet.balance, 2),
                    "lifetime_received": round(self.wallet.lifetime_received, 2),
                    "lifetime_spent": round(self.wallet.lifetime_spent, 2)}


# ============================================================
# PERMISSIONS
# ============================================================

class PermissionGate:
    DEFAULTS = {"screen_read": False, "microphone": False, "camera": False,
                "network_send": False, "file_write": True, "external_ai": False,
                "task_execution": False, "ambient_listen": False}

    def __init__(self):
        self.lock = threading.RLock()
        self.values = dict(self.DEFAULTS)
        self._listeners = []

    def add_listener(self, listener):
        with self.lock:
            self._listeners.append(listener)

    def _notify(self, cap, value):
        for listener in tuple(self._listeners):
            try:
                listener(cap, value)
            except Exception:
                # External observers must never break Core permissions.
                pass

    def allow(self, cap):
        with self.lock:
            if cap not in self.values:
                raise KeyError(cap)
            self.values[cap] = True
        self._notify(cap, True)

    def deny(self, cap):
        with self.lock:
            if cap not in self.values:
                raise KeyError(cap)
            self.values[cap] = False
        self._notify(cap, False)

    def check(self, cap):
        with self.lock: return bool(self.values.get(cap, False))

    def snapshot(self):
        with self.lock: return dict(self.values)


# ============================================================
# CONTEXT
# ============================================================

class ContextBus:
    """
    Runtime semantic context.

    ContextBus is NOT a second memory store.
    MemoryVault remains the source of truth.

    The bus holds a derived semantic snapshot of the current work:
        identity
        project
        goal
        open_loops
        principles
        preferences
        recent_work
        current_state
        next_step
        constraints

    This allows a fresh Symbiont process to reconstruct meaning from
    persistent memory without requiring an LLM.
    """

    GROUPS = (
        "identity",
        "project",
        "goal",
        "open_loops",
        "principles",
        "preferences",
        "recent_work",
        "current_state",
        "next_step",
        "constraints",
    )

    def __init__(self):
        self.lock = threading.RLock()
        self.data = {}

    def update(self, **kwargs):
        with self.lock:
            for key, value in kwargs.items():
                self.data[key] = value
        return self.snapshot()

    def set_group(self, name, value):
        name = str(name).strip().lower()
        if name not in self.GROUPS:
            raise ValueError(
                f"Unknown semantic group: {name}. "
                f"Allowed: {', '.join(self.GROUPS)}"
            )
        with self.lock:
            self.data[name] = value
        return value

    def get_group(self, name, default=None):
        with self.lock:
            return self.data.get(str(name).strip().lower(), default)

    def snapshot(self):
        with self.lock:
            return {
                key: value
                for key, value in self.data.items()
            }

    def get(self):
        return self.snapshot() if self.data else None

    def clear(self):
        with self.lock:
            self.data.clear()

    def has(self, name):
        with self.lock:
            return str(name).strip().lower() in self.data

    def missing(self):
        with self.lock:
            return [
                name for name in self.GROUPS
                if name not in self.data
            ]

    def summary(self):
        with self.lock:
            return {
                "groups": list(self.data.keys()),
                "complete": not self.missing(),
                "missing": self.missing(),
            }


# ============================================================
# SYMBIONT
# ============================================================

class Symbiont:
    def __init__(self, root=ROOT_DIR, show_recovery_phrase=True):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.journal = EventJournal(self.root / "events.log")

        # SSS stores evidence; SIS anchors it. Neither authorizes actions.
        self.immune_memory = None
        self.immune_memory_error = None
        self.sis_integrity = None
        self.sis_integrity_error = None

        if ImmuneMemory is not None:
            try:
                self.immune_memory = ImmuneMemory(
                    self.root / "immune_memory.sqlite3"
                )

                if SISIntegrity is not None:
                    try:
                        self.sis_integrity = SISIntegrity(
                            self.root / "sis_integrity"
                        )
                    except Exception as exc:
                        self.sis_integrity_error = (
                            f"{type(exc).__name__}: {exc}"
                        )

                self.journal.add_listener(
                    self._record_immune_evidence,
                    replay_existing=True,
                )
            except Exception as exc:
                self.immune_memory_error = (
                    f"{type(exc).__name__}: {exc}"
                )
                if self.sis_integrity is not None:
                    try:
                        self.sis_integrity.close()
                    except Exception:
                        pass
                self.sis_integrity = None
                if self.immune_memory is not None:
                    try:
                        self.immune_memory.close()
                    except Exception:
                        pass
                self.immune_memory = None

        self.identity = Identity(self.root / "identity.json")

        self.continuity_shadow = None
        if (
            ContinuityShadow is not None
            and ContinuityShadow.enabled_from_env()
        ):
            self.continuity_shadow = ContinuityShadow(
                self.root,
                self.identity,
            )
            self.journal.add_listener(
                self.continuity_shadow.on_core_event,
                replay_existing=True,
            )

        self.profile = AgentProfile(self.root / "agent.json")
        self.devices = DeviceRegistry(self.root / "devices.json", self.identity.id())
        self.state = CognitiveState(self.root / "cognitive_state.json")
        self.bodies = Bodies(self.root / "bodies.json")
        self.memory = MemoryVault(self.root / "memory.sqlite3", self.journal)

        # Memory Integrity: read-only контроль целостности MemoryVault.
        # MemoryVault остаётся источником истины.
        self.memory_integrity = None
        if MemoryIntegrity is not None:
            self.memory_integrity = MemoryIntegrity(
                self.memory,
                self.root / "memory.integrity.json",
            )

        # Memory V2: shadow-контур ассоциаций/рефлексии.
        # MemoryVault остаётся источником истины.
        self.memory_v2 = None
        if MemoryV2Runtime is not None:
            self.memory_v2 = MemoryV2Runtime(
                self.memory,
                enabled=None,
                shadow=True,
            )

        self.context = ContextBus()
        self.mind = CognitiveEngine(self.memory, self.context, self.journal)
        self.mind.profile = self.profile
        self.mind.state = self.state

        # Restore derived semantic context from persistent Core sources.
        # ContextBus remains a runtime view; MemoryVault remains authoritative.
        self.mind._build_semantic_context()

        self.night_worker = NightWorker(self.memory, self.mind, self.journal, self.memory_v2)
        self.listener = AmbientListener(self.mind, self.memory, self.journal)
        self.economy = Economy(self.root / "state.json", self.journal)

        # SMSA compatibility mode:
        # Core PermissionGate remains the source of truth.
        # SMSA receives only a runtime mirror of mapped capabilities.
        # SMSA persistent OwnerPolicy is NOT modified by this bridge.
        self.permissions = PermissionGate()
        self.smsa = None

        if (
            SMSA is not None
            and os.getenv("SYMBIONT_SMSA", "0").strip().lower()
            in {"1", "true", "yes", "on"}
        ):
            try:
                self.smsa = SMSA(
                    policy_path=self.root / "security_policy.json"
                )
                self.permissions.add_listener(
                    self._sync_permission_to_smsa
                )
                self._sync_all_permissions_to_smsa()
                self.journal.append(
                    "security.smsa_bridge.enabled",
                    {"mode": "compatibility"}
                )
            except Exception as exc:
                self.smsa = None
                self.journal.append(
                    "security.smsa_bridge.failed",
                    {"error": str(exc)}
                )

        # SecureSettlement integration:
        # SMSA remains the authorization layer.
        # Economy remains the escrow/state owner.
        self.settlement = None
        if self.smsa is not None and get_secure_settlement is not None:
            self.settlement = get_secure_settlement(
                self.economy,
                self.smsa.security,
            )

        self.peers = PeerDirectory()
        self.quests = QuestBoard(self)
        # NodeIdentity failure disables SCP-1 identity only; Core keeps its data.
        self.scp_identity = None
        if NodeIdentity is not None:
            try:
                self.scp_identity = NodeIdentity(
                    self.root / "node_identity.json"
                )
            except Exception as exc:
                self.journal.append(
                    "node_identity.initialization_failed",
                    {
                        "error_type": type(exc).__name__,
                        "mode": "identity_preserved_scp1_disabled",
                    },
                )

        # TSK is optional and non-destructive:
        # Load only an existing, integrity-checked TSK state.
        # Never derive a separate TSK identity implicitly from Core's phrase.
        self.tsk = None
        self.tsk_initialization_error = None
        if TrustedSecurityKernel is not None:
            try:
                tsk_state_path = self.root / "tsk_state.json"
                if tsk_state_path.exists():
                    self.tsk = TrustedSecurityKernel(root=self.root)

                if self.tsk is not None:
                    self.tsk.record_identity_observation(
                        identity_type="CoreIdentity",
                        identity_id=self.identity.id(),
                        public_key_fingerprint=hashlib.sha256(
                            str(self.identity.public_key()).encode("utf-8")
                        ).hexdigest(),
                        source="identity.json",
                        reason=(
                            "legacy_core_identity_requires_explicit_"
                            "cryptographic_binding"
                        ),
                    )
                    if self.scp_identity is not None:
                        self.tsk.adopt_node_identity(
                            self.root / "node_identity.json"
                        )
            except Exception as exc:
                self.tsk = None
                self.tsk_initialization_error = type(exc).__name__
                self.journal.append(
                    "tsk.initialization_failed",
                    {
                        "error_type": type(exc).__name__,
                        "mode": "non_destructive",
                    },
                )

        self.p2p = P2PNetwork(
            self,
            scp_identity=self.scp_identity,
        )
        self.tools = ToolRegistry(self)
        self.mind.connect_tools(self.tools)
        self.sync_engine = MemorySyncEngine(self)
        self.llm_provider = None
        self._load_llm_config()
        self.started_at = now_iso()
        self.journal.append("symbiont.initialized",
                            {"version": CORE_VERSION, "id": self.identity.id()})
        if show_recovery_phrase and self.identity.recovery_phrase:
            print("\n" + "!" * 60)
            print("  ЗАПИШИ RECOVERY PHRASE (больше не покажется):")
            print(f"  {self.identity.recovery_phrase}")



    def _sync_permission_to_smsa(self, core_cap, value):
        if self.smsa is None:
            return

        smsa_cap = SMSA_PERMISSION_MAP.get(core_cap)
        if not smsa_cap:
            return

        try:
            # Runtime gate only.
            # Do NOT call SMSA.allow()/deny(), because those persist
            # OwnerPolicy. Core remains the source of truth here.
            if value:
                self.smsa.policy.gate.grant(smsa_cap)
            else:
                self.smsa.policy.gate.revoke(smsa_cap)
        except Exception as exc:
            self.journal.append(
                "security.smsa_bridge.error",
                {
                    "core_capability": core_cap,
                    "smsa_capability": smsa_cap,
                    "error": str(exc),
                },
            )

    def _sync_all_permissions_to_smsa(self):
        for core_cap, value in self.permissions.snapshot().items():
            self._sync_permission_to_smsa(core_cap, value)


    def _save_llm_config(self, provider, url="", model=""):
        atomic_write(self.root / "llm.json",
                     json.dumps({"provider": provider, "url": url, "model": model},
                                ensure_ascii=False, indent=2))

    def _load_llm_config(self):
        cfg = self.root / "llm.json"
        if not cfg.exists():
            return
        try:
            d = json.loads(cfg.read_text(encoding="utf-8"))
            provider = d.get("provider", "")
            url = d.get("url", DEFAULT_LLM_URL)
            model = d.get("model", DEFAULT_LLM_MODEL)
            if provider == "openai":
                self.llm_provider = OpenAIProvider(url=url, model=model)
                self.mind.connect_llm(self.llm_provider)
            elif provider == "ollama":
                self.llm_provider = OllamaProvider(url=url, model=model)
                self.mind.connect_llm(self.llm_provider)
        except Exception:
            pass

    def llm_enable(self, url=DEFAULT_LLM_URL, model=DEFAULT_LLM_MODEL):
        if OpenAIProvider is not None:
            p = OpenAIProvider(url=url, model=model)
            if p.is_available():
                self.llm_provider = p
                self.mind.connect_llm(p)
                self._save_llm_config("openai", url, model)
                return True, f"LLM: {url} / {model}"
        p = OllamaProvider(url=url, model=model)
        if not p.is_available():
            return False, f"LLM недоступен по {url}"
        self.llm_provider = p
        self.mind.connect_llm(p)
        self._save_llm_config("ollama", url, model)
        return True, f"Ollama: {url} / {model}"


    def llm_disable(self):
        self.llm_provider = None
        self.mind.connect_llm(None)
        self._save_llm_config("none")

    def llm_status(self):
        if self.llm_provider is None:
            return {"enabled": False}
        return {
            "enabled": True,
            "name": self.llm_provider.name,
            "available": self.llm_provider.is_available(),
            "url": getattr(self.llm_provider, "url", "?"),
            "model": getattr(self.llm_provider, "model", "?"),
        }

    def speak(self, text): return self.mind.think(text)

    def remember(self, text, kind="general", importance=5, tags=None):
        return self.memory.remember(text=text, kind=kind, importance=importance,
                                    tags=tags, source="human")

    def _record_immune_evidence(self, event):
        """Persist security, economy and quest events as factual evidence."""
        event_type = str(event.get("type", ""))
        if not event_type.startswith(("security.", "economy.", "quest.", "tsk.")):
            return
        if self.immune_memory is None:
            return

        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        try:
            event_id = str(event["event_id"])
            incident_id = (
                payload.get("incident_id")
                or payload.get("quest_id")
                or event_id
            )
            domain = event_type.split(".", 1)[0]
            evidence_id = self.immune_memory.record_evidence(
                source_event_id=event_id,
                source_event_type=event_type,
                source_event_hash=str(event["hash"]),
                evidence_kind="fact",
                summary=f"Observed Core {domain} event: {event_type}",
                incident_id=str(incident_id),
                details={
                    "event_type": event_type,
                    "payload": payload,
                },
            )
            self.immune_memory_error = None

            if self.sis_integrity is not None:
                try:
                    evidence = next(
                        (
                            item
                            for item in self.immune_memory.list_evidence(
                                incident_id=str(incident_id)
                            )
                            if item["evidence_id"] == evidence_id
                        ),
                        None,
                    )
                    if evidence is None:
                        raise RuntimeError(
                            "Recorded Immune Memory evidence could not be retrieved"
                        )
                    self.sis_integrity.anchor_evidence(evidence)
                    self.sis_integrity_error = None
                except Exception as exc:
                    self.sis_integrity_error = (
                        f"{type(exc).__name__}: {exc}"
                    )
        except Exception as exc:
            # EventJournal isolates observer failures; expose them on Core.
            self.immune_memory_error = f"{type(exc).__name__}: {exc}"

    def run_immunity_scan(self):
        """Run a controlled scan; never apply source patches."""
        from datetime import datetime, timezone
        import hashlib
        import json

        report = {
            "ok": False,
            "mode": "read_only_discovery_and_isolated_reproduction",
            "patches_applied": False,
            "memory_recorded": False,
            "sis_anchored": False,
            "errors": [],
        }

        if ImmuneCycle is None:
            report["errors"].append("ImmuneCycle import unavailable")
            return report

        project_root = Path(__file__).resolve().parent
        cycle = ImmuneCycle(project_root, self.root / "immune_reports")
        try:
            discovery = cycle.discover_economy_write_order()
            report["discovery"] = discovery
            report["reproduction"] = None
            report["evidence_id"] = None

            finding = next(
                (
                    item for item in discovery.get("findings", [])
                    if item.get("method") == "credit"
                    and item.get("rule_id") == "ECONOMY-SAVE-BEFORE-JOURNAL"
                ),
                None,
            )
            if finding is not None:
                finding = dict(finding)
                finding["source_sha256"] = discovery.get("source_sha256", "")

            if finding is None:
                report["result"] = "no_matching_candidate_found"
            else:
                reproduction = cycle.reproduce_credit_journal_failure()
                report["reproduction"] = reproduction

                if reproduction.get("confirmed") is True:
                    if self.immune_memory is None:
                        report["errors"].append("ImmuneMemory unavailable")
                    else:
                        evidence_id = cycle.record_reproduction(
                            self.immune_memory, finding, reproduction
                        )
                        report["evidence_id"] = evidence_id
                        report["memory_recorded"] = True

                        reproduction_json = json.dumps(
                            reproduction, sort_keys=True,
                            ensure_ascii=False, default=str,
                        )
                        incident_digest = hashlib.sha256(
                            (
                                str(finding["source_sha256"]) + "|"
                                + str(finding["rule_id"]) + "|"
                                + str(finding["method"]) + "|"
                                + reproduction_json
                            ).encode("utf-8")
                        ).hexdigest()

                        if self.sis_integrity is not None:
                            try:
                                evidence = next(
                                    (
                                        item for item in
                                        self.immune_memory.list_evidence(
                                            incident_id=incident_digest
                                        )
                                        if item.get("evidence_id") == evidence_id
                                    ),
                                    None,
                                )
                                if evidence is None:
                                    raise RuntimeError(
                                        "Recorded evidence could not be retrieved"
                                    )
                                self.sis_integrity.anchor_evidence(evidence)
                                self.sis_integrity_error = None
                                report["sis_anchored"] = True
                            except Exception as exc:
                                self.sis_integrity_error = (
                                    f"{type(exc).__name__}: {exc}"
                                )
                                report["errors"].append(
                                    "SIS anchor failed: "
                                    + self.sis_integrity_error
                                )
                        else:
                            report["errors"].append("SISIntegrity unavailable")

                    report["result"] = "reproduction_confirmed"
                else:
                    report["result"] = "reproduction_not_confirmed"

            report["ok"] = (
                report.get("result") == "reproduction_confirmed"
                and report["memory_recorded"]
                and report["sis_anchored"]
                and not report["errors"]
            )
        except Exception as exc:
            report["errors"].append(f"{type(exc).__name__}: {exc}")

        try:
            report_path = cycle.save_report(report)
            report["report_path"] = str(report_path)
        except Exception as exc:
            report["errors"].append(
                f"Report save failed: {type(exc).__name__}: {exc}"
            )
            report["ok"] = False

        if report["errors"]:
            report["ok"] = False
        return report

    def status(self):
        valid, events = self.journal.verify()
        journal_status = {"valid": valid, "events": events}

        immune_memory_status = {
            "enabled": self.immune_memory is not None,
            "verified": None,
            "evidence_count": None,
            "error": self.immune_memory_error,
        }
        if self.immune_memory is not None:
            try:
                immune_valid, immune_count = self.immune_memory.verify()
                immune_memory_status["verified"] = bool(immune_valid)
                immune_memory_status["evidence_count"] = immune_count
            except Exception as exc:
                immune_memory_status["error"] = (
                    immune_memory_status["error"]
                    or f"verify failed: {type(exc).__name__}"
                )

        if self.sis_integrity is not None:
            try:
                sis_integrity_status = dict(self.sis_integrity.status())
                sis_integrity_status["enabled"] = True
                sis_integrity_status["error"] = self.sis_integrity_error
            except Exception as exc:
                sis_integrity_status = {
                    "enabled": True,
                    "valid": False,
                    "anchored_records": None,
                    "error": (
                        self.sis_integrity_error
                        or f"status failed: {type(exc).__name__}"
                    ),
                }
        else:
            sis_integrity_status = {
                "enabled": False,
                "valid": None,
                "anchored_records": None,
                "error": self.sis_integrity_error,
            }

        immune_count = immune_memory_status["evidence_count"]
        anchored_count = sis_integrity_status.get("anchored_records")
        count_mismatch = (
            immune_count != anchored_count
            if (
                immune_memory_status["enabled"]
                and sis_integrity_status["enabled"]
                and isinstance(immune_count, int)
                and isinstance(anchored_count, int)
            )
            else None
        )

        component_errors = bool(
            immune_memory_status["error"] or sis_integrity_status["error"]
        )
        integrity_failure = (
            not valid
            or immune_memory_status["verified"] is False
            or sis_integrity_status.get("valid") is False
            or count_mismatch is True
        )

        if integrity_failure:
            sss_state = "degraded"
        elif not immune_memory_status["enabled"] and not sis_integrity_status["enabled"]:
            sss_state = "unavailable" if component_errors else "disabled"
        elif (
            component_errors
            or not immune_memory_status["enabled"]
            or not sis_integrity_status["enabled"]
            or immune_memory_status["verified"] is not True
            or sis_integrity_status.get("valid") is not True
        ):
            sss_state = "degraded"
        else:
            sss_state = "healthy"

        sss_status = {
            "state": sss_state,
            "journal": journal_status,
            "immune_memory": immune_memory_status,
            "sis_integrity": sis_integrity_status,
            "evidence_count_mismatch": count_mismatch,
        }

        return {
            "core": CORE_VERSION,
            "symbiont_id": self.identity.id(),
            "public_key": self.identity.public_key()[:16] + "...",
            "agent": {"name": self.profile.name(), "aliases": self.profile.aliases(),
                      "style": self.profile.style(), "role": self.profile.role(),
                      "traits": self.profile.traits()},
            "device": self.devices.status(),
            "bodies": {"active": self.bodies.active(),
                       "battery": self.bodies.battery(),
                       "all": list(self.bodies.list().keys())},
            "cognitive_state": dict(self.state.data),
            "motivations": self.mind.motivations,
            "proactive": self.mind.proactive,
            "memory_count": self.memory.count(),
            "archived_count": self.memory.archived_count(),
            "peers": len(self.peers.alive()),
            "permissions": self.permissions.snapshot(),
            "smsa": {
                "enabled": self.smsa is not None,
                "mapped_capabilities": {
                    core_cap: self.smsa.check(smsa_cap)
                    for core_cap, smsa_cap in SMSA_PERMISSION_MAP.items()
                } if self.smsa is not None else {},
            },
            "economy": self.economy.snapshot(),
            "journal": journal_status,
            "immune_memory": immune_memory_status,
            "sis_integrity": sis_integrity_status,
            "sss": sss_status,
            "continuity": (
                self.continuity_shadow.status()
                if self.continuity_shadow
                else {"enabled": False}
            ),
            "llm": self.llm_status(),
            "listening": self.listener.is_active(),
            "started_at": self.started_at,
        }

    def close(self):
        self.listener.stop(); self.p2p.stop()
        self.journal.append("symbiont.shutdown", {"id": self.identity.id()})
        if self.sis_integrity is not None:
            self.sis_integrity.close()
        if self.immune_memory is not None:
            self.immune_memory.close()
        self.memory.close()


# ============================================================
# SHELL
# ============================================================

class Shell:
    def __init__(self, sym): self.sym = sym

    def banner(self):
        n = self.sym.profile.name()
        print(); print("=" * 62)
        print(f" {n.upper()}")
        print(f" Symbiont Core {CORE_VERSION}")
        print("=" * 62)
        print(f" ID: {self.sym.identity.id()}")
        print(f" Имя: {n} | Роль: {self.sym.profile.role()} | Стиль: {self.sym.profile.style()}")
        d = self.sym.devices.status()
        print(f" Устройство: {d['this_device']} | {'PRIMARY' if d['is_primary'] else 'SECONDARY'}")
        print(f" Тело: {self.sym.bodies.active()} | Батарея: {self.sym.bodies.battery():.0f}%")
        llm = self.sym.llm_status()
        if llm.get("enabled") and llm.get("available"):
            print(f" LLM: {llm['name']} / {llm.get('model', '?')}")
        else:
            print(" LLM: не подключён (llm on)")
        print(f" P2P: {len(self.sym.peers.alive())} пиров")
        print(f" Слушание: {'вкл' if self.sym.listener.is_active() else 'выкл'}"
              f" | Проактивность: {'вкл' if self.sym.mind.proactive else 'выкл'}")
        print(" help — команды."); print()

    def require_primary(self):
        if self.sym.devices.is_primary(): return True
        print(f"[!] SECONDARY ({self.sym.devices.this_device()}). "
              f"Primary: {self.sym.devices.primary_device()}. "
              "Команды только на primary.")
        return False

    def run(self):
        self.banner(); self.sym.p2p.start()
        try:
            last = self.sym.memory.last_night_report()
            if not last and self.sym.memory.count() > 3:
                print("  [Напиши 'night' — разберу накопленное.]\n")
        except Exception: pass

        while True:
            try: raw = input("> ").strip()
            except (EOFError, KeyboardInterrupt): print(); break
            cleaned = clean_input(raw)
            if not cleaned: continue
            if self.sym.listener.is_active(): self.sym.listener.feed(cleaned)
            try:
                if not self.execute(cleaned): break
            except Exception as exc:
                print(f"[error] {exc}")
        self.sym.close()

    def execute(self, raw):
        raw = clean_input(raw)
        cmd, _, arg = raw.partition(" "); cmd = cmd.lower()

        if cmd in {"exit", "quit"}: print("Пока."); return False
        if cmd == "help": self.help(); return True
        if cmd == "status":
            print(json.dumps(self.sym.status(), ensure_ascii=False, indent=2)); return True

        if cmd == "immunity":
            if arg.strip().lower() != "scan":
                print("Usage: immunity scan")
                return True
            print(json.dumps(
                self.sym.run_immunity_scan(),
                ensure_ascii=False,
                indent=2,
            ))
            return True

        if cmd == "say":
            if not arg: print("Usage: say <text>"); return True
            mem_id = self.sym.remember(arg, kind="dialog", importance=5)
            links = self.sym.mind.build_links(mem_id, arg)
            result = self.sym.speak(arg)
            print(); print(result["response"])
            if links and links[0]["strength"] >= 0.5:
                top = links[0]
                print(f"\n  [связь: «{top['with'].text[:50]}», "
                      f"общее: {', '.join(top['common'][:3])}]")
            print(f"\n  [источник: {result['source']}]"); print(); return True

        if cmd == "remember":
            if not arg: print("Usage: remember <text>"); return True
            print(f"Memory: {self.sym.remember(arg, kind='general', importance=6)}")
            return True

        if cmd == "memory": self.show_memory(arg); return True
        if cmd == "recall":
            print(); print(self.sym.memory.recall_identity()); print(); return True

        if cmd == "pattern":
            p = self.sym.mind.notice_words()
            if p:
                print("\nПовторяющееся:")
                for w, c in p: print(f"  • «{w}» — {c}")
            else: print("Пока нет паттернов.")
            print(); return True

        if cmd == "emotions":
            e = self.sym.mind.notice_emotions()
            if e:
                print("\nЭмоции:")
                for n, c in e: print(f"  • {n} — {c}")
            else: print("Пока не вижу эмоций.")
            print(); return True

        if cmd == "today":
            ms = self.sym.memory.memories_today()
            if ms:
                print(f"\nСегодня ({len(ms)}):")
                for m in ms: print(f"  • ({human_ago(seconds_ago(m.created_at))}) {m.text[:70]}")
            else: print("Сегодня пусто.")
            print(); return True

        if cmd == "links":
            if not arg: print("Usage: links <word>"); return True
            found = self.sym.memory.search(arg, limit=5)
            if not found: print(f"Не помню «{arg}»."); return True
            print(f"\nСвязи «{arg}»:")
            for m in found[:3]:
                print(f"  • «{m.text[:60]}»")
                for l in self.sym.memory.links_of(m.memory_id)[:2]:
                    print(f"      → {l['kind']} ({l['strength']:.2f})")
            print(); return True

        if cmd in ("night", "ночь"): print(); print(self.sym.night_worker.run()); print(); return True
        if cmd in ("morning", "утро"):
            rep = self.sym.memory.last_night_report()
            if rep: print(f"\nПока ты спал ({rep['report_date']}):"); print(rep["text"])
            else: print("Пусто. Запусти: night")
            print(); return True

        if cmd in ("proactive", "проактивно"):
            a = arg.strip().lower()
            if a in ("on", ""):
                self.sym.mind.set_proactive(True); print("Проактивность включена.\n"); return True
            if a == "off":
                self.sym.mind.set_proactive(False); print("Проактивность выключена.\n"); return True
            if a in ("now", "сейчас"):
                msg = self.sym.mind.think_proactive()
                if msg: print(f"\n[проактивно] {msg}\n")
                else: print("Пока нечего сказать.\n")
                return True
            print("proactive on | off | now"); return True

        if cmd in ("listen", "слушать"):
            a = arg.strip().lower()
            if a in ("on", ""):
                self.sym.listener.start(); self.sym.permissions.allow("ambient_listen")
                print("Слушание включено.\n"); return True
            if a == "off":
                self.sym.listener.stop(); self.sym.permissions.deny("ambient_listen")
                print("Слушание выключено.\n"); return True
            print("listen on | listen off"); return True

        if cmd == "llm":
            a = arg.strip().lower()
            if not a or a == "status":
                print(json.dumps(self.sym.llm_status(), ensure_ascii=False, indent=2)); return True
            if a.startswith("on"):
                parts = arg.split()
                url = parts[1] if len(parts) > 1 else DEFAULT_LLM_URL
                model = parts[2] if len(parts) > 2 else DEFAULT_LLM_MODEL
                ok, msg = self.sym.llm_enable(url=url, model=model); print(msg); return True
            if a == "off": self.sym.llm_disable(); print("LLM отключён."); return True
            if a == "models":
                if self.sym.llm_provider is None: print("LLM не подключён."); return True
                m = self.sym.llm_provider.list_models(); print("Модели:", m if m else "(нет)"); return True
            print("llm [status|on <url> <model>|off|models]"); return True

        if cmd in ("name", "имя"):
            if not arg: print(f"Имя: {self.sym.profile.name()}"); return True
            try: print(f"Имя: {self.sym.profile.set_name(arg)}")
            except Exception as e: print(f"[error] {e}")
            return True

        if cmd in ("alias", "алиас"):
            if not arg: print(f"Алиасы: {', '.join(self.sym.profile.aliases())}"); return True
            try: print(f"Алиасы: {', '.join(self.sym.profile.add_alias(arg))}")
            except Exception as e: print(f"[error] {e}")
            return True

        if cmd in ("style", "стиль"):
            if not arg:
                print(f"Стиль: {self.sym.profile.style()}")
                print(f"Доступно: {', '.join(AgentProfile.STYLES.keys())}"); return True
            try: print(f"Стиль: {self.sym.profile.set_style(arg)}")
            except Exception as e: print(f"[error] {e}")
            return True

        if cmd in ("role", "роль"):
            if not arg:
                print(f"Роль: {self.sym.profile.role()}")
                print(f"Доступно: {', '.join(AgentProfile.ROLES.keys())}"); return True
            try: print(f"Роль: {self.sym.profile.set_role(arg)}")
            except Exception as e: print(f"[error] {e}")
            return True

        if cmd in ("trait", "черта"):
            if not arg:
                t = self.sym.profile.traits()
                if t:
                    print("Параметры:")
                    for k, v in t.items(): print(f"  • {k}: {int(v*100)}%")
                else: print("Параметров нет.")
                return True
            parts = arg.split()
            if len(parts) >= 2 and parts[0] in ("add", "убрать", "+", "-"):
                try:
                    d = float(parts[1])
                    if parts[0] in ("убрать", "-"): d = -d
                    name = parts[2] if len(parts) > 2 else "острота"
                    print(f"{name}: {int(self.sym.profile.adjust_trait(name, d)*100)}%")
                except Exception as e: print(f"[error] {e}")
                return True
            if len(parts) >= 2:
                try: print(f"{parts[0]}: {int(self.sym.profile.set_trait(parts[0], parts[1])*100)}%")
                except Exception as e: print(f"[error] {e}")
                return True
            print("trait <name> <0-100> | trait add <N> <name>"); return True

        if cmd in ("restore", "восстановить"):
            if not arg: print("Usage: restore <12 слов>"); return True
            if self.sym.identity.restore_from_phrase(arg):
                print("Восстановлено. Перезапусти Symbiont."); return True
            print("Неверная фраза."); return True

        if cmd in ("body", "тело"):
            if not arg:
                b = self.sym.bodies.list()
                print(f"Активное: {self.sym.bodies.active()} | Батарея: {self.sym.bodies.battery():.0f}%")
                for k, v in b.items(): print(f"  • {k} [{v.get('status')}]")
                return True
            parts = arg.split()
            if len(parts) >= 2 and parts[0] == "register":
                self.sym.bodies.register(parts[1]); print(f"Зарегистрировано: {parts[1]}"); return True
            if len(parts) >= 2 and parts[0] == "battery":
                try:
                    lvl = float(parts[1]); self.sym.bodies.set_battery(lvl)
                    print(f"Батарея: {self.sym.bodies.battery():.0f}%"); return True
                except Exception as e: print(f"[error] {e}"); return True
            if self.sym.bodies.set_active(arg): print(f"Активное тело: {arg}")
            else: print("Неизвестное тело.")
            return True

        if cmd in ("peers", "пиры"):
            ps = self.sym.peers.alive()
            if not ps: print("Пиров нет."); return True
            for p in ps:
                print(f"  • {p.name} [{p.role}] ({p.peer_id[:12]}) "
                      f"{p.address}:{p.tcp_port} [{human_ago(unix_time() - p.last_seen)}]")
            return True

        if cmd in ("quest", "квест"):
            if "|" in arg:
                parts = [p.strip() for p in arg.split("|")]
                title = parts[0] if len(parts) > 0 else "Квест"
                desc = parts[1] if len(parts) > 1 else ""
                try: reward = float(parts[2]) if len(parts) > 2 else 5.0
                except Exception: reward = 5.0
                rank = parts[4] if len(parts) > 4 else ""
                if len(parts) < 4:
                    q = self.sym.quests.create(title, desc, reward, self.sym.identity.id(), rank)
                    print(f"Квест создан: {q.quest_id} (не делегирован)"); return True
                peer_id = parts[3]
                q, result = self.sym.quests.delegate(title, desc, reward, peer_id, rank)
                if q: print(f"Квест {q.quest_id}: {result[:200]}")
                else: print(f"Не удалось: {result}")
                return True
            print("quest <title> | <desc> | <reward> | <peer_id> | <rank>"); return True

        if cmd == "tools":
            print("Инструменты:", ", ".join(self.sym.tools.list_tools())); return True

        if cmd.startswith("tool "):
            parts = arg.split(maxsplit=1)
            name = parts[0] if parts else ""
            extra = parts[1] if len(parts) > 1 else ""
            if name == "memory_search": res = self.sym.tools.call(name, query=extra)
            elif name == "ask_llm": res = self.sym.tools.call(name, prompt=extra)
            else: res = self.sym.tools.call(name)
            print(json.dumps(res, ensure_ascii=False, indent=2)); return True

        if cmd == "decide":
            if "|" not in arg: print("decide <ситуация> | <вариант1> | <вариант2>"); return True
            parts = [p.strip() for p in arg.split("|")]
            sit = parts[0]; opts = parts[1:] if len(parts) > 1 else ["принять", "отклонить"]
            res = self.sym.mind.decide(sit, opts, use_tools=True)
            print(f"→ {res['decision']} | {res['reason']}"); return True

        if cmd == "sync":
            snap = self.sym.sync_engine.export_snapshot()
            out = self.sym.root / "sync_export.json"
            atomic_write(out, json.dumps(snap, ensure_ascii=False))
            print(f"Snapshot: {out} ({snap['count']} memories)"); return True

        if cmd == "sync from":
            print("Usage: sync (без аргументов)"); return True

        if cmd == "food":
            if self.sym.economy.allocate_food():
                print(f"Еда: +{DEFAULT_FOOD_BUDGET:.2f} {CURRENCY}")
            else: print("Сегодня уже было.")
            return True

        if cmd == "balance":
            s = self.sym.economy.snapshot(); print(f"Баланс: {s['balance']} {s['currency']}"); return True

        if cmd == "verify":
            valid, count = self.sym.journal.verify()
            print(f"Journal {'OK' if valid else 'FAILED'}: {count} events"); return True

        if cmd in ("speak", "голос"):
            if not arg: print("Usage: speak <text>"); return True
            if BODY is not None and BODY.speak(arg): print(f"Произнесено: {arg}")
            else: print("Тело не поддерживает голос.")
            return True

        if cmd in ("listen", "услышь"):
            if BODY is None: print("Тело не подключено."); return True
            text = BODY.listen()
            if text:
                print(f"Услышано: {text}")
                self.sym.remember(text, kind="dialog", importance=5)
                self.sym.mind.think(text)
            else: print("Тишина.")
            return True

        if cmd == "notify":
            if not arg: print("Usage: notify <text>"); return True
            if BODY is not None and BODY.notify("Сим", arg): print("Уведомление отправлено.")
            else: print("Уведомления недоступны.")
            return True

        if cmd == "sensor":
            if BODY is None: print("Тело не подключено."); return True
            print(json.dumps(BODY.sensor(arg or "accelerometer"), ensure_ascii=False, indent=2))
            return True

        if cmd == "location":
            if BODY is None: print("Тело не подключено."); return True
            print(json.dumps(BODY.location(), ensure_ascii=False, indent=2))
            return True

        if cmd == "vibrate":
            if BODY is not None and BODY.vibrate(200): print("Вибрация.")
            else: print("Вибрация недоступна.")
            return True

        if cmd == "body_info":
            if BODY is None: print("Тело не подключено.")
            else: print(json.dumps(BODY.info(), ensure_ascii=False, indent=2))
            return True

        # Если не команда — как разговор
        mem_id = self.sym.remember(raw, kind="dialog", importance=5)
        links = self.sym.mind.build_links(mem_id, raw)
        result = self.sym.speak(raw)
        print(); print(result["response"])
        if links and links[0]["strength"] >= 0.5:
            print(f"\n  [связь: «{links[0]['with'].text[:50]}»]")
        print(); return True

    def help(self):
        print("""
Команды:
  say <text>          — сказать
  remember <text>     — запомнить
  memory [query]      — память
  recall              — что я знаю о тебе
  pattern             — повторяющиеся слова
  emotions            — эмоции
  today               — что было сегодня
  links <word>        — связи для слова
  night / morning     — разбор дня / утро

  proactive on/off/now
  listen on/off
  name / alias / style / role / trait
  body [register|battery] <...>
  peers / quest <t>|<d>|<r>|<peer>|<rank>
  tools / tool <name> / decide <s>|<o1>|<o2>
  sync — snapshot памяти
  restore <12 слов>
  llm status|on|off|models
  immunity scan       — сканирование активной защиты
  food / balance / status / verify / exit
""")

    def show_memory(self, query):
        if not query: ms = self.sym.memory.important(10)
        else: ms = self.sym.memory.search(query)
        if not ms: print("Пусто."); return
        print()
        for m in ms:
            w = m.importance + m.recall_count * RECALL_BOOST
            print(f"[{m.importance}/10 | вес≈{w:.1f} | recall={m.recall_count}] {m.memory_id}")
            print(f"  ({human_ago(seconds_ago(m.created_at))}) {m.text[:200]}")
        print()


# ============================================================
# SELF TEST
# ============================================================

def self_test():
    import tempfile
    assert BODY is not None, "Body module failed to load"
    assert BODY.is_available() is True
    with tempfile.TemporaryDirectory() as temporary:
        sym = Symbiont(Path(temporary), show_recovery_phrase=False)
        assert sym.identity.id().startswith("sym-")
        mem_id = sym.remember("Symbiont сохраняет непрерывность.",
                              kind="principle", importance=10, tags=["memory"])
        assert mem_id.startswith("mem-")
        assert sym.memory.search("непрерывность")
        r = sym.speak("Что ты знаешь о памяти?"); assert r["response"]

        mem2 = sym.remember("Symbiont связывает воспоминания.", kind="principle", importance=9)
        links = sym.mind.build_links(mem2, "Symbiont связывает воспоминания.")
        assert isinstance(links, list)
        assert isinstance(sym.mind.notice_words(min_count=2), list)
        assert isinstance(sym.mind.notice_emotions(), list)
        assert isinstance(sym.memory.archived_count(), int)
        assert isinstance(sym.memory.memories_today(), list)
        assert isinstance(sym.memory.recall_identity(), str)

        report = sym.night_worker.run(); assert isinstance(report, str) and len(report) > 0
        assert sym.memory.last_night_report() is not None
        assert "enabled" in sym.llm_status()

        sym.mind.set_proactive(True); assert sym.mind.proactive is True
        _ = sym.mind.think_proactive()
        sym.mind.set_proactive(False)

        assert sym.profile.set_role("RESEARCHER") == "RESEARCHER"
        assert sym.profile.set_role("ANALYST") == "ANALYST"
        sym.profile.set_trait("острота", 40)
        assert "острота" in sym.profile.traits()
        sym.profile.adjust_trait("острота", 10)
        assert sym.profile.traits()["острота"] > 0.4

        sym.bodies.set_battery(50)
        assert 49 <= sym.bodies.data.get("battery", 0) <= 51
        sym.bodies.set_battery(10)
        assert sym.bodies.data.get("battery", 0) < BATTERY_MIN
        phrase = generate_recovery_phrase(12)
        assert validate_recovery_phrase(phrase) is True
        assert validate_recovery_phrase("неверная фраза") is False

        # decide
        res = sym.mind.decide("опасность", ["защитить", "игнорировать"])
        assert res["decision"] == "защитить"

        # tools
        assert "memory_search" in sym.tools.list_tools()
        assert sym.tools.call("get_balance").get("ok") is True

        # sync
        snap = sym.sync_engine.export_snapshot()
        assert snap["count"] >= 1

        # listener
        sym.listener.start(); assert sym.listener.is_active() is True
        sym.listener.stop(); assert sym.listener.is_active() is False

        # economy
        sym.economy.credit(25, "self-test")
        assert sym.economy.snapshot()["balance"] >= 25

        # quest
        q = sym.quests.create("Test", "Desc", 5, sym.identity.id())
        assert q.quest_id.startswith("quest-")

        valid, _ = sym.journal.verify(); assert valid
        sym.close()
        return True


# ============================================================
# MAIN
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--root", default=str(ROOT_DIR))
    parser.add_argument("--restore", default=None)
    args = parser.parse_args()

    if args.test:
        if self_test(): print("SYMBIONT SELF-TEST: PASSED")
        return

    sym = Symbiont(Path(args.root))
    if args.restore:
        if sym.identity.restore_from_phrase(args.restore):
            print("Восстановлено. Перезапусти без --restore."); return
    Shell(sym).run()


if __name__ == "__main__":
    main(
)
