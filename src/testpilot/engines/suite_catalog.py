"""Load version-controlled external-runner suite definitions safely."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class SuiteCatalogError(ValueError):
    """Raised when a suite catalog is unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class TestSuite:
    """A selectable, version-controlled external Runner suite."""

    id: str
    name: str
    module: str
    manifest: str
    description: str
    risk: str
    timeout_seconds: int
    approval_required: bool = False


_LEGACY_SUITES = (
    TestSuite(
        id="readonly-smoke",
        name="只读 Smoke（两个 GET 核心接口）",
        module="现场作业",
        manifest="examples/run-manifest.readonly-smoke.example.json",
        description="登录、核心 GET 接口与基础状态读取。",
        risk="readonly",
        timeout_seconds=120,
    ),
    TestSuite(
        id="offline-unit",
        name="离线 Unit（不访问服务）",
        module="通用内核",
        manifest="examples/run-manifest.unit.example.json",
        description="Runner、Schema、YAML 与通用组件测试，不访问服务。",
        risk="offline",
        timeout_seconds=300,
    ),
)


def load_suite_catalog(working_directory: Path) -> tuple[TestSuite, ...]:
    """Load config/test_suites.yaml without accepting arbitrary commands."""

    root = working_directory.resolve()
    catalog_path = root / "config" / "test_suites.yaml"
    if not catalog_path.is_file():
        return _LEGACY_SUITES
    try:
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SuiteCatalogError(f"无法读取测试套件目录：{exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise SuiteCatalogError("test_suites.yaml 必须是 schema_version: 1 的对象")
    suites = raw.get("suites")
    if not isinstance(suites, list) or not suites:
        raise SuiteCatalogError("test_suites.yaml.suites 必须是非空列表")
    loaded = tuple(_parse_suite(item, root) for item in suites)
    ids = [item.id for item in loaded]
    if len(ids) != len(set(ids)):
        raise SuiteCatalogError("test_suites.yaml 中存在重复 suite id")
    return loaded


def _parse_suite(raw: Any, root: Path) -> TestSuite:
    if not isinstance(raw, dict):
        raise SuiteCatalogError("每个测试套件必须是对象")

    def text(key: str) -> str:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SuiteCatalogError(f"测试套件缺少有效字段：{key}")
        return value.strip()

    manifest = text("manifest").replace("\\", "/")
    relative = Path(manifest)
    if relative.is_absolute() or ".." in relative.parts:
        raise SuiteCatalogError("测试套件 manifest 必须是工作目录内的相对路径")
    try:
        resolved_manifest = (root / relative).resolve()
        resolved_manifest.relative_to(root)
    except ValueError as exc:
        raise SuiteCatalogError("测试套件 manifest 超出 Runner 工作目录") from exc
    if not resolved_manifest.is_file():
        raise SuiteCatalogError(f"测试套件 manifest 不存在：{manifest}")

    timeout = raw.get("timeout_seconds", 300)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 7200:
        raise SuiteCatalogError("timeout_seconds 必须是 1 到 7200 的整数")
    risk = text("risk").lower()
    if risk not in {"offline", "readonly", "mutation"}:
        raise SuiteCatalogError("risk 必须是 offline、readonly 或 mutation")
    approval_required = raw.get("approval_required", risk == "mutation")
    if not isinstance(approval_required, bool):
        raise SuiteCatalogError("approval_required 必须是布尔值")
    if risk == "mutation" and not approval_required:
        raise SuiteCatalogError("mutation 套件必须设置 approval_required: true")
    return TestSuite(
        id=text("id"),
        name=text("name"),
        module=text("module"),
        manifest=manifest,
        description=text("description"),
        risk=risk,
        timeout_seconds=timeout,
        approval_required=approval_required,
    )
