import json
import os
import socket
import threading
import time


class PeerRegistry:
    def __init__(self, path="symbiont_data/peers.json"):
        self.path = path
        self.lock = threading.RLock()
        self.peers = {}
        self._load()

    def _load(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self.peers = data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.peers = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.peers, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def upsert(self, node_id, address, port, public_key=None,
               status="seen", metadata=None):
        with self.lock:
            self.peers[str(node_id)] = {
                "node_id": str(node_id),
                "address": str(address),
                "port": int(port),
                "public_key": public_key,
                "status": status,
                "last_seen": time.time(),
                "metadata": metadata or {},
            }
            self._save()
            return True

    def get(self, node_id):
        with self.lock:
            peer = self.peers.get(str(node_id))
            return dict(peer) if peer else None

    def remove(self, node_id):
        with self.lock:
            if str(node_id) not in self.peers:
                return False
            del self.peers[str(node_id)]
            self._save()
            return True

    def all(self):
        with self.lock:
            return [dict(p) for p in self.peers.values()]

    def count(self):
        with self.lock:
            return len(self.peers)


class NodeDiscovery:
    DISCOVERY_PORT = 7781
    MESSAGE_TYPE = "SYM_DISCOVERY/1"

    def __init__(self, node_id, public_key=None, registry=None, port=7781):
        self.node_id = str(node_id)
        self.public_key = public_key
        self.registry = registry or PeerRegistry()
        self.port = int(port)
        self.running = False
        self.socket = None
        self.thread = None

    def announcement(self):
        return {
            "type": self.MESSAGE_TYPE,
            "node_id": self.node_id,
            "public_key": self.public_key,
            "port": self.port,
            "timestamp": time.time(),
        }

    def discover_message(self, data, source_address=None):
        if not isinstance(data, dict):
            return False
        if data.get("type") != self.MESSAGE_TYPE:
            return False

        node_id = data.get("node_id")
        port = data.get("port")

        if not node_id or node_id == self.node_id or not port:
            return False

        address = data.get("address") or source_address
        if not address:
            return False

        return self.registry.upsert(
            node_id,
            address,
            port,
            data.get("public_key"),
            "discovered",
        )

    def start(self):
        if self.running:
            return True

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("", self.port))

        self.running = True
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()
        return True

    def _listen(self):
        while self.running and self.socket:
            try:
                self.socket.settimeout(1.0)
                raw, addr = self.socket.recvfrom(65535)
                data = json.loads(raw.decode("utf-8"))
                self.discover_message(data, addr[0])
            except socket.timeout:
                continue
            except (OSError, ValueError, UnicodeDecodeError):
                continue

    def broadcast(self):
        if not self.socket:
            return False

        raw = json.dumps(
            self.announcement(),
            separators=(",", ":")
        ).encode("utf-8")

        try:
            self.socket.sendto(
                raw,
                ("255.255.255.255", self.port)
            )
            return True
        except OSError:
            return False

    def stop(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
        self.socket = None
        return True

    def status(self):
        return {
            "running": self.running,
            "node_id": self.node_id,
            "port": self.port,
            "peers": self.registry.count(),
        }


def get_peer_registry(path="symbiont_data/peers.json"):
    return PeerRegistry(path)


def get_node_discovery(node_id, public_key=None, registry=None, port=7781):
    return NodeDiscovery(node_id, public_key, registry, port)
