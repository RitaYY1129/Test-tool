from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


class ReplayPackageError(ValueError):
    pass


def export_replay_package(output_path: str | Path, project: dict[str, Any], workflow: dict[str, Any] | None = None,
                          cases: list[dict] | None = None, environment: dict | None = None,
                          include_secrets: bool = False) -> Path:
    """Export a portable, redacted test package; secrets are excluded by default."""
    path = Path(output_path); path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": "1.0", "project": project, "workflow": workflow or {}, "cases": cases or [], "environment": environment or {}}
    if not include_secrets:
        payload["environment"].pop("secrets_encrypted", None); payload["environment"].pop("token", None); payload["environment"].pop("Authorization", None)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def import_replay_package(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise ReplayPackageError("重放包不存在")
    with zipfile.ZipFile(path) as archive:
        if "manifest.json" not in archive.namelist():
            raise ReplayPackageError("重放包缺少 manifest.json")
        names = archive.namelist()
        if any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
            raise ReplayPackageError("重放包包含不安全路径")
        try:
            payload = json.loads(archive.read("manifest.json").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReplayPackageError("重放包 manifest 无效") from exc
    if payload.get("version") != "1.0" or not isinstance(payload.get("project"), dict):
        raise ReplayPackageError("不支持的重放包版本或结构")
    return payload
