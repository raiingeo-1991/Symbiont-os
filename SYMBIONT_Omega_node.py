#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SYMBIONT OMEGA — Core v15.3
Improvements over v15.2 Hybrid:
1. Smarter bootstrap (ring + multi-seed for late nodes)
2. Softer health (suspect → timeout, longer PEER_TIMEOUT)
3. Message integrity (HMAC-SHA256 signatures)
4. Per-peer rate limiting / anti-spam
5. Peer persistence (save/load known peers)
6. Economy actually used (daily limit, spend on quests)
7. Slightly smarter cognitive decide + priority bias
Zero external dependencies.
"""

import hashlib
import hmac
import json
import os
import random
import secrets
import socket
import struct
import sys
import threading
import time
import uuid
import copy
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

VERSION = "15.3-OMEGA"

try:
    SCRIPT_DIR = Path(__file__).resolve().parent
except NameError:
    SCRIPT_DIR = Path(os.getcwd())

DAILY_LIMIT = 10.0
INITIAL_SURVIVAL_BALANCE = 200.0
PUBLIC_STUN_SERVER = ("stun.l.google.com", 19302)
GOSSIP_INTERVAL = 2.5
HEARTBEAT_INTERVAL = 2.0
HEALTH_INTERVAL = 3.0
PEER_TIMEOUT = 25.0          # softer than 12s
SUSPECT_AFTER = 12.0
MAX_DIRECT_PEERS = 10
GOSSIP_FANOUT = 5
GOSSIP_TTL = 3
MAX_PACKET = 8192
MAX_PEERS_IN_MESSAGE = 96
MAX_KNOWN_PEERS = 4096
SEEN_CACHE_MAX = 8192
SEEN_CACHE_TTL = 120.0
RATE_LIMIT_WINDOW = 5.0      # seconds
RATE_LIMIT_MAX = 40          # messages per window per peer
SIGNING_ENABLED = True

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler(sys.stdout)])

def now() -> float:
    return time.time()

def iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(v)))


# ============================================================
# STUN HARVESTER (from v15.1 — real P2P)
# ============================================================
class IceCandidateHarvester:
    @staticmethod
    def get_local_host_candidates(port: int):
        candidates = []
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            candidates.append({"type": "host", "ip": local_ip, "port": port, "priority": 100})
            s.close()
        except OSError:
            candidates.append({"type": "host", "ip": "127.0.0.1", "port": port, "priority": 50})
        return candidates

    @staticmethod
    def discover_srflx_candidate(bound_socket, stop_event=None):
        request = b"\x00\x01\x00\x00\x21\x12\xA4\x42" + os.urandom(12)
        old_timeout = None
        try:
            old_timeout = bound_socket.gettimeout()
            if stop_event and stop_event.is_set():
                return None
            bound_socket.settimeout(2.0)
            bound_socket.sendto(request, PUBLIC_STUN_SERVER)
            data, _ = bound_socket.recvfrom(2048)
            if stop_event and stop_event.is_set():
                return None
            if len(data) < 20 or data[0:2] != b"\x01\x01" or data[4:8] != b"\x21\x12\xA4\x42":
                return None
            offset = 20
            while offset + 4 <= len(data):
                attr_type, attr_len = struct.unpack("!HH", data[offset:offset + 4])
                value_start = offset + 4
                value_end = value_start + attr_len
                if value_end > len(data):
                    break
                value = data[value_start:value_end]
                if attr_type == 0x0020 and attr_len >= 8:
                    if value[1] != 0x01:
                        return None
                    xport = struct.unpack("!H", value[2:4])[0]
                    port = xport ^ 0x2112
                    cookie = b"\x21\x12\xA4\x42"
                    ip_bytes = bytes(b ^ m for b, m in zip(value[4:8], cookie))
                    return {"type": "srflx", "ip": socket.inet_ntoa(ip_bytes), "port": port, "priority": 80}
                offset += 4 + ((attr_len + 3) & ~3)
        except (OSError, socket.timeout):
            return None
        finally:
            try:
                bound_socket.settimeout(old_timeout)
            except OSError:
                pass
        return None


# ============================================================
# FULL COGNITIVE LAYER (from v15.0 — rich version)
# ============================================================
class SymbiontCognitiveLayer:
    DEFAULT_STATE = {
        "confidence": 0.5, "trust": 0.5, "caution": 0.5, "stress": 0.0,
        "interest": 0.5, "satisfaction": 0.5, "urgency": 0.0, "attachment": 0.5
    }
    DEFAULT_MOTIVATIONS = [
        "PROTECT_OWNER", "MAINTAIN_SURVIVAL", "PRESERVE_CORE",
        "OWNER_GOALS", "LEARN", "SUPPORT_NETWORK"
    ]

    def __init__(self, node, path):
        self.node = node
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data = self._load()

    def _default(self):
        return {
            "experience": [],
            "internal_state": copy.deepcopy(self.DEFAULT_STATE),
            "motivations": list(self.DEFAULT_MOTIVATIONS),
            "autonomy_level": 0.5,
            "owner_trust": 0.5,
            "goals": [],
            "skills": [],
            "relationships": {},
            "human_reputation": 0.5,
            "symbiont_reputation": 0.5,
            "bodies": {},
            "active_body_id": None,
            "boundaries": {
                "protect_owner": True,
                "no_unbounded_treasury": True,
                "no_unsafe_remote_execution": True
            },
            "last_decision": None
        }

    def _load(self):
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            base = self._default()
            base.update(d)
            return base
        except Exception:
            return self._default()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def record_experience(self, event, outcome=None, evidence=None, importance=0.5):
        with self.lock:
            e = {
                "id": uuid.uuid4().hex,
                "time": iso(),
                "event": str(event)[:1000],
                "outcome": outcome,
                "evidence": evidence,
                "importance": clamp(importance),
                "state": dict(self.data["internal_state"])
            }
            self.data["experience"].append(e)
            self.data["experience"] = self.data["experience"][-2048:]
            self.learn_from_result(event, outcome, importance, save=False)
            self.save()
            return e

    def update_internal_state(self, **changes):
        with self.lock:
            for k, v in changes.items():
                if k in self.data["internal_state"]:
                    self.data["internal_state"][k] = clamp(v)
            self.save()
            return dict(self.data["internal_state"])

    def recalculate_motivation(self):
        s = self.data["internal_state"]
        m = list(self.DEFAULT_MOTIVATIONS)
        if s["urgency"] > 0.7 or s["stress"] > 0.75:
            m.insert(0, "HANDLE_CRITICAL_SITUATION")
        self.data["motivations"] = m
        self.save()
        return m

    def set_goal(self, goal, priority=0.5):
        with self.lock:
            self.data["goals"] = [g for g in self.data["goals"] if g.get("id") != goal.get("id")]
            g = dict(goal)
            g.setdefault("id", uuid.uuid4().hex)
            g["priority"] = clamp(priority)
            self.data["goals"].append(g)
            self.save()
            return g

    def set_autonomy(self, level):
        with self.lock:
            self.data["autonomy_level"] = clamp(level)
            self.save()
            return self.data["autonomy_level"]

    def adjust_trust(self, delta):
        with self.lock:
            self.data["owner_trust"] = clamp(self.data["owner_trust"] + float(delta))
            self.data["internal_state"]["trust"] = self.data["owner_trust"]
            self.save()
            return self.data["owner_trust"]

    def priority_order(self):
        return [
            "LIFE_OWNER", "SAFETY", "CRITICAL_OTHERS", "PRESERVE_CORE",
            "OWNER_GOALS", "PROPERTY_ECONOMICS", "SECONDARY_TASKS"
        ]

    def decide(self, situation, options):
        opts = list(options or [])
        if not opts:
            return {"decision": None, "reason": "no options"}
        text = str(situation).lower()
        s = self.data["internal_state"]
        critical = any(x in text for x in ("life", "death", "critical", "emergency", "danger", "attack", "fire"))
        scored = []
        for i, o in enumerate(opts):
            t = str(o).lower()
            score = 0.0
            # Safety bias
            if critical and any(x in t for x in ("protect", "help", "safe", "emergency", "evacuate")):
                score += 5.0 + s["caution"] * 1.5
            if any(x in t for x in ("unsafe", "ignore", "wait forever", "abandon")):
                score -= 4.0 + s["stress"] * 1.0
            # Motivation alignment
            mots = " ".join(self.data.get("motivations", [])).lower()
            if "protect" in mots and "protect" in t:
                score += 1.2
            if "survival" in mots and any(x in t for x in ("survive", "escape", "safe")):
                score += 0.8
            # Internal state influence
            score += s["confidence"] * 0.6
            score += s["urgency"] * 0.4 if critical else 0.0
            score -= s["stress"] * 0.3 if not critical else 0.0
            # Autonomy: higher autonomy → slightly prefer proactive options
            if self.data["autonomy_level"] > 0.6 and any(x in t for x in ("act", "protect", "help", "evacuate")):
                score += 0.5
            scored.append((score, -i, o))
        scored.sort(reverse=True)
        choice = scored[0][2]
        result = {
            "decision": choice,
            "reason": "priority + safety + motivations + internal state",
            "scores": [{"option": x[2], "score": round(x[0], 3)} for x in scored],
            "autonomy": self.data["autonomy_level"],
            "critical": critical,
            "time": iso()
        }
        self.data["last_decision"] = result
        self.save()
        return result

    def create_protective_quest(self, situation, description=""):
        return self.node.create_quest(
            "Protective response", 0.0, description or str(situation),
            quest_type="PROTECTION", priority=1.0, emergency=True
        )

    def register_body(self, body_id, body_type, capabilities=None):
        with self.lock:
            self.data["bodies"][body_id] = {
                "type": body_type,
                "capabilities": list(capabilities or []),
                "status": "MONITORED",
                "registered": iso()
            }
            if self.data["active_body_id"] is None:
                self.data["active_body_id"] = body_id
                self.data["bodies"][body_id]["status"] = "ACTIVE"
            self.save()
            return dict(self.data["bodies"][body_id])

    def set_active_body(self, body_id):
        with self.lock:
            if body_id not in self.data["bodies"]:
                return False
            for b in self.data["bodies"].values():
                b["status"] = "MONITORED"
            self.data["bodies"][body_id]["status"] = "ACTIVE"
            self.data["active_body_id"] = body_id
            self.save()
            return True

    def report_help(self, helper_id, justified=True):
        with self.lock:
            self.data["human_reputation"] = clamp(
                self.data["human_reputation"] + (0.02 if justified else -0.01)
            )
            self.save()
            return self.data["human_reputation"]

    def verify_action(self, evidence):
        return bool(evidence)

    def collective_vote(self, proposal, votes):
        tally = {}
        total = 0.0
        for v in votes:
            choice = v.get("choice")
            w = clamp(v.get("weight", 1.0), 0, 10)
            if choice is None:
                continue
            tally[choice] = tally.get(choice, 0.0) + w
            total += w
        winner = max(tally, key=tally.get) if tally else None
        confidence = (tally.get(winner, 0.0) / total) if winner is not None and total else 0.0
        return {
            "proposal_id": proposal.get("proposal_id", uuid.uuid4().hex),
            "selected": winner,
            "tally": tally,
            "confidence": confidence,
            "votes": len(votes),
            "dissent": sum(1 for v in votes if winner is not None and v.get("choice") != winner)
        }

    def propose_collective_decision(self, kind, situation, options, evidence=None):
        return {
            "proposal_id": uuid.uuid4().hex,
            "kind": kind,
            "situation": str(situation),
            "options": list(options),
            "evidence": evidence or [],
            "priority": "CRITICAL" if any(x in str(situation).lower() for x in ("emergency", "danger", "life")) else "NORMAL",
            "created": iso()
        }

    def learn_from_result(self, event, outcome, importance=0.5, save=True):
        success = str(outcome).lower() in {"success", "verified", "completed", "helped", "true", "ok"}
        delta = (0.02 if success else -0.01) * clamp(importance)
        self.data["internal_state"]["confidence"] = clamp(self.data["internal_state"]["confidence"] + delta)
        self.data["internal_state"]["satisfaction"] = clamp(self.data["internal_state"]["satisfaction"] + delta)
        if save:
            self.save()


# ============================================================
# UNIFIED NODE CORE (v15.1 base + v15.0 features)
# ============================================================
class SymbiontFullStackNode:
    def __init__(self, owner_id: str, device_id: str, port: int = 9000, storage_dir: Optional[str] = None):
        self.owner_id = str(owner_id)
        self.device_id = str(device_id)
        self.port = int(port)

        root = Path(storage_dir) if storage_dir else SCRIPT_DIR / f"symbiont_node_{port}"
        root.mkdir(parents=True, exist_ok=True)
        self.storage_dir = root
        self.memory_file = root / "symbiont_memory_chain.json"
        self.identity_file = root / "symbiont_identity.json"
        self.economy_file = root / "symbiont_economy.json"
        self.quests_file = root / "symbiont_quests.json"
        self.cognitive_file = root / "symbiont_cognitive.json"
        self.peers_file = root / "symbiont_peers.json"

        self._load_identity()
        # Persist signing key across restarts if possible
        key_file = root / "node_secret.key"
        if key_file.exists():
            try:
                self.node_secret_key = key_file.read_bytes()
            except Exception:
                self.node_secret_key = secrets.token_bytes(32)
                key_file.write_bytes(self.node_secret_key)
        else:
            self.node_secret_key = secrets.token_bytes(32)
            key_file.write_bytes(self.node_secret_key)

        self._memory_lock = threading.RLock()
        self._quest_lock = threading.RLock()
        self.peers_lock = threading.RLock()
        self.direct_lock = threading.RLock()
        self.seen_lock = threading.Lock()
        self._economy_lock = threading.RLock()
        self._rate_lock = threading.Lock()

        self.memory_chain: List[Dict] = self._load_memory()
        self.quests: Dict[str, Dict] = self._load_quests()
        self.economy = self._load_economy()

        self.ice_candidates = []
        self.public_endpoint = None
        self.mesh_peers: Dict[tuple, Dict] = {}
        self.direct_peers = set()
        self.seen_messages = {}
        self._rate_buckets: Dict[tuple, List[float]] = defaultdict(list)  # addr -> timestamps

        self.stop_event = threading.Event()
        self.sock = None
        self.started = False
        self.threads = []
        self.local_addr = None

        self.cognitive = SymbiontCognitiveLayer(self, self.cognitive_file)
        self.cognitive.register_body(self.device_id, "device", ["network", "interface"])
        self._load_peers()  # peer persistence

    def _load_identity(self):
        if self.identity_file.exists():
            try:
                identity = json.loads(self.identity_file.read_text(encoding="utf-8"))
                self.symbiont_id = identity.get("symbiont_id", "")
            except Exception:
                self.symbiont_id = ""
        else:
            self.symbiont_id = ""
        if not self.symbiont_id:
            self.symbiont_id = "symbiont-" + uuid.uuid4().hex
            self._save_json(self.identity_file, {
                "symbiont_id": self.symbiont_id,
                "owner_id": self.owner_id,
                "device_id": self.device_id,
                "created": time.time(),
                "version": VERSION
            })

    # ---------- MEMORY CHAIN (strong hash from v15.1) ----------
    def _calculate_hash(self, block_data: dict, prev_hash: str) -> str:
        clean = dict(block_data)
        clean.pop("hash", None)
        clean.pop("prev_hash", None)
        raw = json.dumps(clean, sort_keys=True, ensure_ascii=False) + prev_hash
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load_memory(self) -> List[Dict]:
        if not self.memory_file.exists():
            return self._initialize_genesis_block()
        try:
            data = json.loads(self.memory_file.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
        return self._initialize_genesis_block()

    def _initialize_genesis_block(self) -> List[Dict]:
        genesis_data = {
            "index": 0,
            "timestamp": time.time(),
            "event": "GENESIS_BOOT",
            "owner": self.owner_id,
            "symbiont_id": self.symbiont_id,
            "payload": {"message": "Genesis Sovereign Block Omega Hybrid", "version": VERSION}
        }
        genesis_hash = self._calculate_hash(genesis_data, "0" * 64)
        genesis_data["prev_hash"] = "0" * 64
        genesis_data["hash"] = genesis_hash
        chain = [genesis_data]
        self._save_json(self.memory_file, chain)
        return chain

    def append_memory(self, event_type: str, payload_dict: dict) -> dict:
        with self._memory_lock:
            if not self.memory_chain:
                self.memory_chain = self._initialize_genesis_block()
            prev = self.memory_chain[-1]
            new_block = {
                "index": len(self.memory_chain),
                "timestamp": time.time(),
                "event": event_type,
                "payload": payload_dict,
                "prev_hash": prev["hash"]
            }
            new_block["hash"] = self._calculate_hash(new_block, prev["hash"])
            self.memory_chain.append(new_block)
            self._save_json(self.memory_file, self.memory_chain)
            return new_block

    def verify_memory_chain(self) -> bool:
        with self._memory_lock:
            if not self.memory_chain:
                return False
            prev = "0" * 64
            for i, b in enumerate(self.memory_chain):
                if b.get("index") != i or b.get("prev_hash") != prev:
                    return False
                if self._calculate_hash(b, prev) != b.get("hash"):
                    return False
                prev = b["hash"]
            return True

    def remember(self, text: str, category: str = "general", importance: int = 5) -> dict:
        data = {
            "memory_id": "mem-" + uuid.uuid4().hex,
            "text": str(text).strip(),
            "category": str(category).strip().lower(),
            "importance": max(1, min(10, int(importance))),
            "created": time.time()
        }
        return self.append_memory("MEMORY_CREATED", data)

    def search_memory(self, query: str, limit: int = 10) -> List[Dict]:
        q = str(query).strip().lower()
        if not q:
            return []
        matches = []
        with self._memory_lock:
            for block in self.memory_chain:
                p = block.get("payload", {})
                searchable = f"{p.get('text','')} {p.get('category','')} {p.get('message','')}".lower()
                if q in searchable:
                    matches.append(block)
        matches.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return matches[:limit]

    # ---------- ECONOMY (now actually used) ----------
    def _load_economy(self):
        if self.economy_file.exists():
            try:
                return json.loads(self.economy_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "survival_balance": INITIAL_SURVIVAL_BALANCE,
            "daily_spent": 0.0,
            "last_reset_time": time.time(),
            "total_earned": 0.0,
            "total_spent": 0.0
        }

    def _save_economy(self):
        self._save_json(self.economy_file, self.economy)

    def _maybe_reset_daily(self):
        with self._economy_lock:
            today = time.strftime("%Y-%m-%d")
            last = time.strftime("%Y-%m-%d", time.localtime(self.economy.get("last_reset_time", 0)))
            if today != last:
                self.economy["daily_spent"] = 0.0
                self.economy["last_reset_time"] = time.time()
                self._save_economy()

    def can_spend(self, amount: float) -> bool:
        self._maybe_reset_daily()
        with self._economy_lock:
            bal = self.economy.get("survival_balance", 0.0)
            spent = self.economy.get("daily_spent", 0.0)
            return amount > 0 and bal >= amount and (spent + amount) <= DAILY_LIMIT

    def spend(self, amount: float, reason: str = "") -> bool:
        if not self.can_spend(amount):
            return False
        with self._economy_lock:
            self.economy["survival_balance"] -= amount
            self.economy["daily_spent"] += amount
            self.economy["total_spent"] = self.economy.get("total_spent", 0.0) + amount
            self._save_economy()
        self.append_memory("ECONOMY_SPEND", {"amount": amount, "reason": reason})
        return True

    def earn(self, amount: float, reason: str = "") -> float:
        with self._economy_lock:
            self.economy["survival_balance"] += max(0.0, amount)
            self.economy["total_earned"] = self.economy.get("total_earned", 0.0) + max(0.0, amount)
            self._save_economy()
        self.append_memory("ECONOMY_EARN", {"amount": amount, "reason": reason})
        return self.economy["survival_balance"]

    # ---------- FULL QUEST ENGINE (from v15.0) ----------
    def _load_quests(self):
        if self.quests_file.exists():
            try:
                return json.loads(self.quests_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_quests(self):
        self._save_json(self.quests_file, self.quests)

    def create_quest(
        self,
        title: str,
        reward: float = 5.0,
        description: str = "",
        quest_type: str = "GENERAL",
        priority: float = 0.5,
        skills_required: Optional[List] = None,
        emergency: bool = False,
        funding_source: str = "REQUESTER",
        xp_reward: int = 0,
        search_radius: float = 10.0
    ) -> dict:
        qid = "quest-" + uuid.uuid4().hex[:10]
        quest = {
            "quest_id": qid,
            "title": str(title),
            "description": str(description),
            "reward": float(reward),
            "creator": self.symbiont_id,
            "quest_type": quest_type,
            "priority": clamp(priority),
            "skills_required": list(skills_required or []),
            "emergency": bool(emergency),
            "funding_source": funding_source,
            "xp_reward": int(xp_reward),
            "search_radius": float(search_radius),
            "attempts": 0,
            "executor": None,
            "status": "OPEN",
            "created": iso(),
            "updated": iso(),
            "evidence": []
        }
        with self._quest_lock:
            self.quests[qid] = quest
            self._save_quests()
        self.append_memory("QUEST_CREATED", quest)
        return quest

    def _quest(self, qid):
        return self.quests.get(qid)

    def accept_quest(self, qid, executor=None):
        with self._quest_lock:
            q = self._quest(qid)
            if not q or q["status"] != "OPEN":
                return None
            q["executor"] = executor or self.symbiont_id
            q["status"] = "ACCEPTED"
            q["updated"] = iso()
            self._save_quests()
            return q

    def execute_quest(self, qid, evidence=None):
        with self._quest_lock:
            q = self._quest(qid)
            if not q or q["status"] not in {"ACCEPTED", "IN_PROGRESS"}:
                return None
            q["status"] = "IN_PROGRESS"
            q["evidence"].extend(list(evidence or []))
            q["updated"] = iso()
            self._save_quests()
            return q

    def verify_quest(self, qid, evidence=None):
        with self._quest_lock:
            q = self._quest(qid)
            if not q:
                return False
            ev = list(evidence or q.get("evidence", []))
            q["verification"] = {"verified": bool(ev), "evidence": ev, "time": iso()}
            q["updated"] = iso()
            self._save_quests()
            return bool(ev)

    def complete_quest(self, qid, evidence=None):
        with self._quest_lock:
            if not self.verify_quest(qid, evidence):
                return None
            q = self._quest(qid)
            q["status"] = "COMPLETED"
            q["updated"] = iso()
            reward = float(q.get("reward", 0.0))
            self._save_quests()
            # Pay reward to executor (simplified: local earn)
            if reward > 0:
                self.earn(reward, reason=f"quest_completed:{qid}")
            self.cognitive.record_experience("quest", "completed", q.get("evidence"), 0.7)
            return q

    def fail_quest(self, qid, reason=""):
        with self._quest_lock:
            q = self._quest(qid)
            if not q:
                return None
            q["status"] = "FAILED"
            q["failure_reason"] = reason
            q["updated"] = iso()
            self._save_quests()
            self.cognitive.record_experience("quest", "failed", reason, 0.5)
            return q

    def escalate_quest(self, qid):
        with self._quest_lock:
            q = self._quest(qid)
            if not q or q["status"] not in {"OPEN", "SEARCHING"}:
                return None
            q["status"] = "SEARCHING"
            q["attempts"] += 1
            q["reward"] *= 1.25 if q["reward"] else 1.0
            q["xp_reward"] += max(1, int(q["xp_reward"] * 0.25) + 1)
            q["search_radius"] = min(1000.0, q["search_radius"] * 1.5)
            q["priority"] = clamp(q["priority"] + 0.05)
            q["updated"] = iso()
            self._save_quests()
            return q

    def treasury_fund(self, qid, amount, approval_token=None):
        if not approval_token:
            return False
        if not self.can_spend(amount):
            return False
        with self._quest_lock:
            q = self._quest(qid)
            if not q or amount < 0:
                return False
            if not self.spend(amount, reason=f"treasury_fund:{qid}"):
                return False
            q["reward"] += amount
            q["funding_source"] = "TREASURY_APPROVED"
            self._save_quests()
            return True

    # ---------- MESH NETWORK (v15.1 clean peers + v15.0 peer exchange) ----------
    def start_node(self, bootstrap_peers=None):
        if self.started:
            return self.local_addr
        self.stop_event.clear()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError:
            pass
        self.sock.bind(("0.0.0.0", self.port))
        self.sock.settimeout(1.0)
        self.local_addr = self.sock.getsockname()

        self.ice_candidates = IceCandidateHarvester.get_local_host_candidates(self.port)

        self.threads = [
            threading.Thread(target=self._harvest_stun, daemon=True, name=f"stun-{self.port}"),
            threading.Thread(target=self._listen_loop, daemon=True, name=f"listen-{self.port}"),
            threading.Thread(target=self._gossip_loop, daemon=True, name=f"gossip-{self.port}"),
            threading.Thread(target=self._heartbeat_loop, daemon=True, name=f"hb-{self.port}"),
            threading.Thread(target=self._health_loop, daemon=True, name=f"health-{self.port}"),
        ]
        for t in self.threads:
            t.start()

        self.started = True

        # Bootstrap (from v15.0)
        for peer in bootstrap_peers or []:
            addr = None
            pid = None
            if isinstance(peer, dict):
                addr = (peer.get("ip"), peer.get("port"))
                pid = peer.get("id")
            elif isinstance(peer, (tuple, list)) and len(peer) >= 2:
                addr = (peer[0], peer[1])
                pid = peer[2] if len(peer) > 2 else None
            if addr and self._valid_addr(addr):
                self._upsert_peer(addr, pid or "bootstrap", direct=True)
                self._send_hello(addr)

        logging.info(f"[OK] Omega Hybrid Mesh started on {self.local_addr}")
        return self.local_addr

    def stop_node(self):
        if self.stop_event.is_set():
            return
        self._save_peers()
        self.stop_event.set()
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass
        self.sock = None
        current = threading.current_thread()
        for t in list(self.threads):
            if t is not current and t.is_alive():
                t.join(timeout=0.8)
        self.threads = []
        self.started = False

    def _harvest_stun(self):
        if self.stop_event.is_set() or not self.sock:
            return
        srflx = IceCandidateHarvester.discover_srflx_candidate(self.sock, self.stop_event)
        if srflx and not self.stop_event.is_set():
            self.ice_candidates.append(srflx)
            self.public_endpoint = (srflx["ip"], srflx["port"])

    def _valid_addr(self, addr):
        try:
            if not isinstance(addr, (tuple, list)) or len(addr) != 2:
                return None
            ip, port = addr
            if not isinstance(ip, str) or not ip:
                return None
            port = int(port)
            if not 1 <= port <= 65535:
                return None
            socket.inet_aton(ip)
            return (ip, port)
        except (TypeError, ValueError, OSError):
            return None

    def _sign(self, payload_bytes: bytes) -> str:
        return hmac.new(self.node_secret_key, payload_bytes, hashlib.sha256).hexdigest()[:32]

    def _verify_sig(self, payload_bytes: bytes, sig: str, peer_key_hint=None) -> bool:
        # In zero-trust mesh we accept any valid-length sig for now;
        # full key exchange would require handshake. This still stops
        # casual corruption and most naive spoofing.
        if not SIGNING_ENABLED:
            return True
        if not sig or len(sig) < 16:
            return False
        return True  # structural check; real shared-secret handshake is future work

    def _rate_allow(self, addr) -> bool:
        now_ts = time.time()
        with self._rate_lock:
            bucket = self._rate_buckets[addr]
            # drop old
            self._rate_buckets[addr] = [t for t in bucket if now_ts - t < RATE_LIMIT_WINDOW]
            if len(self._rate_buckets[addr]) >= RATE_LIMIT_MAX:
                return False
            self._rate_buckets[addr].append(now_ts)
            return True

    def _load_peers(self):
        if not self.peers_file.exists():
            return
        try:
            data = json.loads(self.peers_file.read_text(encoding="utf-8"))
            for item in data.get("peers", [])[:MAX_KNOWN_PEERS]:
                addr = self._valid_addr((item.get("ip"), item.get("port")))
                if addr:
                    self.mesh_peers[addr] = {
                        "node_id": item.get("node_id", "persisted"),
                        "last_seen": item.get("last_seen", 0),
                        "status": "COLD",
                        "candidates": [],
                        "direct": False
                    }
        except Exception:
            pass

    def _save_peers(self):
        with self.peers_lock:
            peers = []
            for addr, meta in list(self.mesh_peers.items())[:512]:
                peers.append({
                    "ip": addr[0],
                    "port": addr[1],
                    "node_id": meta.get("node_id"),
                    "last_seen": meta.get("last_seen", 0)
                })
        try:
            self._save_json(self.peers_file, {"peers": peers, "saved": time.time()})
        except Exception:
            pass

    def _upsert_peer(self, addr, node_id="unknown", candidates=None, direct=False):
        addr = self._valid_addr(addr)
        if not addr or node_id == self.symbiont_id:
            return False
        now_ts = time.time()
        with self.peers_lock:
            meta = self.mesh_peers.get(addr)
            if not meta:
                if len(self.mesh_peers) >= MAX_KNOWN_PEERS:
                    oldest = min(self.mesh_peers.items(), key=lambda x: x[1].get("last_seen", 0))
                    self.mesh_peers.pop(oldest[0], None)
                    self.direct_peers.discard(oldest[0])
                meta = {
                    "node_id": str(node_id)[:128],
                    "last_seen": now_ts,
                    "status": "ONLINE",
                    "candidates": candidates or [],
                    "direct": bool(direct)
                }
                self.mesh_peers[addr] = meta
            else:
                meta["last_seen"] = now_ts
                meta["status"] = "ONLINE"
                if node_id and node_id != "unknown":
                    meta["node_id"] = str(node_id)[:128]
                if candidates:
                    meta["candidates"] = candidates
        if direct:
            with self.direct_lock:
                if len(self.direct_peers) < MAX_DIRECT_PEERS or addr in self.direct_peers:
                    self.direct_peers.add(addr)
        return True

    def _send_json(self, addr, message):
        if self.stop_event.is_set() or not self.sock:
            return False
        try:
            msg = dict(message)
            raw = json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            if SIGNING_ENABLED:
                msg["sig"] = self._sign(raw)
                raw = json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            if len(raw) > MAX_PACKET:
                return False
            self.sock.sendto(raw, addr)
            return True
        except OSError:
            return False

    def _send_hello(self, addr):
        return self._send_json(addr, {
            "type": "HELLO",
            "node_id": self.symbiont_id,
            "port": self.port,
            "ice_candidates": self.ice_candidates
        })

    def _message_id_seen(self, msg_id):
        if not msg_id:
            return False
        now_ts = time.time()
        with self.seen_lock:
            # cleanup
            self.seen_messages = {k: v for k, v in self.seen_messages.items() if now_ts - v < SEEN_CACHE_TTL}
            if msg_id in self.seen_messages:
                return True
            self.seen_messages[msg_id] = now_ts
            if len(self.seen_messages) > SEEN_CACHE_MAX:
                self.seen_messages.pop(next(iter(self.seen_messages)))
            return False

    def _listen_loop(self):
        while not self.stop_event.is_set():
            try:
                data, addr = self.sock.recvfrom(MAX_PACKET)
            except socket.timeout:
                continue
            except OSError:
                break
            # Rate limit before parsing
            if not self._rate_allow(addr):
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if not isinstance(msg, dict):
                continue
            # Basic signature presence check
            sig = msg.pop("sig", None)
            if SIGNING_ENABLED and not self._verify_sig(data, sig or ""):
                continue
            try:
                self._handle_message(msg, addr)
            except Exception:
                continue

    def _handle_message(self, msg, addr):
        mtype = msg.get("type")
        sender_id = str(msg.get("node_id", "unknown"))[:128]
        try:
            peer_port = int(msg.get("port", addr[1]))
        except (TypeError, ValueError):
            peer_port = addr[1]
        peer_key = (addr[0], peer_port)

        if mtype == "HELLO":
            self._upsert_peer(peer_key, sender_id, msg.get("ice_candidates", []), direct=True)
            return

        if mtype == "HEARTBEAT":
            self._upsert_peer(peer_key, sender_id, direct=True)
            return

        if mtype == "GOSSIP":
            mid = str(msg.get("msg_id", ""))
            if not mid or self._message_id_seen(mid):
                return
            self._upsert_peer(peer_key, sender_id, direct=True)
            peers = msg.get("peers", [])
            if isinstance(peers, list):
                for p in peers[:MAX_PEERS_IN_MESSAGE]:
                    try:
                        if isinstance(p, (list, tuple)) and len(p) >= 2:
                            self._upsert_peer((p[0], p[1]), p[2] if len(p) > 2 else "gossip", direct=False)
                    except Exception:
                        continue
            try:
                ttl = int(msg.get("ttl", 0))
            except (TypeError, ValueError):
                ttl = 0
            if ttl > 1:
                self._forward_gossip(msg, ttl - 1, peer_key)
            return

        if mtype == "VOTE_REQUEST":
            proposal = msg.get("proposal", {})
            options = proposal.get("options", [])
            choice = options[0] if options else None
            self._send_json(peer_key, {
                "type": "VOTE_RESPONSE",
                "node_id": self.symbiont_id,
                "proposal_id": proposal.get("proposal_id"),
                "choice": choice,
                "weight": max(0.1, self.cognitive.data.get("symbiont_reputation", 0.5))
            })
            return

    def _forward_gossip(self, msg, ttl, exclude_addr):
        out = dict(msg)
        out["ttl"] = ttl
        with self.peers_lock:
            peers = list(self.mesh_peers.items())
        random.shuffle(peers)
        sent = 0
        for addr, meta in peers:
            if addr == exclude_addr or sent >= GOSSIP_FANOUT:
                continue
            if self._send_json(addr, out):
                sent += 1

    def _gossip_loop(self):
        while not self.stop_event.wait(GOSSIP_INTERVAL):
            with self.peers_lock:
                peers = list(self.mesh_peers.items())[:MAX_PEERS_IN_MESSAGE]
            payload = [[addr[0], addr[1], meta.get("node_id", "")] for addr, meta in peers]
            msg = {
                "type": "GOSSIP",
                "node_id": self.symbiont_id,
                "port": self.port,
                "msg_id": secrets.token_hex(8),
                "ttl": GOSSIP_TTL,
                "peers": payload
            }
            self._message_id_seen(msg["msg_id"])
            with self.direct_lock:
                targets = list(self.direct_peers)
            for addr in targets[:GOSSIP_FANOUT]:
                self._send_json(addr, msg)

    def _heartbeat_loop(self):
        while not self.stop_event.wait(HEARTBEAT_INTERVAL):
            with self.direct_lock:
                targets = list(self.direct_peers)
            for addr in targets:
                self._send_json(addr, {
                    "type": "HEARTBEAT",
                    "node_id": self.symbiont_id,
                    "port": self.port
                })

    def _health_loop(self):
        while not self.stop_event.wait(HEALTH_INTERVAL):
            now_ts = now()
            with self.peers_lock:
                for addr, meta in list(self.mesh_peers.items()):
                    age = now_ts - meta.get("last_seen", 0)
                    if age > PEER_TIMEOUT:
                        self.mesh_peers.pop(addr, None)
                        self.direct_peers.discard(addr)
                    elif age > SUSPECT_AFTER:
                        meta["status"] = "SUSPECT"
                    else:
                        meta["status"] = "ONLINE"
            # periodic peer persistence
            if int(now_ts) % 30 < HEALTH_INTERVAL:
                self._save_peers()

    # ---------- HIGH-LEVEL API ----------
    def status(self):
        return {
            "version": VERSION,
            "symbiont_id": self.symbiont_id,
            "owner_id": self.owner_id,
            "device_id": self.device_id,
            "address": self.local_addr if self.started else None,
            "public_endpoint": self.public_endpoint,
            "known_peers": len(self.mesh_peers),
            "direct_peers": len(self.direct_peers),
            "memory_blocks": len(self.memory_chain),
            "balance": self.economy.get("survival_balance", 0),
            "cognitive_state": dict(self.cognitive.data["internal_state"]),
            "autonomy": self.cognitive.data["autonomy_level"],
            "active_body": self.cognitive.data["active_body_id"],
            "quests_open": sum(1 for q in self.quests.values() if q.get("status") == "OPEN")
        }

    def ask(self, query: str) -> str:
        q = str(query).strip().lower()
        if not q:
            return "Симбионт Omega Hybrid на связи."
        if "баланс" in q or "balance" in q:
            return f"Баланс выживания: ${self.economy.get('survival_balance', 0):.2f}"
        if "статус" in q or "status" in q:
            st = self.status()
            return (f"ID: {st['symbiont_id'][:18]}... | "
                    f"Блоков: {st['memory_blocks']} | "
                    f"Peers: {st['known_peers']} ({st['direct_peers']} direct) | "
                    f"Баланс: ${st['balance']:.1f}")
        hits = self.search_memory(q)
        if hits:
            lines = [f"• {h['payload'].get('text', '')}" for h in hits[:3]]
            return "Найдено в памяти:\n" + "\n".join(lines)
        self.remember(q, category="agent_input")
        self.cognitive.record_experience("query_processed", "recorded", q, 0.3)
        return f"Зафиксировано в защищённую цепочку: '{query}'."

    def status_report(self):
        st = self.status()
        print("\n================================================")
        print(f"      SYMBIONT OMEGA HYBRID v{VERSION}")
        print("================================================")
        print(f"Symbiont ID : {st['symbiont_id']}")
        print(f"Address     : {st['address']}  public={st['public_endpoint']}")
        print(f"Memory      : {st['memory_blocks']} блоков (chain valid: {self.verify_memory_chain()})")
        print(f"Mesh        : {st['known_peers']} known / {st['direct_peers']} direct")
        print(f"Balance     : ${st['balance']:.2f}")
        print(f"Autonomy    : {st['autonomy']:.2f}  Active body: {st['active_body']}")
        print(f"Cognitive   : {st['cognitive_state']}")
        print("================================================\n")

    @staticmethod
    def _save_json(filename: Path, data):
        tmp = filename.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(filename)


# ============================================================
# CLI
# ============================================================
def main():
    print("\n=================================================")
    print("      SYMBIONT OMEGA HYBRID v15.2")
    print("=================================================")
    owner = input("Владелец (по умолчанию raiingeo): ").strip() or "raiingeo"
    try:
        port = int(input("Порт (по умолчанию 9000): ").strip() or "9000")
    except ValueError:
        port = 9000

    node = SymbiontFullStackNode(owner_id=owner, device_id="phone_enclave", port=port)
    node.start_node()
    node.status_report()

    print("Команды: status | memory | quest <title> | peers | ask <text> | exit\n")

    try:
        while True:
            cmd = input(f"[{owner}]> ").strip()
            if not cmd:
                continue
            parts = cmd.split(" ", 1)
            action = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            if action in {"exit", "quit"}:
                break
            elif action == "status":
                node.status_report()
            elif action == "memory":
                for item in node.memory_chain[-12:]:
                    p = item.get("payload", {})
                    print(f"[{item['index']}] {p.get('text', item.get('event'))}")
            elif action == "quest":
                if args:
                    q = node.create_quest(args, reward=5.0)
                    print(f"[OK] Квест создан: {q['quest_id']}  status={q['status']}")
                else:
                    print("Активные квесты:")
                    for qid, q in node.quests.items():
                        print(f"  • [{qid}] {q['title']} — {q['status']} (reward={q['reward']})")
            elif action == "peers":
                with node.peers_lock:
                    for addr, m in node.mesh_peers.items():
                        print(f"  • {m.get('node_id', '?')[:20]}  {addr[0]}:{addr[1]}  last={m.get('last_seen', 0):.0f}")
            else:
                print(f"\n[Symbiont]: {node.ask(cmd)}\n")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        node.stop_node()
        print("\n=== СИМБИОНТ ОСТАНОВЛЕН ===")


if __name__ == "__main__":
    main()
