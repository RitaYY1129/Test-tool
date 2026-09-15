from pathlib import Path

import pytest

from testpilot.engines.suite_catalog import SuiteCatalogError, load_suite_catalog


def _manifest(root: Path, name: str = "smoke.json") -> None:
    target = root / "examples" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}", encoding="utf-8")


def _catalog(root: Path, content: str) -> None:
    target = root / "config" / "test_suites.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_catalog_loads_registered_suite(tmp_path: Path) -> None:
    _manifest(tmp_path)
    _catalog(
        tmp_path,
        """schema_version: 1
suites:
  - id: readonly-smoke
    name: 只读 Smoke
    module: 现场作业
    manifest: examples/smoke.json
    description: 核心只读接口
    risk: readonly
    timeout_seconds: 120
""",
    )

    suites = load_suite_catalog(tmp_path)

    assert [(suite.id, suite.module, suite.manifest) for suite in suites] == [
        ("readonly-smoke", "现场作业", "examples/smoke.json")
    ]


def test_catalog_rejects_manifest_outside_runner_directory(tmp_path: Path) -> None:
    _catalog(
        tmp_path,
        """schema_version: 1
suites:
  - id: unsafe
    name: 不安全
    module: 现场作业
    manifest: ../outside.json
    description: should fail
    risk: readonly
""",
    )

    with pytest.raises(SuiteCatalogError, match="相对路径"):
        load_suite_catalog(tmp_path)


def test_catalog_requires_approval_for_mutation(tmp_path: Path) -> None:
    _manifest(tmp_path)
    _catalog(
        tmp_path,
        """schema_version: 1
suites:
  - id: flow
    name: 完整 Flow
    module: 现场作业
    manifest: examples/smoke.json
    description: 可清理写入
    risk: mutation
    approval_required: false
""",
    )

    with pytest.raises(SuiteCatalogError, match="approval_required"):
        load_suite_catalog(tmp_path)


def test_catalog_uses_legacy_suites_during_migration(tmp_path: Path) -> None:
    suites = load_suite_catalog(tmp_path)

    assert [suite.id for suite in suites] == ["readonly-smoke", "offline-unit"]
