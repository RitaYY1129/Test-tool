from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


class SideEffectError(RuntimeError):
    pass


@dataclass(slots=True)
class FileChange:
    path: str
    change: str
    before_hash: str = ""
    after_hash: str = ""
    size_bytes: int = 0


class FileSideEffectObserver:
    """Observe files under an explicitly approved test directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise SideEffectError(f"文件副作用目录不存在：{self.root}")

    def snapshot(self) -> dict[str, dict[str, Any]]:
        result = {}
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root).as_posix()
            raw = path.read_bytes()
            result[relative] = {"hash": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
        return result

    @staticmethod
    def diff(before: dict, after: dict) -> list[dict]:
        changes = []
        for path in sorted(set(before) | set(after)):
            if path not in before:
                changes.append(asdict(FileChange(path, "created", after_hash=after[path]["hash"], size_bytes=after[path]["size_bytes"])))
            elif path not in after:
                changes.append(asdict(FileChange(path, "deleted", before_hash=before[path]["hash"])))
            elif before[path] != after[path]:
                changes.append(asdict(FileChange(path, "modified", before[path]["hash"], after[path]["hash"], after[path]["size_bytes"])))
        return changes


class MessageObserver:
    """Protocol-neutral event collector for queues or message-bus adapters."""

    def __init__(self):
        self.events: list[dict[str, Any]] = []

    def record(self, topic: str, payload: dict[str, Any], headers: dict[str, Any] | None = None):
        self.events.append({"topic": topic, "payload": payload, "headers": headers or {}})

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self.events)

    def find(self, topic: str | None = None, field: str | None = None, value: Any = None) -> list[dict[str, Any]]:
        result = [item for item in self.events if topic is None or item["topic"] == topic]
        if field is not None:
            result = [item for item in result if item.get("payload", {}).get(field) == value]
        return result
