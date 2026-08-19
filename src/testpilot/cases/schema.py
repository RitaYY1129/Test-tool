from __future__ import annotations

TEST_GENERATION_SCHEMA = {
    "type": "object",
    "required": ["plan", "cases"],
    "properties": {
        "plan": {
            "type": "object",
            "required": ["scope", "test_types", "requires_confirmation"],
            "properties": {
                "scope": {"type": "array", "items": {"type": "string"}},
                "test_types": {"type": "array", "items": {"type": "string"}},
                "requires_confirmation": {"type": "boolean"},
                "excluded": {"type": "array", "items": {"type": "string"}},
            },
        },
        "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "priority", "request", "assertions", "source", "review_status"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "priority": {"enum": ["P0", "P1", "P2", "P3"]},
                    "request": {
                        "type": "object",
                        "required": ["method", "path"],
                        "properties": {
                            "method": {"enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]},
                            "path": {"type": "string", "pattern": "^/"},
                        },
                    },
                    "assertions": {"type": "array"},
                    "source": {"type": "string"},
                    "review_status": {"enum": ["draft", "confirmed"]},
                },
            },
        },
    },
}


def validate_generation(value: dict, endpoint_keys: set[str] | None = None) -> None:
    from testpilot.common.schema_validation import validate

    validate(value, TEST_GENERATION_SCHEMA)
    if endpoint_keys is not None:
        for case in value["cases"]:
            key = f'{case["request"]["method"]} {case["request"]["path"]}'
            if key not in endpoint_keys:
                raise ValueError(f"模型生成了不存在的接口：{key}")
            if case["request"]["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
                case["risk"] = "high"
                case["review_status"] = "draft"
