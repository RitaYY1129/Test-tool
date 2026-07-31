from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from testpilot.model_providers.base import ModelProvider


@dataclass(slots=True)
class OpenAICompatibleProvider(ModelProvider):
    base_url: str
    api_key: str
    model: str
    timeout: float = 60

    def generate_structured(self, system_prompt: str, user_prompt: str, output_schema: dict) -> dict:
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            url,
            headers=headers,
            json={
                "model": self.model,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "test_generation", "strict": True, "schema": output_schema},
                },
                "temperature": 0.1,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        return json.loads(content) if isinstance(content, str) else content
