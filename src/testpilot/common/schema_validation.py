from __future__ import annotations

from typing import Any


def validate(value: Any, schema: dict) -> None:
    """Small JSON Schema subset used by TestPilot, with optional full support.

    This keeps validation operational when a Python version lacks an ``rpds``
    wheel required by jsonschema.  When available, jsonschema remains the
    authoritative validator for richer schemas.
    """
    try:
        from jsonschema import validate as jsonschema_validate
    except (ImportError, ModuleNotFoundError):
        _validate(value, schema, "$")
    else:
        jsonschema_validate(value, schema)


def _validate(value: Any, schema: dict, path: str) -> None:
    kind = schema.get("type")
    type_map = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}
    if kind and (not isinstance(value, type_map[kind]) or kind in {"integer", "number"} and isinstance(value, bool)):
        raise ValueError(f"{path} 类型应为 {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} 不在允许值中")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{path} 长度不足")
        if schema.get("pattern") == "^/" and not value.startswith("/"):
            raise ValueError(f"{path} 必须以 / 开头")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}.{key} 为必填项")
        for key, child_schema in schema.get("properties", {}).items():
            if key in value:
                _validate(value[key], child_schema, f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _validate(item, schema["items"], f"{path}[{index}]")
