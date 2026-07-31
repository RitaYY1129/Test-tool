from __future__ import annotations

import json
import shlex
from urllib.parse import parse_qsl, urlsplit

from testpilot.domain.api import ApiDocument, ApiEndpoint, ApiParameter


def parse_curl(command: str) -> ApiDocument:
    tokens = shlex.split(command, posix=True)
    if not tokens or tokens[0].lower() != "curl":
        raise ValueError("请输入以 curl 开头的命令")
    method, url, headers, raw_body = "GET", "", {}, None
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token in {"-X", "--request"}:
            i += 1; method = tokens[i].upper()
        elif token in {"-H", "--header"}:
            i += 1
            key, _, value = tokens[i].partition(":"); headers[key.strip()] = value.strip()
        elif token in {"-d", "--data", "--data-raw", "--data-binary"}:
            i += 1; raw_body = tokens[i]
            if method == "GET": method = "POST"
        elif token.startswith(("http://", "https://")):
            url = token
        i += 1
    if not url:
        raise ValueError("cURL 中缺少 HTTP/HTTPS URL")
    parsed = urlsplit(url)
    params = [ApiParameter(k, "query", example=v, schema={"type": "string"}) for k, v in parse_qsl(parsed.query)]
    params.extend(ApiParameter(k, "header", example=v, schema={"type": "string"}) for k, v in headers.items())
    body = {}
    if raw_body is not None:
        try:
            example = json.loads(raw_body)
        except json.JSONDecodeError:
            example = raw_body
        body = {"content": {headers.get("Content-Type", "application/json"): {"example": example}}}
    endpoint = ApiEndpoint(method, parsed.path or "/", "从 cURL 导入", module="cURL", parameters=params,
                           request_body=body, source="curl", source_location="pasted curl")
    return ApiDocument("cURL 导入", "", "cURL", [f"{parsed.scheme}://{parsed.netloc}"], [endpoint])
