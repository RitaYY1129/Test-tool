from __future__ import annotations

from testpilot.cases.generator import generate_cases, generate_plan
from testpilot.model_providers.base import ModelProvider


class RuleBasedProvider(ModelProvider):
    """Offline deterministic provider used when no model API is configured."""

    def __init__(self, endpoints: list[dict]):
        self.endpoints = endpoints

    def generate_structured(self, system_prompt: str, user_prompt: str, output_schema: dict) -> dict:
        return {
            "plan": generate_plan(self.endpoints, user_prompt),
            "cases": generate_cases(self.endpoints, user_prompt),
            "provider": "rule_based",
        }

