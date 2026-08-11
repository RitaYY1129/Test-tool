from __future__ import annotations

import json
import os
import base64
import shutil
import subprocess
import tempfile
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from testpilot.model_providers.base import ModelProvider
from testpilot.model_providers.resilience import AIRequestCancelled, run_with_retry


def find_codex() -> str | None:
    """Return the official Codex executable.

    Prefer the npm CLI when it is available. It is the version that owns the
    current ChatGPT login; the desktop binary remains a fallback.
    """
    for name in ("codex.cmd", "codex"):
        found = shutil.which(name)
        if found:
            return found
    if os.name == "nt":
        desktop_bin = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
        if desktop_bin.is_dir():
            candidates = [item for item in desktop_bin.glob("*/codex.exe") if item.is_file()]
            if candidates:
                return str(max(candidates, key=lambda item: item.stat().st_mtime))
    return None


@dataclass(slots=True)
class CodexCliProvider(ModelProvider):
    project_path: str
    model: str = ""
    timeout: float = 180
    executable: str = ""
    retries: int = 1
    cancel_event: Event | None = None

    def _command(self) -> str:
        command = self.executable or find_codex()
        if not command:
            raise RuntimeError("未检测到 Codex CLI，请先安装 Codex。")
        return command

    @staticmethod
    def default_model() -> str:
        """Read the non-sensitive model preference from Codex configuration."""
        config_file = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
        try:
            config = tomllib.loads(config_file.read_text(encoding="utf-8"))
            return str(config.get("model") or "").strip()
        except (OSError, ValueError, tomllib.TOMLDecodeError):
            return ""

    def _selected_model(self) -> str:
        return self.model.strip() or self.default_model()

    def status(self) -> tuple[bool, str]:
        command = self._command()
        result = subprocess.run(
            [command, "login", "status"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
        message = (result.stdout or result.stderr).strip()
        return result.returncode == 0, message

    @staticmethod
    def account_identity() -> dict[str, str]:
        """Read only the public profile claims from Codex's local login token.

        Tokens are never returned or persisted by TestPilot.
        """
        root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        auth_file = root / "auth.json"
        try:
            payload = json.loads(auth_file.read_text(encoding="utf-8"))
            token = str((payload.get("tokens") or {}).get("id_token") or "")
            if token.count(".") < 2:
                return {}
            encoded = token.split(".")[1]
            encoded += "=" * (-len(encoded) % 4)
            claims = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
            return {
                "name": str(claims.get("name") or claims.get("preferred_username") or ""),
                "email": str(claims.get("email") or ""),
            }
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return {}

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
                self._command(), "exec", "--ephemeral", "--ignore-user-config", "--sandbox", "read-only",
                "--skip-git-repo-check", "--color", "never", "-C", str(root),
                "--output-schema", str(schema_path),
                "--output-last-message", str(output_path),
            ]
            if selected_model := self._selected_model():
                args.extend(["--model", selected_model])
            # Passing a source-rich prompt as a Windows command-line argument
            # easily exceeds CreateProcess' length limit (WinError 206).  Codex
            # accepts '-' as stdin, which also avoids quoting/cmd-shim issues.
            args.append("-")
            result = run_with_retry(
                lambda _attempt: self._run_process(args, prompt),
                self.retries, self.cancel_event,
            )
            if not output_path.exists():
                raise RuntimeError("Codex 未返回结构化结果。")
            return json.loads(output_path.read_text(encoding="utf-8"))

    def generate_chat(self, system_prompt: str, messages: list[dict[str, str]]) -> str:
        """Run a concise direct Codex conversation without JSON schema overhead."""
        root = Path(self.project_path).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("Codex source directory does not exist.")
        history = "\n\n".join(
            f"{'User' if item.get('role') == 'user' else 'Assistant'}: {item.get('content', '')}"
            for item in messages[-12:]
        )
        prompt = (
            f"{system_prompt}\n\n"
            "This is ordinary conversation. Answer the last user message naturally. Do not output JSON, "
            "do not claim commands or tests were executed. You may read the current project, but must not "
            "modify files, run the application, or send network requests.\n\n"
            f"Conversation:\n{history}"
        )
        args = [
            self._command(), "exec", "--ephemeral", "--ignore-user-config", "--sandbox", "read-only",
            "--skip-git-repo-check", "--color", "never", "--json", "-C", str(root),
        ]
        if selected_model := self._selected_model():
            args.extend(["--model", selected_model])
        # A direct prompt makes Codex finish after one turn.  Passing it via
        # stdin causes the CLI to stay in "additional input" mode on some
        # Windows builds even when the first reply has completed.
        args.append(prompt)
        result = run_with_retry(lambda _attempt: self._run_process(args, None), self.retries, self.cancel_event)
        for line in reversed((result.stdout or "").splitlines()):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item") if isinstance(event, dict) else None
            if isinstance(item, dict) and item.get("type") == "agent_message":
                reply = str(item.get("text") or "").strip()
                if reply:
                    return reply
        raise RuntimeError("Codex did not return a chat response.")

    def _run_process(self, args: list[str], prompt: str | None) -> subprocess.CompletedProcess:
        if self.cancel_event is None:
            try:
                if prompt is None:
                    result = subprocess.run(
                        args, stdin=subprocess.DEVNULL, capture_output=True,
                        text=True, encoding="utf-8", errors="replace", timeout=self.timeout,
                    )
                else:
                    result = subprocess.run(
                        args, input=prompt, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=self.timeout,
                    )
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError(
                    f"Codex 在 {int(self.timeout)} 秒内没有完成生成，本次尝试已终止。"
                ) from exc
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()[-4000:]
                raise RuntimeError(f"Codex 生成失败（退出码 {result.returncode}）。\n\n原始诊断：\n{detail}")
            return result
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP") else 0
        process = subprocess.Popen(
            args, stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", creationflags=creationflags,
        )
        # Codex accepts '-' from stdin.  It must see EOF after the one prompt;
        # otherwise it keeps waiting for "additional input" even after the model
        # has completed its response.  Repeated communicate(timeout=...) calls
        # do not close this pipe reliably on Windows.
        if prompt is not None:
            try:
                assert process.stdin is not None
                process.stdin.write(prompt)
                process.stdin.close()
            except (OSError, ValueError):
                self._stop_process(process)
                raise RuntimeError("无法向 Codex 写入对话请求。")
        started = time.monotonic()
        while True:
            if self.cancel_event and self.cancel_event.is_set():
                self._stop_process(process)
                raise AIRequestCancelled("AI 请求已取消。")
            remaining = self.timeout - (time.monotonic() - started)
            if remaining <= 0:
                self._stop_process(process)
                raise TimeoutError(
                    f"Codex 在 {int(self.timeout)} 秒内没有完成生成，本次尝试已终止。"
                )
            try:
                process.wait(timeout=min(0.25, remaining))
                stdout = process.stdout.read() if process.stdout else ""
                stderr = process.stderr.read() if process.stderr else ""
                result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
                if result.returncode != 0:
                    detail = (result.stderr or result.stdout).strip()[-4000:]
                    raise RuntimeError(
                        f"Codex 生成失败（退出码 {result.returncode}）。\n\n原始诊断：\n{detail}"
                    )
                return result
            except subprocess.TimeoutExpired:
                continue

    @staticmethod
    def _stop_process(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt" and getattr(process, "pid", None):
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True, text=True, timeout=5,
                )
                return
            except (OSError, subprocess.SubprocessError):
                pass
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
