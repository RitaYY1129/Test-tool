from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from testpilot.model_providers.codex_cli import CodexCliProvider
from testpilot.model_providers.ollama import OllamaProvider


def test_codex_provider_uses_read_only_and_schema(tmp_path, monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
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
