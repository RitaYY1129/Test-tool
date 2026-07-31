from __future__ import annotations

import json
import re
from pathlib import Path

from testpilot.domain.api import ApiDocument, ApiEndpoint, ApiParameter


HTTP_ATTRIBUTE = re.compile(
    r'\[Http(Get|Post|Put|Patch|Delete|Head|Options)(?:\s*\(\s*"([^"]*)"\s*\))?[^\]]*\]',
    re.IGNORECASE,
)
CLASS_DECLARATION = re.compile(r'\bclass\s+(\w+Controller)\s*:\s*ControllerBase')
ROUTE_ATTRIBUTE = re.compile(r'\[Route\s*\(\s*"([^"]*)"\s*\)\]')


class AspNetCoreParser:
    """Static ASP.NET Core controller parser with source-level evidence."""

    def parse_directory(self, directory: str | Path) -> ApiDocument:
        root = Path(directory).resolve()
        if not root.is_dir():
            raise ValueError("源码目录不存在")
        schemas = self._collect_schemas(root)
        endpoints: list[ApiEndpoint] = []
        for path in root.rglob("*Controller.cs"):
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            class_match = CLASS_DECLARATION.search(text)
            if not class_match or "[ApiController]" not in text:
                continue
            controller_name = class_match.group(1).removesuffix("Controller")
            class_prefix = text[:class_match.start()]
            route_matches = list(ROUTE_ATTRIBUTE.finditer(class_prefix))
            prefix = route_matches[-1].group(1) if route_matches else ""
            prefix = prefix.replace("[controller]", controller_name).replace("[action]", "")
            class_secured = bool(re.search(r"\[(?:Authorize|Permission)(?:\(|\])", class_prefix))

            for attribute in HTTP_ATTRIBUTE.finditer(text):
                signature = self._signature_after(text, attribute.end())
                if not signature:
                    continue
                method_name, parameters_text = signature
                nearby = text[max(class_match.end(), attribute.start() - 700):attribute.start()]
                after_attribute = text[attribute.end():attribute.end() + 350]
                method_annotations = after_attribute.split("public", 1)[0]
                method_route = attribute.group(2) or self._nearby_route(after_attribute)
                method_route = method_route.replace("[action]", method_name)
                full_path = self._combine_route(prefix, method_route)
                parameters, request_body = self._parameters(
                    parameters_text, schemas, full_path
                )
                anonymous = "[AllowAnonymous]" in method_annotations
                secured = (class_secured or bool(re.search(
                    r"\[(?:Authorize|Permission)(?:\(|\])", nearby + method_annotations
                ))) and not anonymous
                line = text.count("\n", 0, attribute.start()) + 1
                endpoints.append(ApiEndpoint(
                    method=attribute.group(1).upper(),
                    path=full_path,
                    summary=self._summary(nearby) or method_name,
                    operation_id=method_name,
                    module=controller_name,
                    parameters=parameters,
                    request_body=request_body,
                    responses=self._responses(text[attribute.start():attribute.start() + 3000]),
                    security=[{"bearerAuth": []}] if secured else [],
                    source="source_code",
                    source_location=f"{path.relative_to(root)}:{line}",
                ))

        base_urls = self._base_urls(root)
        return ApiDocument(
            root.name, "", "ASP.NET Core source", base_urls, endpoints,
            {"bearerAuth": {"type": "http", "scheme": "bearer"}},
        )

    @staticmethod
    def _signature_after(text: str, offset: int) -> tuple[str, str] | None:
        window = text[offset:offset + 2500]
        match = re.search(
            r'\bpublic\s+(?:async\s+)?(?:[\w.<>,?\[\]]+\s+)+(\w+)\s*\(([\s\S]*?)\)\s*(?:\{|=>)',
            window,
        )
        return (match.group(1), match.group(2)) if match else None

    @staticmethod
    def _nearby_route(text: str) -> str:
        match = ROUTE_ATTRIBUTE.search(text)
        return match.group(1) if match and match.start() < 180 else ""

    @staticmethod
    def _combine_route(prefix: str, route: str) -> str:
        parts = [part.strip("/") for part in (prefix, route) if part.strip("/")]
        return "/" + "/".join(parts) if parts else "/"

    @staticmethod
    def _summary(text: str) -> str:
        matches = re.findall(r"///\s*<summary>\s*([\s\S]*?)\s*</summary>", text)
        if not matches:
            return ""
        return re.sub(r"\s*///\s*", " ", matches[-1]).strip()

    @classmethod
    def _parameters(
        cls, raw: str, schemas: dict[str, dict], route: str
    ) -> tuple[list[ApiParameter], dict]:
        output: list[ApiParameter] = []
        request_body: dict = {}
        for item in cls._split_parameters(raw):
            match = re.search(
                r'(?P<attrs>(?:\[[^\]]+\]\s*)*)(?P<type>[\w.<>,?\[\]]+)\s+'
                r'(?P<name>\w+)(?:\s*=\s*(?P<default>[^,]+))?',
                item.strip(),
            )
            if not match:
                continue
            attrs, cs_type, name, default = (
                match.group("attrs"), match.group("type"),
                match.group("name"), match.group("default"),
            )
            clean_type = cs_type.rstrip("?")
            if "[FromBody" in attrs:
                request_body = {
                    "required": default is None and "?" not in cs_type,
                    "content": {
                        "application/json": {
                            "schema": schemas.get(clean_type, {"type": "object"})
                        }
                    },
                }
                continue
            location = "query"
            if "[FromRoute" in attrs or "{" + name + "}" in route:
                location = "path"
            elif "[FromHeader" in attrs:
                location = "header"
            elif "[FromForm" in attrs:
                location = "form"
            elif "[FromQuery" not in attrs and clean_type in schemas:
                request_body = {
                    "required": default is None and "?" not in cs_type,
                    "content": {
                        "application/json": {"schema": schemas[clean_type]}
                    },
                }
                continue
            alias = re.search(r'Name\s*=\s*"([^"]+)"', attrs)
            output.append(ApiParameter(
                alias.group(1) if alias else name,
                location,
                location == "path" or (default is None and "?" not in cs_type),
                {"type": _json_type(clean_type)},
            ))
        return output, request_body

    @staticmethod
    def _split_parameters(raw: str) -> list[str]:
        output, current, depth = [], [], 0
        for char in raw:
            if char in "<[(":
                depth += 1
            elif char in ">])":
                depth = max(0, depth - 1)
            if char == "," and depth == 0:
                output.append("".join(current))
                current = []
            else:
                current.append(char)
        if current:
            output.append("".join(current))
        return output

    @staticmethod
    def _collect_schemas(root: Path) -> dict[str, dict]:
        schemas: dict[str, dict] = {}
        class_pattern = re.compile(
            r'\b(?:class|record)\s+(\w+)[^{]*\{([\s\S]*?)(?=\n\}|\Z)'
        )
        property_pattern = re.compile(
            r'((?:\[[^\]]+\]\s*)*)public\s+([\w.<>,?\[\]]+)\s+(\w+)\s*'
            r'\{\s*get;\s*set;\s*\}(?:\s*=\s*[^;]+;)?'
        )
        for path in root.rglob("*.cs"):
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            for class_match in class_pattern.finditer(text):
                required, properties = [], {}
                for prop in property_pattern.finditer(class_match.group(2)):
                    attrs, cs_type, name = prop.groups()
                    schema = {"type": _json_type(cs_type)}
                    length = re.search(r'\[(?:StringLength|MaxLength)\((\d+)', attrs)
                    if length:
                        schema["maxLength"] = int(length.group(1))
                    range_value = re.search(r'\[Range\(([-\d.]+)\s*,\s*([-\d.]+)', attrs)
                    if range_value:
                        schema.update({
                            "minimum": float(range_value.group(1)),
                            "maximum": float(range_value.group(2)),
                        })
                    if "[Required" in attrs or (
                        "?" not in cs_type and _is_scalar_or_string(cs_type)
                    ):
                        required.append(name)
                    properties[name] = schema
                schemas[class_match.group(1)] = {
                    "type": "object", "properties": properties, "required": required
                }
        return schemas

    @staticmethod
    def _responses(window: str) -> dict:
        responses = {"200": {"description": "源码默认成功响应"}}
        if "Result.Error" in window or "BadRequest(" in window:
            responses["400"] = {"description": "业务校验或请求错误"}
        if "Unauthorized(" in window:
            responses["401"] = {"description": "未认证"}
        if "NotFound(" in window:
            responses["404"] = {"description": "资源不存在"}
        return responses

    @staticmethod
    def _base_urls(root: Path) -> list[str]:
        for path in root.rglob("appsettings.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                url = data.get("Server", {}).get("Url")
                if url:
                    return [str(url)]
            except (OSError, ValueError, TypeError):
                pass
        return []


def _json_type(cs_type: str) -> str:
    lowered = cs_type.lower()
    if lowered in {"bool", "boolean"}:
        return "boolean"
    if any(x in lowered for x in ("list<", "ienumerable<", "icollection<", "[]")):
        return "array"
    if any(x in lowered for x in ("int", "long", "short", "decimal", "double", "float")):
        return "number"
    if any(x in lowered for x in ("datetime", "dateonly", "guid", "string", "char")):
        return "string"
    return "object"


def _is_scalar_or_string(cs_type: str) -> bool:
    return _json_type(cs_type) in {"string", "number", "boolean"}
