from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ModelProvider(ABC):
    @abstractmethod
    def generate_structured(self, system_prompt: str, user_prompt: str, output_schema: dict) -> dict[str, Any]:
        """Return data conforming to output_schema without executing any request."""

