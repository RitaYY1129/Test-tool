from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from testpilot.domain.api import ApiDocument, ApiEndpoint, ApiParameter
from testpilot.parsers.openapi_parser import OpenApiParseError


class PostmanParser:
    def __init__(self):
        self.script_report = {"converted": 0, "manual_review": 0, "blocked": 0}

    def parse_file(self, path: str | Path) -> ApiDocument:
        source = Path(path)
        try:
            data = json.loads(source.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OpenApiParseError(f"Postman 文件无效：{exc}") from exc
        return self.parse_dict(data, source.name)

    def parse_dict(self, data: dict[str, Any], source_name: str = "<memory>") -> ApiDocument:
        schema = str((data.get("info") or {}).get("schema") or "")
        if "collection" not in schema.lower() and not isinstance(data.get("item"), list):
            raise OpenApiParseError("不是 Postman Collection")
        endpoints: list[ApiEndpoint] = []
        self.script_report = analyze_postman_scripts(data)
        self._walk(data.get("item") or [], [], endpoints, source_name)
        info = data.get("info") or {}
        return ApiDocument(str(info.get("name") or Path(source_name).stem), "", "Postman Collection v2.1", [], endpoints)

    def _walk(self, items: list, folders: list[str], output: list[ApiEndpoint], source_name: str):
        for item in items:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("item"), list):
                self._walk(item["item"], [*folders, str(item.get("name") or "未分组")], output, source_name)
                continue
            request = item.get("request")
            if not isinstance(request, dict):
                continue
            url = request.get("url") or ""
            raw_url = url.get("raw", "") if isinstance(url, dict) else str(url)
            path, query = self._path_and_query(url, raw_url)
            parameters = [
                ApiParameter(str(q.get("key") or ""), "query", False, {"type": "string"}, example=q.get("value"))
                for q in query if isinstance(q, dict) and not q.get("disabled")
            ]
            parameters.extend(
                ApiParameter(str(h.get("key") or ""), "header", False, {"type": "string"}, example=h.get("value"))
                for h in request.get("header") or [] if isinstance(h, dict) and not h.get("disabled")
            )
            output.append(ApiEndpoint(
                method=str(request.get("method") or "GET").upper(), path=path, summary=str(item.get("name") or ""),
                module=folders[-1] if folders else "未分组", parameters=parameters,
                request_body=self._body(request.get("body") or {}), responses={},
                security=[{"postmanAuth": []}] if request.get("auth") else [],
                source="postman", source_location=source_name,
            ))

    @staticmethod
    def _path_and_query(url: Any, raw_url: str) -> tuple[str, list]:
        if isinstance(url, dict):
            parts = url.get("path") or []
            path = "/" + "/".join(str(x) for x in parts) if parts else urlsplit(raw_url).path
            return path or "/", url.get("query") or []
        parsed = urlsplit(raw_url.replace("{{baseUrl}}", "http://placeholder"))
        return parsed.path or "/", []

    @staticmethod
    def _body(body: dict) -> dict:
        mode = body.get("mode")
        if mode == "raw":
            raw = body.get("raw", "")
            try:
                example = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                example = raw
            content_type = "application/json" if isinstance(example, (dict, list)) else "text/plain"
            return {"content": {content_type: {"example": example}}}
        if mode in {"urlencoded", "formdata"}:
            values = {x.get("key"): x.get("value") for x in body.get(mode, []) if isinstance(x, dict)}
            content_type = "application/x-www-form-urlencoded" if mode == "urlencoded" else "multipart/form-data"
            return {"content": {content_type: {"example": values}}}
        return {}


def parse_postman_environment(path: str | Path) -> tuple[str, dict[str, str], set[str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    values, sensitive = {}, set()
    for item in data.get("values", []):
        if not item.get("enabled", True):
            continue
        key = str(item.get("key") or "")
        values[key] = str(item.get("value") or "")
        if item.get("type") == "secret" or any(x in key.lower() for x in ("token", "secret", "password", "key")):
            sensitive.add(key)
    return str(data.get("name") or "Postman 环境"), values, sensitive


def analyze_postman_scripts(data: dict) -> dict[str, int]:
    report = {"converted": 0, "manual_review": 0, "blocked": 0}
    safe_patterns = ("pm.environment.set(", "pm.collectionVariables.set(", "pm.response.to.have.status(",
                     "pm.expect(pm.response.json()")
    blocked_patterns = ("require(", "eval(", "pm.sendRequest(", "fs.", "child_process")

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if isinstance(node.get("script"), dict):
                lines = node["script"].get("exec") or []
                script = "\n".join(lines) if isinstance(lines, list) else str(lines)
                if any(pattern in script for pattern in blocked_patterns):
                    report["blocked"] += 1
                elif any(pattern in script for pattern in safe_patterns):
                    report["converted"] += 1
                elif script.strip():
                    report["manual_review"] += 1
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
    walk(data)
    return report
