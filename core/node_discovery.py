import json
import os
import socket
import threading
import time


class PeerRegistry:
    """Persistent registry of known Symbiont nodes."""

    def __init__(self, path=None):
        self.path = path or os.path.join(
            "symbiont_data",
            "peers.json",
        )
        self._lock = threading.RLock()
        self._peers = {}
        self._load()

    def _load(self):
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._peers = data
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                self._peers = {}

    def _save(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        tmp = self.path + ".tmp"

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                self._peers,
                f,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )

        os.replace(tmp, self.path)

    def upsert(
        self,
        node_id,
        address,
        port,
        public_key=None,
        status="known",
        metadata=None,
    ):
        node_id = str(node_id).strip()

        if not node_id:
            return False

        with self._lock:
            current = self._peers.get(node_id, {})

            current.update(
                {
                    "node_id": node_id,
                    "address": str(address),
                    "port": int(port),
                    "status": str(status),
                    "last_seen": time.time(),
                }
            )

            if public_key is not None:
                current["public_key"] = public_key

            if metadata is not None:
                current["metadata"] = metadata

            self._peers[node_id] = current
            self._save()

        return True

    def get(self, node_id):
        with self._lock:
            peer = self._peers.get(str(node_id).strip())

            if peer is None:
                return None

            return dict(peer)

    def remove(self, node_id):
        with self._lock:
            node_id = str(node_id).strip()

            if node_id not in self._peers:
                return False

            del self._peers[node_id]
            self._save()

        return True

    def all(self):
        with self._lock:
            return [dict(peer) for peer in self._peers.values()]

    def count(self):
        with self._lock:
            return len(self._peers)


class NodeDiscovery:
    """
    Lightweight UDP discovery layer.

    Discovery only finds peers.
    Trust and cryptographic verification are handled separately.
    """

    DISCOVERY_PORT = 7781
    MESSAGE_TYPE = "SYM_DISCOVERY/1"

    def __init__(
        self,
        node_id,
        public_key=None,
        registry=None,
        port=DISCOVERY_PORT,
    ):
        self.node_id = str(node_id).strip()
        self.public_key = public_key
        self.registry = registry or PeerRegistry()
        self.port = int(port)

        self.running = False
        self._stop_event = threading.Event()
        self._thread = None
        self._socket = None

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

        if not node_id:
            return False

        if node_id == self.node_id:
            return False

        if not port:
            return False

        address = data.get("address") or source_address

        if not address:
            return False

        return self.registry.upsert(
            node_id,
            address,
            port,
            public_key=data.get("public_key"),
            status="discovered",
        )

    def _listen(self):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )

        try:
            sock.bind(
                ("0.0.0.0", self.port)
            )
        except OSError:
            sock.close()
            return

        sock.settimeout(0.5)
        self._socket = sock

        while not self._stop_event.is_set():
            try:
                raw, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                data = json.loads(
                    raw.decode("utf-8")
                )
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
            ):
                continue

            self.discover_message(
                data,
                addr[0],
            )

        try:
            sock.close()
        except OSError:
            pass

        self._socket = None

    def start(self):
        if self.running:
            return True

        self._stop_event.clear()

        thread = threading.Thread(
            target=self._listen,
            daemon=True,
        )

        self._thread = thread
        self.running = True
        thread.start()

        return True

    def broadcast(self, address="255.255.255.255"):
        payload = json.dumps(
            self.announcement(),
            separators=(",", ":"),
        ).encode("utf-8")

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        try:
            sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_BROADCAST,
                1,
            )

            sock.sendto(
                payload,
                (address, self.port),
            )

            return True

        except OSError:
            return False

        finally:
            sock.close()

    def stop(self):
        self.running = False
        self._stop_event.set()

        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass

        return True

    def status(self):
        return {
            "running": self.running,
            "node_id": self.node_id,
            "port": self.port,
            "peers": self.registry.count(),
        }


def get_peer_registry(path=None):
    return PeerRegistry(path)


def get_node_discovery(
    node_id,
    public_key=None,
    registry=None,
    port=NodeDiscovery.DISCOVERY_PORT,
):
    return NodeDiscovery(
        node_id,
        public_key=public_key,
        registry=registry,
        port=port,
    )
