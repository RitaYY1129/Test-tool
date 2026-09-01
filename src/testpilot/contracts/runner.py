from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"
CASE_STATUSES = {"passed", "failed", "error", "skipped", "blocked"}
RUN_STATUSES = CASE_STATUSES | {"running", "queued", "cancelled"}
RETRY_POLICIES = {"none", "read_only_only"}


class ContractError(ValueError):
    """A platform/runner payload does not conform to the versioned contract."""


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{key} 必须是非空字符串")
    return value.strip()


def _mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, Mapping):
        raise ContractError(f"{key} 必须是对象")
    return value


@dataclass(frozen=True, slots=True)
class RunSelection:
    paths: tuple[str, ...] = ()
    markers: tuple[str, ...] = ()
    case_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RunSelection":
        def values(key: str) -> tuple[str, ...]:
            value = raw.get(key, [])
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                raise ContractError(f"selection.{key} 必须是非空字符串数组")
            return tuple(item.strip() for item in value)

        selection = cls(paths=values("paths"), markers=values("markers"), case_ids=values("case_ids"))
        if not (selection.paths or selection.markers or selection.case_ids):
            raise ContractError("selection 至少要指定 paths、markers 或 case_ids 之一")
        return selection


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    allow_mutation: bool = False
    timeout_seconds: int = 1800
    parallel_workers: int = 1
    retry_policy: str = "read_only_only"

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ExecutionPolicy":
        timeout = raw.get("timeout_seconds", 1800)
        workers = raw.get("parallel_workers", 1)
        retry_policy = raw.get("retry_policy", "read_only_only")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
            raise ContractError("policy.timeout_seconds 必须是正整数")
        if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 64:
            raise ContractError("policy.parallel_workers 必须在 1 到 64 之间")
        if retry_policy not in RETRY_POLICIES:
            raise ContractError(f"policy.retry_policy 仅支持：{sorted(RETRY_POLICIES)}")
        allow_mutation = raw.get("allow_mutation", False)
        if not isinstance(allow_mutation, bool):
            raise ContractError("policy.allow_mutation 必须是布尔值")
        return cls(allow_mutation=allow_mutation, timeout_seconds=timeout, parallel_workers=workers, retry_policy=retry_policy)


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    project_id: str
    runner_name: str
    runner_version: str
    environment_id: str
    selection: RunSelection
    policy: ExecutionPolicy
    artifacts_dir: str
    schema_version: str = SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RunManifest":
        version = _required_text(raw, "schema_version")
        if version != SCHEMA_VERSION:
            raise ContractError(f"不支持的 Manifest schema_version：{version}")
        runner = _mapping(raw, "runner")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ContractError("metadata 必须是对象")
        return cls(
            run_id=_required_text(raw, "run_id"),
            project_id=_required_text(raw, "project_id"),
            runner_name=_required_text(runner, "name"),
            runner_version=_required_text(runner, "version"),
            environment_id=_required_text(raw, "environment_id"),
            selection=RunSelection.from_dict(_mapping(raw, "selection")),
            policy=ExecutionPolicy.from_dict(_mapping(raw, "policy")),
            artifacts_dir=_required_text(raw, "artifacts_dir"),
            schema_version=version,
            metadata=dict(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "runner": {"name": self.runner_name, "version": self.runner_version},
            "environment_id": self.environment_id,
            "selection": asdict(self.selection),
            "policy": asdict(self.policy),
            "artifacts_dir": self.artifacts_dir,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: str
    status: str
    summary: dict[str, int]
    cases: tuple[dict[str, Any], ...]
    artifacts: dict[str, str]
    started_at: str = ""
    finished_at: str = ""
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RunResult":
        version = _required_text(raw, "schema_version")
        if version != SCHEMA_VERSION:
            raise ContractError(f"不支持的 Result schema_version：{version}")
        status = _required_text(raw, "status")
        if status not in RUN_STATUSES:
            raise ContractError(f"无效的运行状态：{status}")
        summary = _mapping(raw, "summary")
        counts: dict[str, int] = {}
        for key in ("total", "passed", "failed", "error", "skipped"):
            value = summary.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ContractError(f"summary.{key} 必须是非负整数")
            counts[key] = value
        cases = raw.get("cases", [])
        if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
            raise ContractError("cases 必须是对象数组")
        for item in cases:
            case_status = _required_text(item, "status")
            if case_status not in CASE_STATUSES:
                raise ContractError(f"无效的用例状态：{case_status}")
        artifacts = raw.get("artifacts", {})
        if not isinstance(artifacts, Mapping) or not all(isinstance(key, str) and isinstance(value, str) for key, value in artifacts.items()):
            raise ContractError("artifacts 必须是字符串路径对象")
        return cls(
            run_id=_required_text(raw, "run_id"), status=status, summary=counts,
            cases=tuple(dict(item) for item in cases), artifacts=dict(artifacts),
            started_at=str(raw.get("started_at") or ""), finished_at=str(raw.get("finished_at") or ""),
            schema_version=version,
        )

    @classmethod
    def queued(cls, manifest: RunManifest) -> "RunResult":
        timestamp = datetime.now().isoformat(timespec="seconds")
        return cls(manifest.run_id, "queued", {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0}, (), {}, timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "run_id": self.run_id, "status": self.status,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "summary": self.summary, "cases": list(self.cases), "artifacts": self.artifacts,
        }
