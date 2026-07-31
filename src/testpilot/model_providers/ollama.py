from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from testpilot.model_providers.base import ModelProvider


@dataclass(slots=True)
class OllamaProvider(ModelProvider):
    base_url: str = "http://localhost:11434"
    model: str = ""
    timeout: float = 180

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
