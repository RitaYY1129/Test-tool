from __future__ import annotations

"""Controlled AI conversation orchestration.

The orchestrator never executes a request or SQL statement. It turns evidence
and user answers into reviewable artifacts and records every approval/tool
boundary in the local database.
"""

import json
from dataclasses import dataclass
from typing import Any

from testpilot.domain.flow import build_flow_model, evidence_counts, validate_flow_model
from testpilot.domain.process_script import build_process_script, evaluate_process_script
from testpilot.model_providers.base import ModelProvider
from testpilot.model_providers.resilience import AIRequestCancelled


ARTIFACT_SCHEMA = {
    "type": "object",
    "required": ["reply", "questions", "test_scope"],
    "properties": {
        "reply": {"type": "string"},
        "kind": {"type": "string"},
        "questions": {"type": "array"},
        "test_scope": {"type": "array"},
        "database_changes": {"type": "array"},
        "risk_level": {"type": "string"},
        "process_script": {"type": "object"},
    },
}

CHAT_SCHEMA = {
    "type": "object",
    "required": ["reply"],
    "properties": {"reply": {"type": "string"}},
}


@dataclass(slots=True)
class DialogueResult:
    message: str
    artifact_id: int | None = None
    approval_id: int | None = None
    questions: list[dict[str, Any]] | None = None


