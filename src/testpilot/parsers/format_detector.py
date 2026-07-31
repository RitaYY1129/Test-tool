from __future__ import annotations

import json
from pathlib import Path


def detect_format(path: str | Path) -> str:
    source = Path(path)
    if source.suffix.lower() == ".har":
        return "har"
    if source.suffix.lower() in {".md", ".txt", ".html", ".htm", ".xlsx", ".xlsm", ".docx", ".pdf"}:
        return "document"
    if source.suffix.lower() in {".yaml", ".yml"}:
        return "openapi"
    if source.suffix.lower() == ".json":
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        if data.get("openapi") or data.get("swagger"):
            return "openapi"
        if isinstance(data.get("log", {}).get("entries"), list):
            return "har"
        schema = str((data.get("info") or {}).get("schema") or "")
        if "postman" in schema or isinstance(data.get("item"), list):
            return "postman"
        if isinstance(data.get("values"), list) and "environment" in str(data.get("_postman_variable_scope", "")).lower():
            return "postman_environment"
        return "apifox"
    return "unknown"
