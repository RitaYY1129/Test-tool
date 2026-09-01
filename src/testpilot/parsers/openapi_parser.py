from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from testpilot.domain.api import ApiDocument, ApiEndpoint, ApiParameter

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


class OpenApiParseError(ValueError):
    pass


class OpenApiParser:
    def parse_url(self, url: str) -> ApiDocument:
        import httpx
        if not url.lower().startswith(("http://", "https://")):
            raise OpenApiParseError("在线文档地址必须以 http:// 或 https:// 开头")
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        return self.parse_text(response.text, url)

    def parse_file(self, path: str | Path) -> ApiDocument:
        source = Path(path)
        try:
            text = source.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise OpenApiParseError(f"无法读取文件：{exc}") from exc
        return self.parse_text(text, source.name)

    def parse_text(self, text: str, source_name: str = "<memory>") -> ApiDocument:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            try:
                import yaml
                data = yaml.safe_load(text)
            except ImportError as exc:
                raise OpenApiParseError("YAML 文件需要安装 PyYAML") from exc
            except Exception as exc:
                raise OpenApiParseError(f"JSON/YAML 格式无效：{exc}") from exc
        if not isinstance(data, dict):
            raise OpenApiParseError("接口文档根节点必须是对象")
        return self.parse_dict(data, source_name)

    def parse_dict(self, data: dict[str, Any], source_name: str = "<memory>") -> ApiDocument:
        spec = str(data.get("openapi") or data.get("swagger") or "")
        if not spec:
            raise OpenApiParseError("不是 OpenAPI/Swagger 文档：缺少 openapi 或 swagger 字段")
        paths = data.get("paths")
        if not isinstance(paths, dict):
            raise OpenApiParseError("接口文档缺少 paths 对象")

        is_swagger = spec.startswith("2.")
        endpoints: list[ApiEndpoint] = []
        global_security = data.get("security") or []
        for route, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            common_params = path_item.get("parameters") or []
            for method, operation in path_item.items():
                if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                raw_params = [*common_params, *(operation.get("parameters") or [])]
                parameters, swagger_body = self._parameters(raw_params, data)
                request_body = self._resolve_local_references(operation.get("requestBody") or swagger_body, data)
                tags = operation.get("tags") or ["未分组"]
                endpoints.append(
                    ApiEndpoint(
                        method=method.upper(),
                        path=str(route),
                        summary=str(operation.get("summary") or operation.get("description") or ""),
                        operation_id=str(operation.get("operationId") or ""),
                        module=str(tags[0]),
                        parameters=parameters,
                        request_body=request_body if isinstance(request_body, dict) else {},
                        responses=operation.get("responses") or {},
                        security=operation.get("security", global_security) or [],
                        source="swagger" if is_swagger else "openapi",
                        source_location=f"{source_name}#/paths/{route}/{method}",
                    )
                )
        info = data.get("info") or {}
        security_schemes = (
            (data.get("securityDefinitions") or {})
            if is_swagger
            else ((data.get("components") or {}).get("securitySchemes") or {})
        )
        return ApiDocument(
            title=str(info.get("title") or Path(source_name).stem),
            version=str(info.get("version") or ""),
            specification=f"Swagger {spec}" if is_swagger else f"OpenAPI {spec}",
            base_urls=self._base_urls(data, is_swagger),
            endpoints=endpoints,
            security_schemes=security_schemes,
        )

    @classmethod
    def _parameters(cls, items: list[Any], document: dict[str, Any]) -> tuple[list[ApiParameter], dict[str, Any]]:
        result: list[ApiParameter] = []
        body: dict[str, Any] = {}
        for item in items:
            item = cls._resolve_local_references(item, document)
            if not isinstance(item, dict):
                continue
            location = str(item.get("in") or "")
            if location == "body":
                body = {
                    "required": bool(item.get("required")),
                    "content": {"application/json": {"schema": cls._resolve_local_references(item.get("schema") or {}, document)}},
                }
                continue
            schema = item.get("schema") or {
                key: item[key]
                for key in ("type", "format", "enum", "minimum", "maximum", "minLength", "maxLength")
                if key in item
            }
            result.append(
                ApiParameter(
                    name=str(item.get("name") or ""),
                    location=location,
                    required=bool(item.get("required")) or location == "path",
                    schema=cls._resolve_local_references(schema, document),
                    description=str(item.get("description") or ""),
                    example=item.get("example"),
                )
            )
        return result, body

    @classmethod
    def _resolve_local_references(cls, value: Any, document: dict[str, Any], seen: frozenset[str] = frozenset()) -> Any:
        """Inline local OpenAPI refs so the debugger can render request fields."""
        if isinstance(value, list):
            return [cls._resolve_local_references(item, document, seen) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/") and reference not in seen:
            target: Any = document
            for part in reference[2:].split("/"):
                if not isinstance(target, dict):
                    target = None
                    break
                target = target.get(part.replace("~1", "/").replace("~0", "~"))
            if isinstance(target, dict):
                overrides = {key: item for key, item in value.items() if key != "$ref"}
                return cls._resolve_local_references({**target, **overrides}, document, seen | {reference})
        return {key: cls._resolve_local_references(item, document, seen) for key, item in value.items()}

    @staticmethod
    def _base_urls(data: dict[str, Any], is_swagger: bool) -> list[str]:
        if not is_swagger:
            return [str(x["url"]) for x in data.get("servers", []) if isinstance(x, dict) and x.get("url")]
        host = data.get("host")
        if not host:
            return []
        schemes = data.get("schemes") or ["https"]
        base_path = data.get("basePath") or ""
        return [f"{scheme}://{host}{base_path}" for scheme in schemes]
