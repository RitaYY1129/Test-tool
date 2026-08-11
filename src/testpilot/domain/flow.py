from __future__ import annotations

"""Evidence-first business flow and data-flow primitives.

The UI and runners store JSON definitions, but this module keeps the shape
consistent and prevents AI guesses from silently becoming verified facts.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable


EVIDENCE_LEVELS = {"observed", "static", "inferred", "manual"}
NODE_KINDS = {
    "external_input", "api", "controller", "service", "repository", "database",
    "cache", "file", "message", "scheduler", "external_system",
}
EDGE_KINDS = {"reads", "writes", "publishes", "calls", "transforms", "compensates"}


@dataclass(slots=True)
class FlowEvidence:
    evidence_type: str
    locator: str = ""
    detail: str = ""
    confidence: str = "static"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_type": self.evidence_type,
            "locator": self.locator,
            "detail": self.detail,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class FlowNode:
    key: str
    kind: str
    name: str
    visibility: str = "hidden"
    entities: list[str] = field(default_factory=list)
    evidence: list[FlowEvidence] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "kind": self.kind, "name": self.name,
            "visibility": self.visibility, "entities": self.entities,
            "evidence": [item.to_dict() for item in self.evidence],
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class FlowEdge:
    source: str
    target: str
    kind: str
    fields: dict[str, str] = field(default_factory=dict)
    condition: str = ""
    evidence: list[FlowEvidence] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source, "target": self.target, "kind": self.kind,
            "fields": self.fields, "condition": self.condition,
            "evidence": [item.to_dict() for item in self.evidence],
            "metadata": self.metadata,
        }


def validate_flow_model(model: dict[str, Any]) -> list[str]:
    """Return actionable validation errors without mutating the model."""
    errors: list[str] = []
    nodes = model.get("nodes") or []
    edges = model.get("edges") or []
    keys = {str(item.get("key")) for item in nodes if isinstance(item, dict)}
    if not isinstance(nodes, list):
        errors.append("nodes 必须是数组")
        nodes = []
    if not isinstance(edges, list):
        errors.append("edges 必须是数组")
        edges = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"节点 {index + 1} 必须是对象")
            continue
        if not node.get("key") or not node.get("name"):
            errors.append(f"节点 {index + 1} 缺少 key/name")
        if node.get("kind") not in NODE_KINDS:
            errors.append(f"节点 {node.get('key', index + 1)} 的 kind 无效")
        if node.get("visibility", "hidden") not in {"visible", "hidden", "unknown"}:
            errors.append(f"节点 {node.get('key', index + 1)} 的 visibility 无效")
        for evidence in node.get("evidence") or []:
            if evidence.get("confidence") not in EVIDENCE_LEVELS:
                errors.append(f"节点 {node.get('key')} 的证据可信度无效")
    if len(keys) != len(nodes):
        errors.append("节点 key 必须唯一且不能为空")
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"边 {index + 1} 必须是对象")
            continue
        if edge.get("source") not in keys or edge.get("target") not in keys:
            errors.append(f"边 {index + 1} 引用了不存在的节点")
        if edge.get("kind") not in EDGE_KINDS:
            errors.append(f"边 {index + 1} 的 kind 无效")
        for evidence in edge.get("evidence") or []:
            if evidence.get("confidence") not in EVIDENCE_LEVELS:
                errors.append(f"边 {index + 1} 的证据可信度无效")
    return errors


def build_flow_model(analysis: dict[str, Any], workflow: dict[str, Any] | None = None,
                     manual: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a conservative flow graph from current source evidence.

    Inferred database nodes are explicitly marked ``inferred`` and ``unknown``
    visibility; users must confirm them before execution.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    def metadata(item: dict[str, Any], key: str = "metadata") -> dict[str, Any]:
        value = item.get(key)
        if isinstance(value, dict):
            return value
        raw = item.get(f"{key}_json")
        if isinstance(raw, str):
            try:
                import json
                return json.loads(raw or "{}")
            except (TypeError, ValueError):
                return {}
        return {}

    for item in analysis.get("symbols", []):
        kind = "database" if item.get("symbol_type") == "entity" else "service" if str(item.get("qualified_name", "")).endswith(("Service", "Manager", "Handler")) else "repository" if str(item.get("qualified_name", "")).endswith(("Repository", "Dao")) else "service"
        nodes.append(FlowNode(
            key=f"symbol:{item['qualified_name']}", kind=kind, name=item["qualified_name"],
            visibility="hidden", entities=[item["qualified_name"]] if kind == "database" else [],
            evidence=[FlowEvidence("source_symbol", f"{item.get('file_path','')}:{item.get('line_start',0)}", confidence="static", metadata=metadata(item))],
        ).to_dict())
    for endpoint in analysis.get("evidence", []):
        details = metadata(endpoint, "details")
        key = f"api:{details.get('method','GET')}:{details.get('path','')}"
        nodes.append(FlowNode(
            key=key, kind="api", name=f"{details.get('method','GET')} {details.get('path','')}",
            visibility="visible", evidence=[FlowEvidence("endpoint_route", f"{endpoint.get('file_path','')}:{endpoint.get('line_start',0)}", confidence="static", metadata=details)],
        ).to_dict())
    seen = {item["key"] for item in nodes}
    for item in analysis.get("edges", []):
        source = f"symbol:{item.get('source_symbol')}"
        target = f"symbol:{item.get('target_symbol')}"
        if source not in seen:
            nodes.append(FlowNode(source, "service", item.get("source_symbol", "未知"), evidence=[FlowEvidence("dependency_reference", item.get("file_path", ""), confidence="inferred")]).to_dict()); seen.add(source)
        if target not in seen:
            is_db = str(item.get("target_symbol", "")).startswith("db:")
            target_name = str(item.get("target_symbol", "未知")).removeprefix("db:")
            nodes.append(FlowNode(target, "database" if is_db else "service", target_name, visibility="hidden", evidence=[FlowEvidence("dependency_reference", item.get("file_path", ""), confidence="inferred")]).to_dict()); seen.add(target)
        edge_metadata = metadata(item)
        edge_kind = "writes" if item.get("edge_type") == "writes" else "calls"
        edges.append(FlowEdge(source, target, edge_kind, evidence=[FlowEvidence("dependency_reference", f"{item.get('file_path','')}:{item.get('line_start',0)}", confidence=edge_metadata.get("confidence", "inferred"), metadata=edge_metadata)]).to_dict())
    for node in list(nodes):
        if node["kind"] == "api":
            target = next((n for n in nodes if n["kind"] == "service"), None)
            if target:
                edges.append(FlowEdge(node["key"], target["key"], "calls", evidence=[FlowEvidence("endpoint_route", confidence="inferred")]).to_dict())
    result = {
        "version": "1.0",
        "visibility_policy": "visible_and_hidden",
        "nodes": nodes,
        "edges": edges,
        "state_transitions": (workflow or {}).get("state_transitions", []),
        "invariants": (workflow or {}).get("invariants", []),
        "database_changes": (workflow or {}).get("database_changes", []),
        "review_status": "draft",
        "evidence_summary": {"static": len(analysis.get("evidence", [])) + len(analysis.get("symbols", [])), "inferred": len(edges), "manual": 0, "observed": 0},
    }
    if manual:
        result.update(manual)
    errors = validate_flow_model(result)
    if errors:
        result["validation_errors"] = errors
    return result


def evidence_counts(model: dict[str, Any]) -> dict[str, int]:
    counts = {level: 0 for level in EVIDENCE_LEVELS}
    for container in (model.get("nodes") or []) + (model.get("edges") or []):
        for evidence in container.get("evidence") or []:
            level = evidence.get("confidence")
            if level in counts:
                counts[level] += 1
    return counts
