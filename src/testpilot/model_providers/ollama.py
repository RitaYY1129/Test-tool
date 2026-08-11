from __future__ import annotations

import json
from dataclasses import dataclass
from threading import Event
from typing import Any

import httpx

from testpilot.model_providers.base import ModelProvider
from testpilot.model_providers.resilience import run_with_retry


@dataclass(slots=True)
class OllamaProvider(ModelProvider):
    base_url: str = "http://localhost:11434"
    model: str = ""
    timeout: float = 180
    retries: int = 1
    cancel_event: Event | None = None

    def list_models(self) -> list[str]:
        response = httpx.get(self.base_url.rstrip("/") + "/api/tags", timeout=20)
        response.raise_for_status()
        return [
            item.get("name", "") for item in response.json().get("models", [])
            if item.get("name")
        ]

    def generate_structured(
        self, system_prompt: str, user_prompt: str, output_schema: dict
    ) -> dict[str, Any]:
        if not self.model.strip():
            raise ValueError("请填写 Ollama 模型名称。")
        def request(_attempt):
            response = httpx.post(
            self.base_url.rstrip("/") + "/api/chat",
            json={
                "model": self.model.strip(),
                "stream": False,
                "format": output_schema,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "options": {"temperature": 0.1},
            },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            return json.loads(content) if isinstance(content, str) else content
        return run_with_retry(request, self.retries, self.cancel_event)

    def generate_chat(self, system_prompt: str, messages: list[dict[str, str]]) -> str:
        if not self.model.strip():
            raise ValueError("Please enter an Ollama model name.")

        def request(_attempt):
            response = httpx.post(
                self.base_url.rstrip("/") + "/api/chat",
                json={
                    "model": self.model.strip(),
                    "stream": False,
                    "messages": [{"role": "system", "content": system_prompt}, *messages],
                    "options": {"temperature": 0.4},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return str(response.json()["message"].get("content") or "").strip()

        reply = run_with_retry(request, self.retries, self.cancel_event)
        if not reply:
            raise RuntimeError("Model returned an empty response")
        return reply
