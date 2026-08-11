from __future__ import annotations

import pytest

from testpilot.domain.flow import build_flow_model, validate_flow_model
from testpilot.engines.ai_dialogue import ControlledDialogue
from testpilot.engines.database_observer import execute_read_only_query, inspect_sqlite_database
from testpilot.engines.replay_package import export_replay_package, import_replay_package
from testpilot.reports.difference import build_combined_difference
from testpilot.engines.side_effects import FileSideEffectObserver, MessageObserver
from testpilot.storage.database import Database


def _analysis():
    return {
        "symbols": [
            {"symbol_type": "class", "qualified_name": "OrderService", "file_path": "OrderService.cs", "line_start": 10},
            {"symbol_type": "entity", "qualified_name": "OrderEntity", "file_path": "OrderEntity.cs", "line_start": 3},
        ],
        "edges": [{"source_symbol": "OrderService", "target_symbol": "OrderRepository", "edge_type": "dependency_reference", "file_path": "OrderService.cs", "line_start": 20, "metadata": {"confidence": "inferred"}}],
        "evidence": [{"evidence_type": "endpoint_route", "file_path": "OrderController.cs", "line_start": 8, "details": {"method": "POST", "path": "/orders"}}],
    }


def test_flow_model_distinguishes_visible_and_hidden_nodes():
    model = build_flow_model(_analysis())
    assert not validate_flow_model(model)
    assert any(node["visibility"] == "visible" for node in model["nodes"])
    assert any(node["visibility"] == "hidden" for node in model["nodes"])
    assert any(edge["kind"] == "calls" for edge in model["edges"])


def test_ai_dialogue_requires_approval_and_blocks_high_risk_tools(tmp_path):
    db = Database(tmp_path / "test.db")
    project_id = db.create_project("dialogue")
    dialogue = ControlledDialogue(db, project_id, route="route_a")
    result = dialogue.send("请分析订单创建流程", {"analysis": _analysis()})
    assert result.artifact_id and result.approval_id
    assert result.questions
    assert len(db.list_ai_messages(dialogue.session_id)) == 2
    with pytest.raises(PermissionError):
        dialogue.call_tool("send_confirmed_request", {"method": "POST", "path": "/orders"}, result.approval_id)
    dialogue.approve(result.approval_id, "测试环境已确认")
    authorized = dialogue.call_tool("send_confirmed_request", {"method": "POST", "path": "/orders"}, result.approval_id)
    assert authorized["status"] == "authorized"
    assert db.list_ai_approvals(dialogue.session_id)[0]["status"] == "approved"


def test_ai_dialogue_plain_chat_does_not_echo_full_source_graph(tmp_path):
    class Provider:
        captured = ""
        def generate_structured(self, system_prompt, user_prompt, output_schema):
            self.captured = user_prompt
            return {"reply": "你好，我可以帮你设计测试。", "questions": [], "test_scope": []}

    db = Database(tmp_path / "chat.db")
    project_id = db.create_project("chat")
    provider = Provider()
    huge = _analysis()
    huge["symbols"] = huge["symbols"] * 500
    dialogue = ControlledDialogue(db, project_id, route="route_a", provider=provider)
    result = dialogue.send("你好", {"analysis": huge})
    assert result.message.startswith("你好")
    assert result.artifact_id is None and result.approval_id is None
    assert len(provider.captured) < 3000
    assert not db.list_ai_artifacts(dialogue.session_id)


def test_ai_dialogue_returns_local_evidence_result_when_provider_times_out(tmp_path):
    class TimeoutProvider:
        def generate_structured(self, *_args, **_kwargs):
            raise TimeoutError("provider timeout")

    db = Database(tmp_path / "fallback.db")
    project_id = db.create_project("fallback")
    dialogue = ControlledDialogue(db, project_id, route="route_a", provider=TimeoutProvider())
    result = dialogue.send("检查当前项目的接口和数据库", {
        "analysis": _analysis(),
        "endpoints": [{"method": "GET", "path": "/api/health", "module": "system", "summary": "health"}],
        "workflow": {"name": "source workflow", "steps": []},
    })
    assert "本地源码证据分析" in result.message
    assert result.artifact_id is not None
    assert db.list_ai_messages(dialogue.session_id)[-1]["role"] == "assistant"


def test_general_chat_keeps_history_without_forcing_test_artifact(tmp_path):
    class Provider:
        def generate_structured(self, _system, prompt, _schema):
            payload = __import__("json").loads(prompt)
            return {"reply": f"收到：{payload['message']}；历史：{len(payload['history'])}"}

    db = Database(tmp_path / "general-chat.db")
    project_id = db.create_project("chat")
    dialogue = ControlledDialogue(db, project_id, route="chat", provider=Provider())
    first = dialogue.send("你好", {"project_summary": {"endpoint_count": 2}})
    second = dialogue.send("继续说", {"project_summary": {"endpoint_count": 2}})
    assert "你好" in first.message
    assert "历史：2" in second.message
    assert not db.list_ai_artifacts(dialogue.session_id)


def test_sqlite_schema_snapshot_and_read_only_query(tmp_path):
    target = tmp_path / "replica.db"
    import sqlite3
    with sqlite3.connect(target) as connection:
        connection.execute("CREATE TABLE orders(id INTEGER PRIMARY KEY, state TEXT)")
        connection.execute("INSERT INTO orders(state) VALUES ('draft')")
    snapshot = inspect_sqlite_database(target)
    assert snapshot["status"] == "healthy"
    assert snapshot["tables"][0]["name"] == "orders"
    assert execute_read_only_query(target, "SELECT state FROM orders")[0]["state"] == "draft"
    with pytest.raises(Exception):
        execute_read_only_query(target, "DELETE FROM orders")


def test_replay_package_is_redacted_and_round_trips(tmp_path):
    package = export_replay_package(tmp_path / "case.tpa", {"name": "demo"}, environment={"base_url": "http://test", "token": "secret"})
    payload = import_replay_package(package)
    assert payload["project"]["name"] == "demo"
    assert "token" not in payload["environment"]


def test_combined_difference_reports_hidden_state_gap():
    class Document:
        endpoints = [type("Endpoint", (), {"method": "POST", "path": "/orders"})()]
    difference = build_combined_difference(Document(), {"evidence": []}, {"flow_model": {"nodes": [{"visibility": "hidden"}]}, "review_status": "draft"})
    assert difference["status"] == "failed"
    assert {item["kind"] for item in difference["issues"]} >= {"hidden_state_unobserved", "workflow_not_confirmed"}


def test_file_and_message_side_effect_observers(tmp_path):
    root = tmp_path / "out"; root.mkdir(); (root / "a.txt").write_text("before", encoding="utf-8")
    observer = FileSideEffectObserver(root); before = observer.snapshot(); (root / "a.txt").write_text("after", encoding="utf-8"); (root / "b.txt").write_text("new", encoding="utf-8")
    changes = observer.diff(before, observer.snapshot())
    assert {item["change"] for item in changes} == {"modified", "created"}
    messages = MessageObserver(); messages.record("order.created", {"id": 1, "state": "submitted"})
    assert messages.find("order.created", "id", 1)[0]["payload"]["state"] == "submitted"
