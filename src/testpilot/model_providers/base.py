from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ModelProvider(ABC):
    @abstractmethod
    def generate_structured(self, system_prompt: str, user_prompt: str, output_schema: dict) -> dict[str, Any]:
        """Return data conforming to output_schema without executing any request."""

    def generate_chat(self, system_prompt: str, messages: list[dict[str, str]]) -> str:
        """Return a direct conversational reply when supported by the provider."""
        raise NotImplementedError("This model provider does not support direct chat")
