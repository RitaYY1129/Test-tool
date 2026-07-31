from __future__ import annotations

import re
from pathlib import Path

from testpilot.domain.api import ApiDocument, ApiEndpoint, ApiParameter

CLASS_MAPPING = re.compile(r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']*)["\']')
METHOD_MAPPING = re.compile(
    r'@(Get|Post|Put|Patch|Delete)Mapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']*)["\']'
)
REQUEST_MAPPING = re.compile(
    r'@RequestMapping\s*\([^)]*?(?:value|path)\s*=\s*["\']([^"\']+)["\'][^)]*?method\s*=\s*RequestMethod\.(GET|POST|PUT|PATCH|DELETE)',
    re.DOTALL,
)


class SpringBootParser:
    """Conservative Spring MVC annotation parser with source evidence."""

    def parse_directory(self, directory: str | Path) -> ApiDocument:
        root = Path(directory).resolve()
        if not root.is_dir():
            raise ValueError("源码目录不存在")
        endpoints: list[ApiEndpoint] = []
        schemas = self._collect_schemas(root)
        for path in root.rglob("*.java"):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="gb18030", errors="replace")
            if "@RestController" not in text and "@Controller" not in text:
                continue
            prefix_match = CLASS_MAPPING.search(text)
            prefix = prefix_match.group(1) if prefix_match else ""
            secured_class = bool(re.search(r"@(PreAuthorize|Secured|RolesAllowed)", text))
            for method, route, offset in self._mappings(text):
                window = text[offset:offset + 1500]
                signature_match = re.search(r"(?:public|protected|private)\s+[\s\S]*?\)\s*\{", window)
                signature = signature_match.group(0) if signature_match else window[:500]
                params = self._parameters(signature)
                request_body = self._request_body(signature, schemas)
                security = [{"springSecurity": []}] if secured_class or re.search(r"@(PreAuthorize|Secured|RolesAllowed)", text[max(0, offset-500):offset]) else []
                full_path = "/" + "/".join(x.strip("/") for x in (prefix, route) if x.strip("/"))
                line = text.count("\n", 0, offset) + 1
                endpoints.append(ApiEndpoint(
                    method=method, path=full_path or "/", summary=self._method_name(signature),
                    module=path.stem, parameters=params, request_body=request_body,
                    responses=self._exception_responses(window), security=security, source="source_code",
                    source_location=f"{path.relative_to(root)}:{line}",
                ))
        return ApiDocument(root.name, "", "Spring Boot source", [], endpoints)

    @staticmethod
    def _collect_schemas(root: Path) -> dict[str, dict]:
        schemas: dict[str, dict] = {}
        for path in root.rglob("*.java"):
            text = path.read_text(encoding="utf-8", errors="replace")
            enum_match = re.search(r"\benum\s+(\w+)\s*\{([^}]+)", text, re.DOTALL)
            if enum_match:
                values = [x.strip().split("(")[0] for x in enum_match.group(2).split(",") if re.match(r"\s*[A-Z][A-Z0-9_]*", x)]
                schemas[enum_match.group(1)] = {"type": "string", "enum": values}
            class_match = re.search(r"\b(?:class|record)\s+(\w+)", text)
            if not class_match:
                continue
            required, properties = [], {}
            field_pattern = re.compile(
                r"((?:@[\w.]+(?:\([^)]*\))?\s*)*)\b(?:private|public|protected)?\s*"
                r"([\w.<>?\[\]]+)\s+(\w+)\s*(?:[;,)]|=)"
            )
            for field in field_pattern.finditer(text):
                annotations, java_type, name = field.groups()
                if name in {"class", "interface"}:
                    continue
                schema = {"type": _json_type(java_type)}
                size = re.search(r"@Size\s*\([^)]*min\s*=\s*(\d+)[^)]*max\s*=\s*(\d+)", annotations)
                if size:
                    schema.update({"minLength": int(size.group(1)), "maxLength": int(size.group(2))})
                minimum = re.search(r"@Min\s*\(\s*(?:value\s*=\s*)?(\d+)", annotations)
                maximum = re.search(r"@Max\s*\(\s*(?:value\s*=\s*)?(\d+)", annotations)
                if minimum: schema["minimum"] = int(minimum.group(1))
                if maximum: schema["maximum"] = int(maximum.group(1))
                if java_type in schemas and "enum" in schemas[java_type]:
                    schema = schemas[java_type]
                if re.search(r"@(NotNull|NotBlank|NotEmpty)", annotations):
                    required.append(name)
                properties[name] = schema
            schemas[class_match.group(1)] = {"type": "object", "properties": properties, "required": required}
        return schemas

    @staticmethod
    def _request_body(signature: str, schemas: dict[str, dict]) -> dict:
        match = re.search(r"@RequestBody\s+(?:@Valid\s+)?(?:@Validated\s+)?(\w+)", signature)
        if not match:
            match = re.search(r"@Valid\s+@RequestBody\s+(\w+)", signature)
        if not match:
            return {}
        schema = schemas.get(match.group(1), {"type": "object"})
        return {"required": True, "content": {"application/json": {"schema": schema}}}

    @staticmethod
    def _exception_responses(window: str) -> dict:
        responses = {"200": {"description": "源码默认成功响应"}}
        mappings = {
            "IllegalArgumentException": "400", "AccessDeniedException": "403",
            "NotFoundException": "404", "ConflictException": "409",
        }
        for exception, status in mappings.items():
            if exception in window:
                responses[status] = {"description": f"显式异常：{exception}"}
        return responses

    @staticmethod
    def _mappings(text: str):
        result = [(m.group(1).upper(), m.group(2) or "", m.start()) for m in METHOD_MAPPING.finditer(text)]
        result.extend((m.group(2), m.group(1), m.start()) for m in REQUEST_MAPPING.finditer(text))
        return sorted(result, key=lambda x: x[2])

    @staticmethod
    def _parameters(signature: str) -> list[ApiParameter]:
        output = []
        pattern = re.compile(
            r'@(RequestParam|PathVariable|RequestHeader)\s*(?:\(([^)]*)\))?\s+'
            r'(?:@[\w.]+(?:\([^)]*\))?\s+)*([\w<>, ?.\[\]]+)\s+(\w+)'
        )
        locations = {"RequestParam": "query", "PathVariable": "path", "RequestHeader": "header"}
        for match in pattern.finditer(signature):
            annotation, options, java_type, variable = match.groups()
            name_match = re.search(r'(?:value|name)\s*=\s*["\']([^"\']+)', options or "")
            required = annotation == "PathVariable" or "required = false" not in (options or "")
            output.append(ApiParameter(
                name_match.group(1) if name_match else variable, locations[annotation], required,
                {"type": _json_type(java_type.strip())},
            ))
        return output

    @staticmethod
    def _method_name(signature: str) -> str:
        match = re.search(r'\b(\w+)\s*\([^)]*$', signature.strip())
        return match.group(1) if match else ""


def _json_type(java_type: str) -> str:
    lowered = java_type.lower()
    if any(x in lowered for x in ("int", "long", "short", "bigdecimal", "double", "float")):
        return "number"
    if "bool" in lowered:
        return "boolean"
    if any(x in lowered for x in ("list", "set", "[]")):
        return "array"
    return "string"
