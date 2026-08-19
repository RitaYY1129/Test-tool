from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
from typing import Any


def notify(notification: dict[str, Any], project: str, summary: dict, report_path: str = "") -> None:
    """Deliver a failure notification through a webhook or SMTP.

    Webhooks are compatible with DingTalk and WeCom robot webhooks.  Notification
    failures are deliberately raised to the caller so a scheduler log is useful.
    """
    if not notification or not (summary.get("failed") or summary.get("error")):
        return
    text = (f"TestPilot AI 执行失败\n项目：{project}\n通过率：{summary.get('pass_rate', 0)}%\n"
            f"失败：{summary.get('failed', 0)}，错误：{summary.get('error', 0)}\n报告：{report_path}")
    kind = notification.get("kind", "webhook")
    if kind == "webhook":
        import httpx
        response = httpx.post(str(notification["url"]), json={"msgtype": "text", "text": {"content": text}}, timeout=15)
        response.raise_for_status()
        return
    if kind == "email":
        message = EmailMessage()
        message["Subject"] = f"[TestPilot AI] {project} 测试失败"
        message["From"] = notification["from"]
        message["To"] = notification["to"]
        message.set_content(text)
        with smtplib.SMTP(str(notification["host"]), int(notification.get("port", 587)), timeout=15) as smtp:
            if notification.get("starttls", True):
                smtp.starttls()
            if notification.get("username"):
                smtp.login(str(notification["username"]), str(notification.get("password", "")))
            smtp.send_message(message)
        return
    raise ValueError(f"不支持的通知类型：{kind}")
