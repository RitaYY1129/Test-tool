from __future__ import annotations

from dataclasses import dataclass

from testpilot.domain.api import ApiDocument


@dataclass(frozen=True, slots=True)
class CompletenessReport:
    endpoint_count: int
    module_count: int
    missing_base_url: int
    missing_request_example: int
    missing_response_schema: int
    missing_auth: int
    score: int
    level: str
    suggestions: tuple[str, ...]


def check_completeness(document: ApiDocument) -> CompletenessReport:
    endpoints = document.endpoints
    no_example = sum(not _has_request_example(e.request_body, e.parameters) for e in endpoints)
    no_response = sum(not _has_response_schema(e.responses) for e in endpoints)
    no_auth = sum(not e.security and not document.security_schemes for e in endpoints)
    no_base = len(endpoints) if not document.base_urls else 0
    total_checks = max(1, len(endpoints) * 4)
    missing = no_example + no_response + no_auth + no_base
    score = max(0, round(100 * (total_checks - missing) / total_checks))
    level = "完整" if score >= 85 else "基本完整" if score >= 65 else "需补充"
    suggestions: list[str] = []
    if no_base:
        suggestions.append("补充测试环境 Base URL")
    if no_example:
        suggestions.append("补充请求示例或字段 example/default")
    if no_response:
        suggestions.append("补充成功响应 Schema")
    if no_auth:
        suggestions.append("明确接口是否需要鉴权及鉴权方式")
    if not endpoints:
        suggestions.append("文档中未识别到可测试的 HTTP 接口")
    return CompletenessReport(
        endpoint_count=len(endpoints),
        module_count=len({e.module for e in endpoints}),
        missing_base_url=no_base,
        missing_request_example=no_example,
        missing_response_schema=no_response,
        missing_auth=no_auth,
        score=score,
        level=level,
        suggestions=tuple(suggestions),
    )


def _has_request_example(body: dict, parameters: list) -> bool:
    if any(p.example is not None or "example" in p.schema or "default" in p.schema for p in parameters):
        return True
    content = body.get("content", {}) if isinstance(body, dict) else {}
    return any(
        isinstance(media, dict) and ("example" in media or "examples" in media)
        for media in content.values()
    )


def _has_response_schema(responses: dict) -> bool:
    for status, response in responses.items():
        if not str(status).startswith("2") or not isinstance(response, dict):
            continue
        if response.get("schema"):
            return True
        if any(isinstance(media, dict) and media.get("schema") for media in response.get("content", {}).values()):
            return True
    return False