class ControlledDialogue:
    ALLOWED_TOOLS = {
        "read_source_summary": "low",
        "read_schema_snapshot": "medium",
        "read_test_db": "medium",
        "send_confirmed_request": "high",
        "execute_compensation": "high",
    }

    def __init__(self, database, project_id: int, route: str = "route_a",
                 provider: ModelProvider | None = None, session_id: int | None = None):
        self.db = database
        self.project_id = project_id
        self.route = route
        self.provider = provider
        self.session_id = session_id or database.create_ai_session(project_id, route)

    def send(self, content: str, context: dict[str, Any] | None = None) -> DialogueResult:
        content = content.strip()
        if not content:
            raise ValueError("消息不能为空")
        self.db.add_ai_message(self.session_id, "user", content)
        context = context or {}
        if self.route == "chat":
            return self._send_chat(content, context)
        analysis = context.get("analysis") or {}
        workflow = context.get("workflow") or {}
        answers = context.get("answers") or {}
        flow_model = build_flow_model(analysis, workflow, {"manual_answers": answers} if answers else None)
        questions = self._questions(flow_model, context)
        generated = self._generate(content, context, flow_model, questions)
        message = str(generated.get("reply") or "我可以帮助你理解项目、设计接口测试，或生成 API + 数据库联合测试草稿。")
        test_intent = bool(generated.get("process_script")) or any(word in content.lower() for word in (
            "测试", "用例", "接口", "数据库", "流程", "校验", "验证", "test", "api", "database",
        ))
        if not test_intent:
            self.db.add_ai_message(self.session_id, "assistant", message)
            return DialogueResult(message, questions=[])
        process_script = generated.get("process_script") or workflow
        if self.route == "route_a":
            process_script = build_process_script(process_script or {"name": "AI process draft", "steps": []}, analysis)
        artifact = {
            "version": "1.0",
            "kind": "flow_review",
            "questions": generated.get("questions", questions),
            "flow_model": generated.get("flow_model", flow_model),
            "test_scope": generated.get("test_scope", context.get("test_scope", [])),
            "database_changes": generated.get("database_changes", workflow.get("database_changes", [])),
            "risk_level": generated.get("risk_level", "medium" if self.route == "route_a" else "low"),
            "evidence_counts": evidence_counts(generated.get("flow_model", flow_model)),
            "requires_human_approval": True,
            "process_script": process_script if self.route == "route_a" else {},
            "process_coverage": evaluate_process_script(process_script) if self.route == "route_a" else {},
        }
        errors = validate_flow_model(artifact["flow_model"])
        if errors:
            artifact["flow_model"]["validation_errors"] = errors
        artifact_id = self.db.save_ai_artifact(
            self.session_id, "flow_review", "业务流程与数据流审查草稿", artifact,
            self._evidence_refs(artifact["flow_model"]), "draft",
        )
        approval_id = self.db.create_ai_approval(self.session_id, "confirm_flow_and_scope", artifact_id)
        message = str(generated.get("reply") or self._message(artifact))
        self.db.add_ai_message(self.session_id, "assistant", message, metadata={"artifact_id": artifact_id, "approval_id": approval_id})
        return DialogueResult(message, artifact_id, approval_id, artifact["questions"])

    def _send_chat(self, content: str, context: dict[str, Any]) -> DialogueResult:
        """Normal multi-turn conversation; it never creates a test artifact."""
        history = self.db.list_ai_messages(self.session_id)[-12:]
        messages = [
            {"role": "assistant" if item["role"] == "assistant" else "user", "content": item["content"]}
            for item in history
            if item["role"] in {"user", "assistant"}
        ]
        project = context.get("project_summary") or {}
        if not self.provider:
            reply = "当前没有可用模型。请在 AI 模型配置中配置兼容 API 或本地 Ollama。"
            self.db.add_ai_message(self.session_id, "system", reply)
            return DialogueResult(reply, questions=[])
        try:
            system_prompt = (
                "你是 TestPilot 的通用 AI 助手。像自然聊天一样直接回答用户，保持上下文，简洁、准确。"
                "用户若要求测试编排，可以提出可执行的测试建议；不要声称已经执行了未经确认的操作。"
                f"当前项目摘要：{json.dumps(project, ensure_ascii=False)}"
            )
            generate_chat = getattr(self.provider, "generate_chat", None)
            if callable(generate_chat):
                try:
                    reply = str(generate_chat(system_prompt, messages))
                except NotImplementedError:
                    reply = ""
            else:
                reply = ""
            if not reply:
                prompt = json.dumps({"message": content, "history": messages[:-1], "project": project}, ensure_ascii=False)
                generated = self.provider.generate_structured(system_prompt, prompt, CHAT_SCHEMA)
                reply = str(generated.get("reply") or "")
            if not reply.strip():
                raise RuntimeError("模型没有返回可显示的内容")
        except AIRequestCancelled:
            raise
        except TimeoutError:
            reply = "当前模型没有在限定时间内返回真实内容。这不是 AI 回答；请重试或切换已配置的模型。"
            self.db.add_ai_message(self.session_id, "system", reply)
            return DialogueResult(reply, questions=[])
        except Exception as exc:
            reply = f"当前模型未返回真实内容：{str(exc).splitlines()[0][:180]}。请重试或切换模型。"
            self.db.add_ai_message(self.session_id, "system", reply)
            return DialogueResult(reply, questions=[])
        self.db.add_ai_message(self.session_id, "assistant", reply)
        return DialogueResult(reply, questions=[])

    def approve(self, approval_id: int, comment: str = "") -> None:
        self.db.decide_ai_approval(approval_id, "approved", comment)
        self.db.add_ai_message(self.session_id, "tool", f"人工已确认审批 #{approval_id}：{comment or '同意执行下一步'}")

    def reject(self, approval_id: int, comment: str = "") -> None:
        self.db.decide_ai_approval(approval_id, "rejected", comment)
        self.db.add_ai_message(self.session_id, "tool", f"人工已拒绝审批 #{approval_id}：{comment or '需要补充信息'}")

    def call_tool(self, tool_name: str, arguments: dict[str, Any], approval_id: int | None = None) -> dict[str, Any]:
        if tool_name not in self.ALLOWED_TOOLS:
            self.db.save_tool_call(self.session_id, tool_name, arguments, status="blocked", risk_level="high", approval_id=approval_id)
            raise PermissionError(f"工具未在白名单中：{tool_name}")
        risk = self.ALLOWED_TOOLS[tool_name]
        approved = any(item["id"] == approval_id and item["status"] == "approved" for item in self.db.list_ai_approvals(self.session_id)) if approval_id else False
        if risk in {"high", "medium"} and not approved:
            self.db.save_tool_call(self.session_id, tool_name, arguments, status="blocked", risk_level=risk, approval_id=approval_id)
            raise PermissionError("该工具调用需要关联已批准的人工审批")
        result = {"status": "authorized", "tool": tool_name, "note": "工具适配器由执行层实现；对话层不直接执行"}
        self.db.save_tool_call(self.session_id, tool_name, arguments, result=result, status="authorized", risk_level=risk, approval_id=approval_id)
        return result

    def _generate(self, content: str, context: dict[str, Any], flow_model: dict, questions: list[dict]) -> dict:
        if not self.provider:
            return {"questions": questions, "flow_model": flow_model, "test_scope": context.get("test_scope", [])}
        analysis = context.get("analysis") or {}
        compact = {
            "user_message": content,
            "environment_confirmed": bool(context.get("environment_confirmed")),
            "database_connection": context.get("database_connection") or {},
            "base_url_configured": bool(context.get("base_url_configured")),
            "test_scope": context.get("test_scope") or [],
            "endpoints": [{key: item.get(key) for key in ("method", "path", "module", "summary")} for item in (context.get("endpoints") or [])[:30]],
            "source_summary": analysis.get("summary") or {
                "symbols": len(analysis.get("symbols") or []), "edges": len(analysis.get("edges") or []),
                "evidence": len(analysis.get("evidence") or []),
            },
            "workflow": {"name": (context.get("workflow") or {}).get("name", ""), "step_count": len((context.get("workflow") or {}).get("steps") or [])},
            "flow_summary": {"nodes": len(flow_model.get("nodes") or []), "edges": len(flow_model.get("edges") or []), "validation_errors": (flow_model.get("validation_errors") or [])[:10]},
            "questions": questions,
        }
        prompt = json.dumps(compact, ensure_ascii=False)
        try:
            return self.provider.generate_structured(
                "你是受控接口测试助手。先在 reply 中简洁回答用户，不要复述完整源码图。只有用户明确要求生成测试时才给出 process_script 草稿。不要执行请求、SQL、源码或外部调用；数据库变更必须等待人工确认。",
                prompt, ARTIFACT_SCHEMA,
            )
        except AIRequestCancelled:
            raise
        except TimeoutError:
            endpoints = compact["endpoints"]
            modules = sorted({str(item.get("module") or "未分组") for item in endpoints})
            reply = (
                "Codex 本次响应超时，已自动切换为本地源码证据分析，不会让对话空白。"
                f"当前上下文包含 {len(endpoints)} 个代表接口"
                f"（项目接口较多时最多展示 30 个），涉及模块：{('、'.join(modules[:10]) or '未识别')}。"
                "我已根据现有源码分析、接口资产和数据库证据生成可审核草稿；"
                "你可以先查看测试草稿，补充具体业务目标后再继续。"
            )
            return {
                "reply": reply,
                "kind": "local_evidence_fallback",
                "questions": questions,
                "test_scope": compact["test_scope"],
                "database_changes": (context.get("workflow") or {}).get("database_changes", []),
                "risk_level": "medium",
            }

    @staticmethod
    def _questions(flow_model: dict, context: dict) -> list[dict[str, Any]]:
        questions: list[dict[str, Any]] = []
        if not context.get("environment_confirmed"):
            questions.append({"key": "environment", "question": "当前目标是否为已授权的测试环境？请提供环境名称。", "required": True})
        if not context.get("database_connection") and any(node.get("kind") == "database" for node in flow_model.get("nodes", [])):
            questions.append({"key": "database", "question": "隐藏工艺需要查询哪个测试库副本？只能提供测试库或只读观测配置。", "required": True})
        if not context.get("write_policy"):
            questions.append({"key": "write_policy", "question": "哪些表/字段允许写入夹具？失败后使用回滚还是显式补偿？", "required": True})
        if not context.get("test_scope"):
            questions.append({"key": "test_scope", "question": "本次优先验证哪些方向：契约、状态迁移、幂等、权限、工艺参数、异常补偿？", "required": True})
        return questions

    @staticmethod
    def _evidence_refs(flow_model: dict) -> list[dict]:
        refs = []
        for node in flow_model.get("nodes", []):
            for evidence in node.get("evidence", []):
                refs.append({"evidence_kind": evidence.get("evidence_type", "unknown"), "locator": evidence.get("locator", ""), "detail": node.get("name", ""), "confidence": evidence.get("confidence", "inferred")})
        return refs

    @staticmethod
    def _message(artifact: dict) -> str:
        questions = artifact.get("questions") or []
        counts = artifact.get("evidence_counts") or {}
        return (f"已生成业务流程与数据流审查草稿：{len(artifact.get('flow_model', {}).get('nodes', []))} 个节点、"
                f"{len(artifact.get('flow_model', {}).get('edges', []))} 条边。证据统计 {counts}。"
                f"仍有 {len(questions)} 个问题需要人工确认；审批通过前不会执行请求、写库或外部调用。")
