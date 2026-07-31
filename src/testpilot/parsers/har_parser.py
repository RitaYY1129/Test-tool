from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from testpilot.domain.api import ApiDocument, ApiEndpoint, ApiParameter


class HarParser:
    def parse_file(self, path: str | Path) -> ApiDocument:
        source = Path(path)
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        entries = (data.get("log") or {}).get("entries")
        if not isinstance(entries, list):
            raise ValueError("不是有效的 HAR 文件")
        endpoints, bases, seen = [], set(), set()
        for index, entry in enumerate(entries):
            request = entry.get("request") or {}
            url = urlsplit(str(request.get("url") or ""))
            method, route = str(request.get("method") or "GET").upper(), url.path or "/"
            key = (method, route)
            if key in seen or not url.scheme:
                continue
            seen.add(key); bases.add(f"{url.scheme}://{url.netloc}")
            params = [
                ApiParameter(str(x.get("name") or ""), "query", example=x.get("value"), schema={"type": "string"})
                for x in request.get("queryString") or [] if isinstance(x, dict)
            ]
            params.extend(
                ApiParameter(str(x.get("name") or ""), "header", example=x.get("value"), schema={"type": "string"})
                for x in request.get("headers") or []
                if isinstance(x, dict) and str(x.get("name", "")).lower() not in {"cookie", "authorization"}
            )
            body = {}
            post = request.get("postData") or {}
            if post:
                text = post.get("text")
                try:
                    example = json.loads(text) if text else None
                except json.JSONDecodeError:
                    example = text
                body = {"content": {post.get("mimeType") or "text/plain": {"example": example}}}
            response = entry.get("response") or {}
            status = str(response.get("status") or "default")
            endpoints.append(ApiEndpoint(
                method, route, f"HAR 请求 {index + 1}", module=url.netloc, parameters=params,
                request_body=body, responses={status: {"description": response.get("statusText") or ""}},
                security=[{"capturedAuth": []}] if any(
                    str(x.get("name", "")).lower() in {"cookie", "authorization"} for x in request.get("headers") or []
                ) else [], source="har", source_location=f"{source.name}#entries/{index}",
            ))
        return ApiDocument(source.stem, "", "HAR 1.2", sorted(bases), endpoints)

