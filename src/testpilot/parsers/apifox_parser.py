from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from testpilot.domain.api import ApiDocument, ApiEndpoint, ApiParameter
from testpilot.parsers.openapi_parser import OpenApiParser
from testpilot.parsers.postman_parser import PostmanParser


class ApifoxParser:
    """Supports OpenAPI/Postman exports and common Apifox native JSON shapes."""

    def parse_file(self, path: str | Path) -> ApiDocument:
        source = Path(path)
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        if data.get("openapi") or data.get("swagger"):
            return OpenApiParser().parse_dict(data, source.name)
        if isinstance(data.get("item"), list):
            return PostmanParser().parse_dict(data, source.name)
        endpoints = []
        self._walk(data, [], endpoints, source.name)
        if not endpoints:
            raise ValueError("无法识别该 Apifox 原生 JSON；建议从 Apifox 导出 OpenAPI 3.0")
        info = data.get("info") or data.get("project") or {}
        return ApiDocument(str(info.get("name") or source.stem), "", "Apifox native (basic)", [], endpoints)

    def _walk(self, node: Any, folders: list[str], output: list[ApiEndpoint], source_name: str):
        if isinstance(node, list):
            for item in node:
                self._walk(item, folders, output, source_name)
            return
        if not isinstance(node, dict):
            return
        method = str(node.get("method") or node.get("apiMethod") or "").upper()
        path = node.get("path") or node.get("url")
        if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} and isinstance(path, str):
            params = []
            for location, keys in (("query", ("parameters", "queryParams")), ("header", ("headers",)), ("path", ("pathParams",))):
                items = next((node.get(key) for key in keys if isinstance(node.get(key), list)), [])
                params.extend(
                    ApiParameter(str(x.get("name") or x.get("key") or ""), location, bool(x.get("required")),
                                 x.get("schema") or {"type": x.get("type", "string")}, example=x.get("example") or x.get("value"))
                    for x in items if isinstance(x, dict)
                )
            output.append(ApiEndpoint(
                method, _normalize_path(path), str(node.get("name") or node.get("summary") or ""),
                module=folders[-1] if folders else str(node.get("folder") or "Apifox"),
                parameters=params, request_body=node.get("requestBody") or {}, responses=node.get("responses") or {},
                source="apifox", source_location=source_name,
            ))
        for key, value in node.items():
            next_folders = folders
            if key in {"items", "children", "apis", "apiCollection"} and node.get("name"):
                next_folders = [*folders, str(node["name"])]
            if isinstance(value, (dict, list)):
                self._walk(value, next_folders, output, source_name)


def _normalize_path(value: str) -> str:
    from urllib.parse import urlsplit
    if value.startswith(("http://", "https://")):
        return urlsplit(value).path or "/"
    return value if value.startswith("/") else "/" + value

