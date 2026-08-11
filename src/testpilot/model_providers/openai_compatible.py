from __future__ import annotations

import json
from dataclasses import dataclass
from threading import Event

import httpx

from testpilot.model_providers.base import ModelProvider
from testpilot.model_providers.resilience import run_with_retry


@dataclass(slots=True)
class OpenAICompatibleProvider(ModelProvider):
    base_url: str
    api_key: str
    model: str
    timeout: float = 60
    retries: int = 1
    cancel_event: Event | None = None

    def generate_structured(self, system_prompt: str, user_prompt: str, output_schema: dict) -> dict:
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        def request(_attempt):
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
        return run_with_retry(request, self.retries, self.cancel_event)

    def generate_chat(self, system_prompt: str, messages: list[dict[str, str]]) -> str:
        """Use native chat mode instead of forcing a JSON test artifact."""
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        def request(_attempt):
            response = httpx.post(
                url,
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system_prompt}, *messages],
                    "temperature": 0.4,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"] or "").strip()

        reply = run_with_retry(request, self.retries, self.cancel_event)
        if not reply:
            raise RuntimeError("Model returned an empty response")
        return reply
