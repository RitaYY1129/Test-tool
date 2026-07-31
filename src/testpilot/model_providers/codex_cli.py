from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testpilot.model_providers.base import ModelProvider


def find_codex() -> str | None:
    """Return the official Codex CLI launcher, including Windows' cmd shim."""
    for name in ("codex.cmd", "codex"):
        found = shutil.which(name)
        if found:
            return found
    return None


@dataclass(slots=True)
class CodexCliProvider(ModelProvider):
    project_path: str
    model: str = ""
    timeout: float = 600
    executable: str = ""

    def _command(self) -> str:
        command = self.executable or find_codex()
        if not command:
            raise RuntimeError("未检测到 Codex CLI，请先安装 Codex。")
        return command

    def status(self) -> tuple[bool, str]:
        command = self._command()
        result = subprocess.run(
            [command, "login", "status"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
        message = (result.stdout or result.stderr).strip()
        return result.returncode == 0, message

    def generate_structured(
        self, system_prompt: str, user_prompt: str, output_schema: dict
    ) -> dict[str, Any]:
        root = Path(self.project_path).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("Codex 源码目录不存在。")

        prompt = (
            f"{system_prompt}\n\n"
            "你只能读取并分析当前工作目录中的源码，不要修改文件、不要运行应用、"
            "不要发送网络或接口请求。最终只输出符合给定 JSON Schema 的数据。\n\n"
            f"任务输入：{user_prompt}"
        )
        with tempfile.TemporaryDirectory(prefix="testpilot-codex-") as temp:
            schema_path = Path(temp) / "schema.json"
            output_path = Path(temp) / "result.json"
            schema_path.write_text(
                json.dumps(output_schema, ensure_ascii=False), encoding="utf-8"
            )
            args = [
                self._command(), "exec", "--ephemeral", "--sandbox", "read-only",
                "--skip-git-repo-check", "--color", "never", "-C", str(root),
                "--output-schema", str(schema_path),
                "--output-last-message", str(output_path),
            ]
            if self.model.strip():
                args.extend(["--model", self.model.strip()])
            args.append(prompt)
            result = subprocess.run(
                args, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=self.timeout,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()[-4000:]
                raise RuntimeError(f"Codex 生成失败：{detail}")
            if not output_path.exists():
                raise RuntimeError("Codex 未返回结构化结果。")
            return json.loads(output_path.read_text(encoding="utf-8"))
