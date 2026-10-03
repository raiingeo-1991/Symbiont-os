# core/body.py
# Тело Symbiont — продолжение ядра.
# Ядро думает. Тело делает. Ядро просит — тело отвечает.

import os
import socket
import threading
import json


class Body:
    """Контракт тела. Что ядро может попросить."""

    name = "abstract"

    # --- Сенсоры и голос ---
    def is_available(self): return False
    def speak(self, text): return False
    def listen(self, timeout=15): return ""
    def battery(self): return 100.0
    def notify(self, title, content): return False
    def sensor(self, name="accelerometer"): return {}
    def location(self): return {}
    def vibrate(self, ms=200): return False
    def info(self): return {"name": self.name, "available": self.is_available()}

    # --- Сеть ---
    def send_udp(self, ip, port, data): return False
    def send_tcp(self, ip, port, data, timeout=8.0): return None
    def start_udp_listener(self, port, callback): return False
    def start_tcp_server(self, port, callback): return False
    def stop_network(self): return False


class NullBody(Body):
    """Заглушка. Для Pydroid, ПК, сервера."""

    name = "null"

    def is_available(self): return True

    def speak(self, text):
        print(f"[voice] {text}")
        return True

    def battery(self): return 100.0



def get_body(force=None):
    return NullBody()

# ============================================================
# XLINK — Core/Body Adapter
# ============================================================

class XLink:
    """
    Lightweight adapter between Body and an external node layer.
    Keeps the Core itself untouched.
    """

    def __init__(self, core=None):
        self.core = core
        self.connected = False
        self.node_id = None
        self.node_type = "node"

    def connect(self, node_id):
        node_id = str(node_id).strip()

        if not node_id:
            return False

        self.node_id = node_id
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False
        self.node_id = None
        return True

    def attach_core(self, core):
        self.core = core
        return True

    def status(self):
        return {
            "module": "xlink",
            "connected": self.connected,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "core_attached": self.core is not None,
        }

    def send_event(self, event, data=None):
        if not self.connected:
            return False

        data = data or {}

        if self.core is not None and hasattr(self.core, "remember"):
            self.core.remember(
                f"Node event: {event} | {data}",
                kind="external",
                
            )

        return True


def get_xlink(core=None):
    return XLink(core)


# ============================================================
# SMSA — Security Adapter
# ============================================================

try:
    from .security import get_security, SecurityError
except ImportError:
    from security import get_security, SecurityError


class SecureBody:
    """
    Security-aware adapter for Body capabilities.
    Does not modify Core.
    """

    def __init__(self, body=None, security=None):
        self.body = body or get_body()
        self.security = security or get_security()

    def _authorize(self, capability):
        self.security.authorize(capability)
        return True

    def speak(self, text):
        self._authorize("file.write")
        return self.body.speak(text)

    def listen(self):
        self._authorize("microphone.listen")
        return self.body.listen()

    def battery(self):
        self._authorize("sensor.read")
        return self.body.battery()

    def sensor(self):
        self._authorize("sensor.read")
        return self.body.sensor()

    def location(self):
        self._authorize("location.read")
        return self.body.location()

    def notify(self, title, content):
        self._authorize("file.write")
        return self.body.notify(title, content)

    def vibrate(self, duration=300):
        self._authorize("file.write")
        return self.body.vibrate(duration)

    def send_udp(self, host, port, data):
        self._authorize("network.send")
        return self.body.send_udp(host, port, data)

    def send_tcp(self, host, port, data):
        self._authorize("network.send")
        return self.body.send_tcp(host, port, data)


def get_secure_body(body=None, security=None):
    return SecureBody(body, security)
