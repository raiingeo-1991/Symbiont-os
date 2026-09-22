#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SYMBIONT CORE v11.0
Симбиоз и Мир.
"""

from __future__ import annotations

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
from core.memory_v2_runtime import MemoryV2Runtime
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
        self.path = path; self.lock = threading.RLock(); self._cached_last_hash = None

    def _last_hash(self):
        # Читаем events.log только один раз.
        # Последующие append() используют последний hash из памяти.
        if self._cached_last_hash is not None:
            return self._cached_last_hash

        if not self.path.exists():
            self._cached_last_hash = "0" * 64
            return self._cached_last_hash

        last = ""
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = line.strip()

        if not last:
            self._cached_last_hash = "0" * 64
            return self._cached_last_hash

        try:
            self._cached_last_hash = json.loads(last).get(
                "hash", "0" * 64
            )
        except Exception:
            self._cached_last_hash = "0" * 64

        return self._cached_last_hash

    def append(self, event_type, payload):
        with self.lock:
            prev = self._last_hash()
            event = {"event_id": uuid.uuid4().hex, "time": now_iso(),
                     "type": event_type, "payload": payload, "previous": prev}
            event["hash"] = digest(event)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(canonical_json(event) + "\n"); f.flush(); os.fsync(f.fileno())
                self._cached_last_hash = event["hash"]
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
                    (fts_query,)).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT * FROM memories ORDER BY importance DESC, updated_at DESC LIMIT 500").fetchall()

        scored = []
        for row in rows:
            w = self._decay(row)
            if w < min_weight: continue
            if self.fts_available and fts_query:
                # SQLite FTS5 bm25() returns negative values: more negative is better.
                # Scale the small default magnitudes into a useful 0..10 signal.
                raw_bm25 = float(row["fts_score"] or 0.0)
                fts_score = max(0.0, min(10.0, (-raw_bm25) * 1_000_000.0))
            else:
                hay = (str(row["text"]) + " " + str(row["kind"]) + " " + str(row["project"] or "") + " " + str(row["tags"])).lower()
                fts_score = sum(2.0 for word in str(query).lower().split() if len(word) >= 2 and word in hay)
                if fts_score <= 0:
                    continue
            score = fts_score + w + self._ranking_boost(row, query)
            scored.append((score, row))

        scored.sort(key=lambda x: (x[0], x[1]["updated_at"]), reverse=True)
        out = []
        for _, row in scored[:limit]:
            self.mark_recall(row["memory_id"]); out.append(self._to_record(row))
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
                    (max(1, int(limit)),)
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
        critical = any(x in text for x in ("опасность", "атака", "сбой", "критично", "угроза"))
        tool_hints = []
        if use_tools and self.tools:
            if any(x in text for x in ("память", "раньше", "история")):
                r = self.tools.call("memory_search", query=situation[:60])
                if r.get("ok"): tool_hints.append(f"memory:{len(r['result'])}")
            if any(x in text for x in ("баланс", "деньги", "награда")):
                r = self.tools.call("get_balance")
                if r.get("ok"): tool_hints.append(f"balance:{r['result'].get('balance')}")
        scored = []
        for i, opt in enumerate(options):
            ot = str(opt).lower(); score = 0.0
            if critical and any(x in ot for x in ("защитить", "исправить", "помочь", "безопасность")):
                score += 5.0 + s.get("caution", 0.5) * 1.5
            if any(x in ot for x in ("игнорировать", "риск", "удалить", "отключить")):
                score -= 4.0 + s.get("stress", 0.0)
            mots = " ".join(self.motivations).lower()
            if "protect" in mots and "защит" in ot: score += 1.2
            if "secure_resources" in mots and any(x in ot for x in ("заработок", "награда", "квест")):
                score += 1.5
            score += s.get("confidence", 0.5) * 0.6
            scored.append((score, -i, opt))
        scored.sort(reverse=True)
        result = {"decision": scored[0][2],
                  "reason": "безопасность, мотивации, экономика, автономия",
                  "scores": [{"option": x[2], "score": round(x[0], 3)} for x in scored],
                  "tool_hints": tool_hints, "time": now_iso()}
        return result

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
        self.recalculate_motivations()
        source = "local"; response = ""
        if self.llm is not None and self.llm.is_available():
            ans = self.llm.chat(self._llm_messages(request, memories), timeout=90.0)
            if ans: response = ans.strip(); source = self.llm.name
        if not response:
            response = self._local(request, memories); source = "local"
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

    def _local(self, request, memories):
        low = request.lower()
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
    def __init__(self, memory, mind, journal):
        self.memory = memory; self.mind = mind; self.journal = journal

    def run(self):
        today = datetime.now(timezone.utc).date().isoformat()
        existing = self.memory.night_report_for_date(today)
        if existing: return existing["text"]
        mems = self.memory.memories_today()
        principles = self.memory.principles(5)
        open_loops = self.memory.open_loops(8)
        if not mems and not principles and not open_loops: return "Сегодня я ничего не запомнил."
        diary = [f"• {m.text[:150]}" for m in mems if m.kind in ("dialog", "general", "experience")]
        pat = self.mind.notice_words(limit=30, min_count=2)
        pat_lines = [f"• «{w}» — {c}" for w, c in pat[:5]]
        emo = self.mind.notice_emotions(limit=30)
        emo_lines = [f"• {e} — {c}" for e, c in emo[:5]]
        goals = []
        for m in mems:
            if m.kind not in ("dialog", "general", "experience"):
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
# CONVERSATIONAL LEARNING / SOURCE TRUST
# ============================================================

class LearningSource:
    OWNER = "owner"
    KNOWN_PERSON = "known_person"
    UNKNOWN = "unknown"
    BACKGROUND = "background"


class LearningPolicy:
    """
    Controls whether observed speech may become durable owner knowledge.

    Important:
    Hearing something does not mean learning it as owner truth.
    """

    VERSION = "LEARNING/1"

    def __init__(self):
        self.lock = threading.RLock()
        self.owner_confirmed = 0
        self.rejected_unknown = 0

    def classify(self, source):
        source = str(source or LearningSource.UNKNOWN).strip().lower()
        if source in {
            LearningSource.OWNER,
            LearningSource.KNOWN_PERSON,
            LearningSource.UNKNOWN,
            LearningSource.BACKGROUND,
        }:
            return source
        return LearningSource.UNKNOWN

    def should_learn(self, source, explicit_confirmation=False):
        source = self.classify(source)

        with self.lock:
            if source == LearningSource.OWNER:
                self.owner_confirmed += 1
                return True

            if source == LearningSource.KNOWN_PERSON:
                return bool(explicit_confirmation)

            self.rejected_unknown += 1
            return False

    def decision(self, source, explicit_confirmation=False):
        source = self.classify(source)
        learn = self.should_learn(source, explicit_confirmation)

        return {
            "source": source,
            "learn": learn,
            "confidence": (
                1.0 if source == LearningSource.OWNER
                else 0.8 if source == LearningSource.KNOWN_PERSON and explicit_confirmation
                else 0.0
            ),
            "reason": (
                "owner_source"
                if learn and source == LearningSource.OWNER
                else "confirmed_known_person"
                if learn
                else "source_not_trusted_for_owner_learning"
            ),
        }

    def status(self):
        with self.lock:
            return {
                "version": self.VERSION,
                "owner_confirmed": self.owner_confirmed,
                "rejected_unknown": self.rejected_unknown,
            }




# ============================================================
# CONVERSATIONAL PATTERN LEARNING
# ============================================================

class LearningCandidate:
    """
    Temporary knowledge candidate discovered from ambient speech.

    It is NOT owner knowledge until explicitly confirmed.
    """

    VERSION = "CANDIDATE/1"

    def __init__(self, text, confidence=0.0, evidence=None):
        self.text = str(text).strip()
        self.confidence = float(confidence)
        self.evidence = list(evidence or [])
        self.status = "pending"
        self.observations = 1

    def add_observation(self, text, confidence_gain=0.18):
        text = str(text).strip()

        if text:
            self.evidence.append(text[:500])

        self.observations += 1
        self.confidence = min(
            0.98,
            self.confidence + float(confidence_gain),
        )

    def to_dict(self):
        return {
            "version": self.VERSION,
            "text": self.text,
            "confidence": round(self.confidence, 3),
            "observations": self.observations,
            "evidence": self.evidence[-5:],
            "status": self.status,
        }


class ConversationalPatternLearner:
    """
    Detects potentially meaningful patterns in ambient speech.

    Ambient speech is treated as evidence, not owner truth.

    A candidate becomes owner knowledge only after explicit
    confirmation from the owner.
    """

    VERSION = "PATTERN/1"

    # Words/phrases suggesting a stable personal preference,
    # habit, need, routine or recurring state.
    PATTERN_MARKERS = (
        "люблю",
        "любишь",
        "нравится",
        "нравится мне",
        "предпочитаю",
        "предпочитаешь",
        "обычно",
        "часто",
        "всегда",
        "никогда",
        "не люблю",
        "не нравится",
        "мне удобнее",
        "тебе удобнее",
        "тебе нравится",
        "твой",
        "твоя",
        "твоё",
        "тебе",
        "ты обычно",
        "ты часто",
        "ты всегда",
    )

    # Words that usually indicate an ordinary event rather than
    # stable knowledge worth asking the owner about.
    LOW_VALUE_MARKERS = (
        "сегодня",
        "сейчас",
        "вчера",
        "завтра",
        "привет",
        "пока",
        "спасибо",
        "извини",
    )

    def __init__(self, learning_policy=None):
        self.learning_policy = learning_policy
        self.lock = threading.RLock()
        self.candidates = {}
        self.rejected = set()
        self.confirmed = 0

    def _normalize(self, text):
        text = str(text or "").lower().strip()

        replacements = {
            "ё": "е",
            ",": " ",
            ".": " ",
            "!": " ",
            "?": " ",
            ":": " ",
            ";": " ",
            "(": " ",
            ")": " ",
            '"': " ",
            "'": " ",
            "—": " ",
            "-": " ",
        }

        for a, b in replacements.items():
            text = text.replace(a, b)

        return " ".join(text.split())

    def _tokens(self, text):
        stop = {
            "я", "ты", "он", "она", "мы", "вы",
            "это", "и", "а", "но", "же", "в", "во",
            "на", "по", "с", "со", "к", "у", "из",
            "для", "что", "как", "мне", "тебе",
        }

        result = []

        for word in self._normalize(text).split():
            if len(word) < 3 or word in stop:
                continue

            # Lightweight Russian stem approximation.
            for suffix in (
                "ами", "ями", "ого", "ему", "ому",
                "ами", "ями", "ов", "ев",
                "ах", "ях", "ы", "и", "а", "я",
                "е", "о", "у", "ю", "ь",
            ):
                if len(word) > 5 and word.endswith(suffix):
                    word = word[:-len(suffix)]
                    break

            result.append(word)

        return set(result)

    def _similarity(self, a, b):
        ta = self._tokens(a)
        tb = self._tokens(b)

        if not ta or not tb:
            return 0.0

        intersection = len(ta & tb)
        union = len(ta | tb)

        if not union:
            return 0.0

        return intersection / union

    def _is_pattern_candidate(self, text):
        normalized = self._normalize(text)

        if len(normalized) < 8:
            return False

        marker_hit = any(
            marker in normalized
            for marker in self.PATTERN_MARKERS
        )

        if not marker_hit:
            return False

        # A phrase containing only transient context should not
        # immediately become a learning candidate.
        low_value_count = sum(
            1
            for marker in self.LOW_VALUE_MARKERS
            if marker in normalized
        )

        return low_value_count < 2

    def observe(self, text, source=LearningSource.UNKNOWN):
        """
        Observe speech without treating it as owner knowledge.

        Returns:
            None
            or a candidate dict when confirmation should be requested.
        """

        text = str(text or "").strip()

        if not text:
            return None

        source = (
            self.learning_policy.classify(source)
            if self.learning_policy is not None
            else str(source)
        )

        # We only build candidates from ambient/unknown speech.
        if source not in {
            LearningSource.UNKNOWN,
            LearningSource.BACKGROUND,
        }:
            return None

        if not self._is_pattern_candidate(text):
            return None

        normalized = self._normalize(text)

        with self.lock:

            if normalized in self.rejected:
                return None

            # First observation.
            if normalized not in self.candidates:
                candidate = LearningCandidate(
                    text=text,
                    confidence=0.42,
                    evidence=[text[:500]],
                )

                self.candidates[normalized] = candidate
                return None

            candidate = self.candidates[normalized]
            candidate.add_observation(text)

            # Confirmation threshold.
            if (
                candidate.observations >= 3
                and candidate.confidence >= 0.72
                and candidate.status == "pending"
            ):
                candidate.status = "needs_confirmation"

                return {
                    "question": (
                        "Я заметил устойчивую закономерность: "
                        f"«{candidate.text}». "
                        "Запомнить это?"
                    ),
                    "candidate": candidate.to_dict(),
                }

        return None

    def pending(self):
        with self.lock:
            return [
                candidate.to_dict()
                for candidate in self.candidates.values()
                if candidate.status == "needs_confirmation"
            ]

    def confirm(self, normalized_text=None):
        with self.lock:

            selected = None

            for key, candidate in self.candidates.items():
                if candidate.status != "needs_confirmation":
                    continue

                if (
                    normalized_text is None
                    or key == self._normalize(normalized_text)
                ):
                    selected = (key, candidate)
                    break

            if selected is None:
                return None

            key, candidate = selected

            candidate.status = "confirmed"
            self.confirmed += 1

            return candidate.to_dict()

    def reject(self, normalized_text=None):
        with self.lock:

            for key, candidate in self.candidates.items():
                if candidate.status != "needs_confirmation":
                    continue

                if (
                    normalized_text is None
                    or key == self._normalize(normalized_text)
                ):
                    candidate.status = "rejected"
                    self.rejected.add(key)

                    return candidate.to_dict()

        return None

    def status(self):
        with self.lock:
            return {
                "version": self.VERSION,
                "candidates": len(self.candidates),
                "pending": len([
                    c for c in self.candidates.values()
                    if c.status == "needs_confirmation"
                ]),
                "confirmed": self.confirmed,
                "rejected": len(self.rejected),
            }




# ============================================================
# AMBIENT LISTENER
# ============================================================

class AmbientListener:
    def __init__(self, mind, memory, journal, learning_policy=None):
        self.mind = mind; self.memory = memory; self.journal = journal
        self.learning_policy = learning_policy
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

            # Ambient speech is never owner knowledge automatically.
            # First send it through the pattern-learning layer.
            pattern_event = None

            if self.learning_policy is not None:
                pattern_event = None

            try:
                pattern_event = self.learning.pattern_learning.observe(
                    text,
                    source=source,
                )
            except Exception as exc:
                self.journal.append(
                    "learning.pattern_error",
                    {"error": str(exc)[:300]},
                )

            source = LearningSource.UNKNOWN

            try:
                pattern_event = self.learning.pattern_learning.observe(
                    text,
                    source=source,
                )
            except Exception as exc:
                self.journal.append(
                    "learning.pattern_error",
                    {"error": str(exc)[:300]},
                )

            if pattern_event:
                self.journal.append(
                    "learning.pattern_candidate",
                    {
                        "question": pattern_event["question"],
                        "candidate": pattern_event["candidate"],
                    },
                )

                # The ambient worker deliberately does NOT promote
                # this candidate to owner memory.
                print("\n[SYMBIONT] " + pattern_event["question"])

            decision = (
                self.learning_policy.decision(source)
                if self.learning_policy is not None
                else {
                    "source": source,
                    "learn": False,
                    "confidence": 0.0,
                    "reason": "no_learning_policy",
                }
            )

            markers = ["хочу", "надо", "устал", "работа", "вода", "проблем", "помощь", "план"]

            if any(m in text.lower() for m in markers):
                metadata = {
                    "learning_source": decision["source"],
                    "learning_allowed": decision["learn"],
                    "learning_confidence": decision["confidence"],
                    "learning_reason": decision["reason"],
                }

                mem_id = self.memory.remember(
                    text,
                    kind="ambient",
                    importance=4,
                    source="mic",
                    metadata=metadata,
                )

                self.mind.build_links(mem_id, text)

                self.journal.append(
                    "ambient.captured",
                    {
                        "text": text[:200],
                        "learning_source": decision["source"],
                        "learning_allowed": decision["learn"],
                    },
                )


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
    def __init__(self, node, udp_port=P2P_UDP_PORT, tcp_port=P2P_TCP_PORT):
        self.node = node; self.udp_port = udp_port; self.tcp_port = tcp_port
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._udp_listen, daemon=True).start()
        threading.Thread(target=self._udp_beacon, daemon=True).start()
        threading.Thread(target=self._tcp_server, daemon=True).start()

    def stop(self): self.running = False

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
            if not data: return
            req = json.loads(data.decode("utf-8"))
            sender = req.get("sender"); sig = req.get("signature", "")
            peer = self.node.peers.get(sender)
            if not peer or not self.node.identity.verify(req, sig, peer.public_key):
                conn.sendall(canonical_json({"status": "UNAUTHORIZED"}).encode()); return
            action = req.get("action")
            if action == "QUEST_OFFER":
                resp = self.node.quests.handle_incoming(req)
                conn.sendall(canonical_json(resp).encode())
            elif action == "PING":
                conn.sendall(canonical_json({"status": "PONG",
                                             "sender": self.node.identity.id()}).encode())
            else:
                conn.sendall(canonical_json({"status": "UNKNOWN"}).encode())
        except Exception: pass
        finally:
            try: conn.close()
            except Exception: pass

    def send_to(self, peer_id, packet):
        peer = self.node.peers.get(peer_id)
        if not peer: return None
        packet["sender"] = self.node.identity.id()
        packet["signature"] = self.node.identity.sign(packet)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(8.0)
            s.connect((peer.address, peer.tcp_port))
            s.sendall(canonical_json(packet).encode("utf-8"))
            data = s.recv(65536); s.close()
            return json.loads(data.decode("utf-8"))
        except Exception: return None


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
        if self.node.economy.snapshot()["balance"] < reward:
            return None, "Недостаточно средств"
        q = self.create(title, description, reward, self.node.identity.id(), required_rank)
        packet = {"action": "QUEST_OFFER", "quest_id": q.quest_id, "title": q.title,
                  "description": q.description, "reward": q.reward, "creator": q.creator,
                  "required_rank": required_rank}
        resp = self.node.p2p.send_to(peer_id, packet)
        if resp and resp.get("status") == "COMPLETED":
            self.node.economy.debit(reward, f"Quest {q.quest_id} to {peer_id}")
            q.status = "completed"; q.assignee = peer_id; q.completed_at = now_iso()
            self.node.journal.append("quest.delegated.done",
                                     {"quest_id": q.quest_id, "peer": peer_id,
                                      "result": resp.get("result", "")[:500]})
            return q, resp.get("result", "")
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

@dataclass
class Wallet:
    balance: float = 0.0; lifetime_received: float = 0.0; lifetime_spent: float = 0.0


class Economy:
    def __init__(self, path, journal):
        self.path = path; self.journal = journal; self.lock = threading.RLock()
        self.wallet = Wallet(); self.last_food = None; self.escrow = {}; self._load()

    def _load(self):
        if not self.path.exists(): return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8")); w = data.get("wallet", {})
            self.wallet = Wallet(float(w.get("balance", 0)),
                                 float(w.get("lifetime_received", 0)),
                                 float(w.get("lifetime_spent", 0)))
            self.last_food = data.get("last_food_allocation"); self.escrow = data.get("escrow", {})
        except Exception: pass

    def _save(self):
        atomic_write(self.path, json.dumps({
            "wallet": asdict(self.wallet),
            "last_food_allocation": self.last_food,
            "currency": CURRENCY}, ensure_ascii=False, indent=2))

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
        self.lock = threading.RLock(); self.values = dict(self.DEFAULTS)

    def allow(self, cap):
        with self.lock:
            if cap not in self.values: raise KeyError(cap)
            self.values[cap] = True

    def deny(self, cap):
        with self.lock:
            if cap not in self.values: raise KeyError(cap)
            self.values[cap] = False

    def check(self, cap):
        with self.lock: return bool(self.values.get(cap, False))

    def snapshot(self):
        with self.lock: return dict(self.values)


# ============================================================
# CONTEXT
# ============================================================

class ContextBus:
    def __init__(self):
        self.lock = threading.RLock(); self.data = {}

    def update(self, **kwargs):
        with self.lock: self.data.update(kwargs)
        return self.data

    def get(self):
        with self.lock: return dict(self.data) if self.data else None


# ============================================================
# SYMBIONT
# ============================================================

class Symbiont:
    def __init__(self, root=ROOT_DIR):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.journal = EventJournal(self.root / "events.log")
        self.identity = Identity(self.root / "identity.json")
        self.profile = AgentProfile(self.root / "agent.json")
        self.devices = DeviceRegistry(self.root / "devices.json", self.identity.id())
        self.state = CognitiveState(self.root / "cognitive_state.json")
        self.bodies = Bodies(self.root / "bodies.json")
        self.memory = MemoryVault(self.root / "memory.sqlite3", self.journal)

        # Memory V2: отдельный слой ассоциаций/рефлексии.
        # MemoryVault остаётся источником истины.
        # Shadow mode не меняет существующее поведение Core.
        self.memory_v2 = MemoryV2Runtime(
            self.memory,
            enabled=None,
            shadow=True,
        )
        self.context = ContextBus()
        self.learning = LearningPolicy()
        self.learning_conflict = None
        self.pattern_learning = ConversationalPatternLearner(
            self.learning
        )
        self.consistency = KnowledgeConsistency(self.memory)
        self.mind = CognitiveEngine(self.memory, self.context, self.journal)
        self.mind.profile = self.profile
        self.mind.state = self.state
        self.night_worker = NightWorker(self.memory, self.mind, self.journal)
        self.listener = AmbientListener(
            self.mind,
            self.memory,
            self.journal,
            self.learning,
        )
        self.economy = Economy(self.root / "state.json", self.journal)
        self.permissions = PermissionGate()
        self.peers = PeerDirectory()
        self.quests = QuestBoard(self)
        self.p2p = P2PNetwork(self)
        self.tools = ToolRegistry(self)
        self.mind.connect_tools(self.tools)
        self.sync_engine = MemorySyncEngine(self)
        self.llm_provider = None
        self._load_llm_config()
        self.started_at = now_iso()
        self.journal.append("symbiont.initialized",
                            {"version": CORE_VERSION, "id": self.identity.id()})
        if self.identity.recovery_phrase:
            print("\n" + "!" * 60)
            print("  ЗАПИШИ RECOVERY PHRASE (больше не покажется):")
            print(f"  {self.identity.recovery_phrase}")



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

    def observe_ambient_pattern(self, text):
        """
        Analyze ambient speech for repeated meaningful patterns.

        This never turns ambient speech directly into owner knowledge.
        """
        return self.pattern_learning.observe(
            text,
            source=LearningSource.UNKNOWN,
        )

    def confirm_learning_candidate(self, candidate_text=None):
        """
        Promote a learning candidate to owner knowledge.

        Before saving, compare it with existing owner knowledge.
        Conflicts require explicit owner resolution.
        """

        candidate = self.pattern_learning.confirm(candidate_text)

        if candidate is None:
            return None

        consistency = self.consistency.inspect(
            candidate["text"]
        )

        if consistency["status"] == "conflict":
            # Do not save yet.
            self.learning_conflict = {
                "candidate": candidate,
                "consistency": consistency,
            }

            # Put candidate back into a confirmation state.
            with self.pattern_learning.lock:
                normalized = self.pattern_learning._normalize(
                    candidate["text"]
                )

                existing = self.pattern_learning.candidates.get(
                    normalized
                )

                if existing is not None:
                    existing.status = "needs_resolution"

            self.journal.append(
                "learning.conflict",
                {
                    "candidate": candidate["text"],
                    "related": consistency["related"],
                },
            )

            return {
                "status": "conflict",
                "question": consistency["question"],
                "candidate": candidate,
                "related": consistency["related"],
            }

        metadata = {
            "learning_source": LearningSource.OWNER,
            "learning_allowed": True,
            "learning_confidence": 1.0,
            "learning_origin": "ambient_pattern_confirmation",
            "pattern_confidence": candidate["confidence"],
            "pattern_observations": candidate["observations"],
            "pattern_evidence": candidate["evidence"],
        }

        memory_id = self.remember(
            candidate["text"],
            kind="learned_pattern",
            importance=8,
            source=LearningSource.OWNER,
            metadata=metadata,
        )

        self.journal.append(
            "learning.confirmed",
            {
                "memory_id": memory_id,
                "text": candidate["text"],
                "consistency": consistency["status"],
            },
        )

        return {
            "status": "confirmed",
            "memory_id": memory_id,
            "candidate": candidate,
            "consistency": consistency,
        }

    def resolve_learning_conflict(self, use_new=True):
        """
        Resolve the latest knowledge conflict.

        use_new=True:
            keep the new knowledge and archive the old conflicting
            knowledge logically through metadata.

        use_new=False:
            reject the new candidate.
        """

        conflict = self.learning_conflict

        if not conflict:
            return {
                "status": "none",
                "message": "Нет конфликта знаний.",
            }

        candidate = conflict["candidate"]
        related = conflict["consistency"]["related"]

        if not use_new:
            self.pattern_learning.reject(candidate["text"])
            self.learning_conflict = None

            self.journal.append(
                "learning.conflict_rejected",
                {
                    "candidate": candidate["text"],
                },
            )

            return {
                "status": "rejected",
                "candidate": candidate,
            }

        metadata = {
            "learning_source": LearningSource.OWNER,
            "learning_allowed": True,
            "learning_confidence": 1.0,
            "learning_origin": "conflict_resolution",
            "supersedes": [
                item["memory_id"]
                for item in related
                if item.get("conflict")
            ],
        }

        memory_id = self.remember(
            candidate["text"],
            kind="learned_pattern",
            importance=9,
            source=LearningSource.OWNER,
            metadata=metadata,
        )

        self.learning_conflict = None

        self.journal.append(
            "learning.conflict_resolved",
            {
                "memory_id": memory_id,
                "candidate": candidate["text"],
                "superseded": metadata["supersedes"],
            },
        )

        return {
            "status": "updated",
            "memory_id": memory_id,
            "candidate": candidate,
            "superseded": metadata["supersedes"],
        }


    def reject_learning_candidate(self, candidate_text=None):
        return self.pattern_learning.reject(candidate_text)

    def remember(
        self,
        text,
        kind="general",
        importance=5,
        tags=None,
        source="human",
        metadata=None,
    ):
        return self.memory.remember(
            text=text,
            kind=kind,
            importance=importance,
            tags=tags,
            source=source,
            metadata=metadata,
        )

    def status(self):
        valid, events = self.journal.verify()
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
            "economy": self.economy.snapshot(),
            "journal": {"valid": valid, "events": events},
            "llm": self.llm_status(),
            "listening": self.listener.is_active(),
            "started_at": self.started_at,
        }

    def close(self):
        self.listener.stop(); self.p2p.stop()
        self.journal.append("symbiont.shutdown", {"id": self.identity.id()})
        self.memory.close()


# ============================================================
# KNOWLEDGE CONSISTENCY
# ============================================================

class KnowledgeConsistency:
    """
    Checks new owner knowledge against existing memory.

    Important:
    - similar knowledge is not automatically duplicated
    - conflicting knowledge is never silently overwritten
    - the owner decides which knowledge should become current
    """

    VERSION = "CONSISTENCY/1"

    POSITIVE_MARKERS = (
        "люблю",
        "нравится",
        "предпочитаю",
        "удобнее",
        "любимый",
        "любимая",
        "любимое",
        "хочу",
        "нравилось",
    )

    NEGATIVE_MARKERS = (
        "не люблю",
        "не нравится",
        "не предпочитаю",
        "неудобно",
        "ненавижу",
        "не хочу",
    )

    CONTRAST_PAIRS = (
        ("ночью", "утром"),
        ("утром", "ночью"),
        ("вечером", "утром"),
        ("утром", "вечером"),
        ("дома", "офисе"),
        ("офисе", "дома"),
        ("часто", "редко"),
        ("всегда", "никогда"),
        ("люблю", "не люблю"),
        ("нравится", "не нравится"),
        ("удобно", "неудобно"),
    )

    def __init__(self, memory):
        self.memory = memory
        self.lock = threading.RLock()

    def _normalize(self, text):
        text = str(text or "").lower().strip()

        for a, b in {
            "ё": "е",
            ",": " ",
            ".": " ",
            "!": " ",
            "?": " ",
            ":": " ",
            ";": " ",
            "(": " ",
            ")": " ",
            "«": " ",
            "»": " ",
            '"': " ",
            "'": " ",
            "—": " ",
            "-": " ",
        }.items():
            text = text.replace(a, b)

        return " ".join(text.split())

    def _tokens(self, text):
        stop = {
            "я", "ты", "он", "она", "мы", "вы",
            "мне", "тебе", "это", "что", "как",
            "и", "а", "но", "же", "в", "во",
            "на", "по", "с", "со", "к", "у",
            "из", "для", "мне", "тебе",
        }

        result = set()

        for word in self._normalize(text).split():
            if len(word) < 3 or word in stop:
                continue

            for suffix in (
                "ами", "ями", "ого", "ему", "ому",
                "ов", "ев", "ах", "ях",
                "ы", "и", "а", "я", "е", "о", "у", "ю", "ь",
            ):
                if len(word) > 5 and word.endswith(suffix):
                    word = word[:-len(suffix)]
                    break

            result.add(word)

        return result

    def _similarity(self, a, b):
        ta = self._tokens(a)
        tb = self._tokens(b)

        if not ta or not tb:
            return 0.0

        return len(ta & tb) / max(1, len(ta | tb))

    def _polarity(self, text):
        normalized = self._normalize(text)

        negative = any(
            marker in normalized
            for marker in self.NEGATIVE_MARKERS
        )

        positive = any(
            marker in normalized
            for marker in self.POSITIVE_MARKERS
        )

        if negative and not positive:
            return "negative"

        if positive and not negative:
            return "positive"

        return "neutral"

    def _contrast(self, a, b):
        a = self._normalize(a)
        b = self._normalize(b)

        for left, right in self.CONTRAST_PAIRS:
            if left in a and right in b:
                return True

        for left, right in self.CONTRAST_PAIRS:
            if right in a and left in b:
                return True

        pa = self._polarity(a)
        pb = self._polarity(b)

        if (
            pa != "neutral"
            and pb != "neutral"
            and pa != pb
        ):
            # Only treat opposite polarity as a conflict when
            # the statements are already reasonably similar.
            if self._similarity(a, b) >= 0.20:
                return True

        return False

    def inspect(self, candidate_text):
        """
        Search existing memory for knowledge related to candidate.

        Returns:
            {
                status: "new" | "similar" | "conflict",
                related: [...],
                question: ...
            }
        """

        candidate_text = str(candidate_text or "").strip()

        if not candidate_text:
            return {
                "status": "new",
                "related": [],
                "question": None,
            }

        try:
            memories = self.memory.search(
                candidate_text,
                limit=20,
            )
        except Exception:
            memories = []

        related = []

        for memory in memories:
            # Only compare durable owner knowledge.
            source = str(getattr(memory, "source", "") or "")

            metadata = getattr(memory, "metadata", {}) or {}

            learning_source = metadata.get(
                "learning_source",
                source,
            )

            if learning_source != LearningSource.OWNER:
                continue

            similarity = self._similarity(
                candidate_text,
                memory.text,
            )

            if similarity < 0.20:
                continue

            conflict = self._contrast(
                candidate_text,
                memory.text,
            )

            related.append({
                "memory_id": memory.memory_id,
                "text": memory.text,
                "similarity": round(similarity, 3),
                "conflict": conflict,
                "importance": memory.importance,
            })

        if not related:
            return {
                "status": "new",
                "related": [],
                "question": None,
            }

        conflicts = [
            item for item in related
            if item["conflict"]
        ]

        if conflicts:
            old = conflicts[0]

            return {
                "status": "conflict",
                "related": related,
                "question": (
                    "У меня уже есть другое знание: "
                    f"«{old['text']}». "
                    f"Сейчас я услышал: «{candidate_text}». "
                    "Это изменение твоих предпочтений? "
                    "Обновить старое знание?"
                ),
            }

        return {
            "status": "similar",
            "related": related,
            "question": None,
        }

    def status(self):
        return {
            "version": self.VERSION,
        }




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

        if cmd == "say":
            if not arg: print("Usage: say <text>"); return True
            mem_id = self.sym.remember(arg, kind="dialog", importance=5, source=LearningSource.OWNER, metadata={"learning_source": LearningSource.OWNER, "learning_allowed": True, "learning_confidence": 1.0})
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

        if cmd in ("learning pending", "обучение", "обучение кандидаты"):
            pending = self.sym.pattern_learning.pending()

            if not pending:
                print("Нет кандидатов на подтверждение.")
            else:
                print("Кандидаты на подтверждение:")
                for i, item in enumerate(pending, 1):
                    print(
                        f"{i}. {item['text']} "
                        f"(confidence={item['confidence']}, "
                        f"observations={item['observations']})"
                    )

            return

        if cmd in ("learning conflict", "обучение конфликт"):
            conflict = self.sym.learning_conflict

            if not conflict:
                print("Нет ожидающего конфликта знаний.")
            else:
                print()
                print(conflict["consistency"]["question"])
                print()
                print("  learning update — принять новое знание")
                print("  learning keep — оставить старое")
                print()

            return

        if cmd in ("learning update", "обучение обновить"):
            result = self.sym.resolve_learning_conflict(True)

            if result["status"] == "updated":
                print(
                    "Знание обновлено. "
                    f"MEMORY={result['memory_id']}"
                )
            else:
                print(result.get("message", result["status"]))

            return

        if cmd in ("learning keep", "обучение оставить"):
            result = self.sym.resolve_learning_conflict(False)

            if result["status"] == "rejected":
                print("Новое знание отклонено. Старое сохранено.")
            else:
                print(result.get("message", result["status"]))

            return

        if cmd in ("learning yes", "обучение да", "запомни"):
            result = self.sym.confirm_learning_candidate()

            if result is None:
                print("Нет кандидата, ожидающего подтверждения.")
            else:
                print(
                    "Запомнил как знание владельца. "
                    f"MEMORY={result['memory_id']}"
                )

            return

        if cmd in ("learning no", "обучение нет", "не запоминай"):
            result = self.sym.reject_learning_candidate()

            if result is None:
                print("Нет кандидата, ожидающего подтверждения.")
            else:
                print("Кандидат отклонён и не стал знанием владельца.")

            return

        if cmd in ("listen", "услышь"):
            if BODY is None: print("Тело не подключено."); return True
            text = BODY.listen()
            if text:
                print(f"Услышано: {text}")
                self.sym.remember(text, kind="dialog", importance=5, source=LearningSource.UNKNOWN, metadata={"learning_source": LearningSource.UNKNOWN, "learning_allowed": False, "learning_confidence": 0.0})
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
        mem_id = self.sym.remember(raw, kind="dialog", importance=5, source=LearningSource.OWNER, metadata={"learning_source": LearningSource.OWNER, "learning_allowed": True, "learning_confidence": 1.0})
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
        sym = Symbiont(Path(temporary))
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
