from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ApiParameter:
    name: str
    location: str
    required: bool = False
    schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    example: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "location": self.location,
            "required": self.required,
            "schema": self.schema,
            "description": self.description,
            "example": self.example,
        }


@dataclass(slots=True)
class ApiEndpoint:
    method: str
    path: str
    summary: str = ""
    operation_id: str = ""
    module: str = "未分组"
    parameters: list[ApiParameter] = field(default_factory=list)
    request_body: dict[str, Any] = field(default_factory=dict)
    responses: dict[str, Any] = field(default_factory=dict)
    security: list[dict[str, Any]] = field(default_factory=list)
    source: str = "openapi"
    source_location: str = ""

    @property
    def key(self) -> str:
        return f"{self.method.upper()} {self.path}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method.upper(),
            "path": self.path,
            "summary": self.summary,
            "operation_id": self.operation_id,
            "module": self.module,
            "parameters": [p.to_dict() for p in self.parameters],
            "request_body": self.request_body,
            "responses": self.responses,
            "security": self.security,
            "source": self.source,
            "source_location": self.source_location,
        }


@dataclass(slots=True)
class ApiDocument:
    title: str
    version: str
    specification: str
    base_urls: list[str]
    endpoints: list[ApiEndpoint]
    security_schemes: dict[str, Any] = field(default_factory=dict)

