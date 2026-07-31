from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from testpilot.common.security import redact


@dataclass(slots=True)
class HttpResult:
    status_code: int
    elapsed_ms: int
    headers: dict[str, str]
    body: Any


def execute_request(method: str, base_url: str, path: str, headers: dict | None = None, body: Any = None,
                    params: dict | None = None, content_type: str = "application/json") -> HttpResult:
    import httpx

    if not base_url.lower().startswith(("http://", "https://")):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    started = time.perf_counter()
    request_options = {"headers": headers, "params": params, "timeout": 30, "follow_redirects": False}
    if body is not None:
        if content_type == "application/x-www-form-urlencoded":
            request_options["data"] = body
        elif content_type == "multipart/form-data":
            fields, files = {}, {}
            for key, value in (body or {}).items():
                if isinstance(value, dict) and value.get("file"):
                    files[key] = open(value["file"], "rb")
                else:
                    fields[key] = str(value)
            request_options.update({"data": fields, "files": files})
        elif content_type.startswith("text/"):
            request_options["content"] = str(body)
        else:
            request_options["json"] = body
    try:
        response = httpx.request(method, url, **request_options)
    finally:
        for file_handle in request_options.get("files", {}).values():
            file_handle.close()
    elapsed = round((time.perf_counter() - started) * 1000)
    try:
        payload = redact(response.json())
    except ValueError:
        payload = response.text[:20000]
    return HttpResult(response.status_code, elapsed, dict(response.headers), payload)
