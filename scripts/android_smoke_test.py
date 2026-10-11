#!/usr/bin/env python3
"""Проверка Symbiont и Termux:API на реальном Android-устройстве."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.android_bridge import listen
from core.body import get_body
from core.llm_openai import OpenAIProvider
from symbiont_core import Symbiont


class Report:
    def __init__(self):
        self.failed = 0

    def check(self, name, ok, detail=""):
        label = "PASS" if ok else "FAIL"
        print(f"[{label}] {name}" + (f": {detail}" if detail else ""))
        if not ok:
            self.failed += 1
        return ok


def run_command(args, timeout=15):
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        detail = (result.stdout or result.stderr).strip()
        return result.returncode == 0, detail
    except Exception as error:
        return False, str(error)


def test_persistence(report):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        hidden_output = io.StringIO()
        with contextlib.redirect_stdout(hidden_output):
            first = Symbiont(root)
        identity = first.identity.id()
        memory_id = first.remember("Android smoke test", importance=10)
        offline = not first.llm_status()["enabled"]
        first.close()

        with contextlib.redirect_stdout(hidden_output):
            second = Symbiont(root)
        try:
            memories = second.memory.search("Android smoke test")
            ok = (
                second.identity.id() == identity
                and memories
                and memories[0].memory_id == memory_id
                and offline
            )
            report.check("Память и личность после перезапуска", bool(ok))
        finally:
            second.close()


def test_termux(report, interactive):
    is_termux = "com.termux" in os.environ.get("PREFIX", "")
    report.check("Среда Termux", is_termux, os.environ.get("PREFIX", "не обнаружена"))

    commands = [
        "termux-battery-status",
        "termux-notification",
        "termux-speech-to-text",
        "termux-tts-speak",
        "termux-vibrate",
    ]
    available = all(shutil.which(command) for command in commands)
    report.check("Команды Termux:API", available)

    body = get_body(force="android")
    report.check("AndroidBody", body.is_available())

    battery_ok, battery_raw = run_command(["termux-battery-status"], timeout=8)
    try:
        battery_data = json.loads(battery_raw) if battery_ok else {}
        percentage = battery_data.get("percentage")
        battery_ok = battery_ok and isinstance(percentage, (int, float))
    except json.JSONDecodeError:
        percentage = None
        battery_ok = False
    report.check("Батарея", battery_ok, f"{percentage}%" if percentage is not None else battery_raw)

    if not interactive or not (is_termux and available):
        print("[SKIP] Голос, микрофон, уведомление и вибрация: добавь --interactive")
        return

    speak_ok, speak_detail = run_command(
        ["termux-tts-speak", "Тест Symbiont. Голос работает."],
        timeout=30,
    )
    if speak_ok:
        heard = input("Ты услышал фразу? [y/N]: ").strip().lower() in {"y", "yes", "д", "да"}
        speak_ok = heard
    report.check("Голос", speak_ok, speak_detail)

    print("Скажи короткую фразу после появления окна микрофона.")
    heard_text = listen(timeout=30)
    report.check("Микрофон", bool(heard_text), heard_text or "текст не получен")

    notify_ok, notify_detail = run_command(
        ["termux-notification", "-t", "Symbiont", "-c", "Android smoke test"],
        timeout=20,
    )
    report.check("Уведомление", notify_ok, notify_detail)

    vibrate_ok, vibrate_detail = run_command(["termux-vibrate", "-d", "250"], timeout=15)
    report.check("Вибрация", vibrate_ok, vibrate_detail)


def test_llm(report, url, model):
    if not url:
        print("[SKIP] Локальная LLM: добавь --llm-url и при необходимости --llm-model")
        return

    provider = OpenAIProvider(url=url, model=model)
    if not report.check("LLM-сервер", provider.is_available(), url):
        return
    models = provider.list_models()
    report.check("Список моделей", bool(models), ", ".join(models))
    answer = provider.chat([{"role": "user", "content": "Ответь одним словом: работает?"}])
    report.check("Ответ LLM", bool(answer), (answer or "нет ответа")[:160])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive", action="store_true", help="проверить голос и микрофон")
    parser.add_argument("--llm-url", default="", help="URL OpenAI-совместимого локального сервера")
    parser.add_argument("--llm-model", default="qwen2.5", help="имя локальной модели")
    args = parser.parse_args()

    report = Report()
    print("Symbiont Android smoke test\n")
    test_persistence(report)
    test_termux(report, args.interactive)
    test_llm(report, args.llm_url, args.llm_model)

    print(f"\nИтог: {'PASS' if report.failed == 0 else 'FAIL'}; ошибок: {report.failed}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
