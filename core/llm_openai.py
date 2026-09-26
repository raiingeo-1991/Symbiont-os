# core/llm_openai.py
# OpenAI-совместимый провайдер для llama-server.

import json
import urllib.request


class OpenAIProvider:
    name = "openai"

    def __init__(self, url="http://localhost:11434", model="qwen2.5"):
        self.url = url.rstrip("/")
        self.model = model

    def is_available(self):
        try:
            req = urllib.request.Request(self.url + "/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self):
        try:
            req = urllib.request.Request(self.url + "/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("id", "?") for m in data.get("data", [])]
        except Exception:
            return []

    def chat(self, messages, timeout=120.0):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.7,
            "max_tokens": 512,
        }
        try:
            req = urllib.request.Request(
                self.url + "/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return None
