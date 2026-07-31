from __future__ import annotations

import re
import secrets
import time
import uuid
from typing import Any

VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def resolve(value: Any, variables: dict[str, Any]) -> Any:
    dynamic = {
        "TIMESTAMP": str(int(time.time())),
        "TIMESTAMP_MS": str(int(time.time() * 1000)),
        "UUID": str(uuid.uuid4()),
        "RANDOM": str(secrets.randbelow(1_000_000)),
    }
    context = {**dynamic, **variables}
    if isinstance(value, dict):
        return {key: resolve(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, context) for item in value]
    if not isinstance(value, str):
        return value
    full = VARIABLE.fullmatch(value)
    if full:
        return context.get(full.group(1), value)
    return VARIABLE.sub(lambda match: str(context.get(match.group(1), match.group(0))), value)


def extract_values(body: Any, headers: dict, rules: list[dict]) -> dict:
    from testpilot.engines.assertions import json_path

    output = {}
    lowered_headers = {key.lower(): value for key, value in headers.items()}
    for rule in rules:
        source = rule.get("source", "json")
        if source == "json":
            value = json_path(body, rule.get("path", ""))
        elif source == "header":
            value = lowered_headers.get(str(rule.get("name", "")).lower())
        else:
            continue
        if value is not None and rule.get("variable"):
            output[rule["variable"]] = value
    return output
