from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

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
                                 x.get("schema") or {"type": x.get("type", "string")},
                                 str(x.get("description") or x.get("comment") or ""),
                                 example=x.get("example") if x.get("example") is not None else x.get("value"))
                    for x in items if isinstance(x, dict)
                )
            route, inline_query = _path_and_query(path)
            known_query_names = {parameter.name for parameter in params if parameter.location == "query"}
            params.extend(
                ApiParameter(name, "query", schema={"type": "string"}, example=value)
                for name, value in inline_query if name not in known_query_names
            )
            output.append(ApiEndpoint(
                method, route, str(node.get("name") or node.get("summary") or ""),
                module=folders[-1] if folders else str(node.get("folder") or "Apifox"),
                parameters=params, request_body=_normalize_request_body(node), responses=node.get("responses") or {},
                source="apifox", source_location=source_name,
            ))
        for key, value in node.items():
            next_folders = folders
            if key in {"items", "children", "apis", "apiCollection"} and node.get("name"):
                next_folders = [*folders, str(node["name"])]
            if isinstance(value, (dict, list)):
                self._walk(value, next_folders, output, source_name)


def _normalize_path(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return urlsplit(value).path or "/"
    return value if value.startswith("/") else "/" + value


def _path_and_query(value: str) -> tuple[str, list[tuple[str, str]]]:
    parsed = urlsplit(value)
    if value.startswith(("http://", "https://")):
        route = parsed.path or "/"
    else:
        route = parsed.path if parsed.path.startswith("/") else "/" + parsed.path
    return route or "/", parse_qsl(parsed.query, keep_blank_values=True)


def _normalize_request_body(node: dict[str, Any]) -> dict[str, Any]:
    """Map common Apifox native body variants into the OpenAPI content shape."""
    request_body = node.get("requestBody") or node.get("body")
    if not isinstance(request_body, dict) or not request_body:
        return {}
    if isinstance(request_body.get("content"), dict):
        return request_body
    body_type = str(request_body.get("type") or request_body.get("mode") or node.get("bodyType") or "json").lower()
    content_type = {
        "json": "application/json", "raw": "text/plain", "text": "text/plain", "xml": "application/xml",
        "form-data": "multipart/form-data", "formdata": "multipart/form-data",
        "x-www-form-urlencoded": "application/x-www-form-urlencoded", "urlencoded": "application/x-www-form-urlencoded",
    }.get(body_type, "application/json")
    schema = request_body.get("schema") or request_body.get("jsonSchema") or request_body.get("json_schema") or {}
    raw_example = request_body.get("example")
    if raw_example is None:
        raw_example = request_body.get("json", request_body.get("raw", request_body.get("data")))
    if isinstance(raw_example, str) and body_type == "json":
        try:
            raw_example = json.loads(raw_example)
        except json.JSONDecodeError:
            pass
    fields = request_body.get("parameters") or request_body.get("params") or request_body.get("formData") or []
    if isinstance(fields, list) and fields:
        properties: dict[str, dict] = {}
        example: dict[str, Any] = {}
        for field in fields:
            if not isinstance(field, dict):
                continue
            name = str(field.get("name") or field.get("key") or "")
            if not name:
                continue
            properties[name] = {
                "type": str(field.get("type") or "string"),
                "description": str(field.get("description") or field.get("comment") or ""),
            }
            if field.get("example") is not None or field.get("value") is not None:
                example[name] = field.get("example") if field.get("example") is not None else field.get("value")
        if properties and not schema:
            schema = {"type": "object", "properties": properties}
        if example and raw_example is None:
            raw_example = example
    media: dict[str, Any] = {"schema": schema if isinstance(schema, dict) else {}}
    if raw_example is not None:
        media["example"] = raw_example
    return {"content": {content_type: media}}

