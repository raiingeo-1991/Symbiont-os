# core/android_bridge.py
# Мост между ядром Symbiont и Android через Termux:API.
# Даёт: голос, слух, батарею, уведомления, сенсоры, GPS, вибрацию.

import subprocess
import json


def is_available():
    """Проверяет, работает ли Termux:API."""
    try:
        r = subprocess.run(["which", "termux-tts-speak"],
                           capture_output=True, timeout=2)
        return r.returncode == 0
    except Exception:
        return False


def speak(text):
    """Symbiont говорит голосом."""
    if not text:
        return False
    try:
        subprocess.run(["termux-tts-speak", str(text)],
                       timeout=30, capture_output=True)
        return True
    except Exception:
        return False


def listen(timeout=15):
    """Symbiont слушает через микрофон. Возвращает текст."""
    try:
        r = subprocess.run(["termux-speech-to-text"],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def battery():
    """Реальный уровень батареи в процентах."""
    try:
        r = subprocess.run(["termux-battery-status"],
                           capture_output=True, text=True, timeout=5)
        data = json.loads(r.stdout)
        return float(data.get("percentage", 100))
    except Exception:
        return 100.0


def battery_full():
    """Полная информация о батарее."""
    try:
        r = subprocess.run(["termux-battery-status"],
                           capture_output=True, text=True, timeout=5)
        return json.loads(r.stdout)
    except Exception:
        return {}


def notify(title, content):
    """Уведомление в шторке."""
    try:
        subprocess.run(["termux-notification",
                        "-t", str(title),
                        "-c", str(content)],
                       timeout=5, capture_output=True)
        return True
    except Exception:
        return False


def sensor(name="accelerometer"):
    """Показания сенсора."""
    try:
        r = subprocess.run(["termux-sensor", "-s", name, "-n", "1"],
                           capture_output=True, text=True, timeout=5)
        return json.loads(r.stdout)
    except Exception:
        return {}


def location():
    """GPS-координаты."""
    try:
        r = subprocess.run(["termux-location", "-p", "gps", "-f", "once"],
                           capture_output=True, text=True, timeout=10)
        return json.loads(r.stdout)
    except Exception:
        return {}


def vibrate(duration_ms=200):
    """Вибрация."""
    try:
        subprocess.run(["termux-vibrate", "-d", str(duration_ms)],
                       timeout=3, capture_output=True)
        return True
    except Exception:
        return False
