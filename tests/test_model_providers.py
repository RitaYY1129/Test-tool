from __future__ import annotations

import json
import subprocess
import base64
from threading import Event
from pathlib import Path
from types import SimpleNamespace

import pytest

from testpilot.model_providers.codex_cli import CodexCliProvider
from testpilot.model_providers.ollama import OllamaProvider
from testpilot.model_providers.resilience import AIRequestCancelled, run_with_retry


def test_codex_provider_uses_read_only_and_schema(tmp_path, monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["input"] = kwargs.get("input")
        output = Path(args[args.index("--output-last-message") + 1])
        output.write_text(json.dumps({"cases": []}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = CodexCliProvider(
        str(tmp_path), executable="codex.cmd"
    ).generate_structured("system", "input", {"type": "object"})

    assert result == {"cases": []}
    assert captured["args"][captured["args"].index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in captured["args"]
    assert "--output-schema" in captured["args"]
    assert captured["args"][-1] == "-"
    assert "任务输入：input" in captured["input"]
    assert "任务输入：input" not in captured["args"]


def test_ollama_lists_models(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "qwen3:8b"}]}

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: Response())
    assert OllamaProvider().list_models() == ["qwen3:8b"]


def test_ollama_structured_generation(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": '{"plan": {}, "cases": []}'}}

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: Response())
    result = OllamaProvider(model="qwen3:8b").generate_structured(
        "system", "input", {"type": "object"}
    )
    assert result["cases"] == []


def test_retry_recovers_from_transient_failure():
    attempts = []

    def operation(attempt):
        attempts.append(attempt)
        if attempt < 2:
            raise TimeoutError("temporary timeout")
        return "ok"

    assert run_with_retry(operation, retries=2, delay=0) == "ok"
    assert attempts == [1, 2]


def test_codex_cancel_terminates_running_process(tmp_path, monkeypatch):
    cancel = Event()
    processes = []

    class FakeProcess:
        returncode = None

        def __init__(self, *args, **kwargs):
            self.terminated = False
            self.stdin = type("Input", (), {"write": lambda _self, _value: None, "close": lambda _self: None})()
            self.stdout = type("Output", (), {"read": lambda _self: ""})()
            self.stderr = type("Output", (), {"read": lambda _self: ""})()
            processes.append(self)

        def wait(self, timeout=None):
            if self.returncode is not None:
                return self.returncode
            cancel.set()
            raise subprocess.TimeoutExpired("codex", timeout)

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -1

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(subprocess, "Popen", FakeProcess)
    provider = CodexCliProvider(
        str(tmp_path), executable="codex.cmd", cancel_event=cancel, retries=0,
    )
    with pytest.raises(AIRequestCancelled):
        provider.generate_structured("system", "input", {"type": "object"})
    assert processes and processes[0].terminated


def test_codex_account_identity_reads_only_public_claims(tmp_path, monkeypatch):
    claims = base64.urlsafe_b64encode(json.dumps({"name": "测试用户", "email": "user@example.com"}).encode()).decode().rstrip("=")
    root = tmp_path / "codex"; root.mkdir()
    (root / "auth.json").write_text(json.dumps({"tokens": {"id_token": f"a.{claims}.c"}}), encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(root))
    assert CodexCliProvider.account_identity() == {"name": "测试用户", "email": "user@example.com"}
