from __future__ import annotations

import hashlib
import re
from pathlib import Path


_SKIP_DIRS = {".git", ".venv", "bin", "obj", "target", "node_modules", "dist", "build"}
_LANGUAGES = {
    ".cs": "csharp",
    ".java": "java",
    ".kt": "kotlin",
    ".xml": "xml",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".sql": "sql",
    ".js": "javascript",
    ".ts": "typescript",
}
_CLASS = re.compile(r"\b(?:public\s+|internal\s+|private\s+|protected\s+)*(?:class|record|interface|enum)\s+(\w+)")
_SERVICE = re.compile(r"\b(\w*(?:Service|Repository|Manager|Handler|Dao))\b")
_METHOD = re.compile(r"(?:public|private|protected|internal|static|async|final|override|virtual|synchronized|\s)+[\w<>\[\],.?]+\s+(\w+)\s*\(([^)]*)\)\s*[\{:]", re.MULTILINE)
_CALL = re.compile(r"\b(?:this\.)?(\w+)\s*\(([^;{}]*)\)")
_SQL_WRITE = re.compile(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+[\[\]`\"']?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_TRANSACTION = re.compile(r"\b(?:BeginTransaction|TransactionScope|Transactional|SaveChanges|CommitAsync|RollbackAsync)\b", re.IGNORECASE)
_JS_FUNCTION = re.compile(r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>|(?:async\s+)?function\s+(\w+)\s*\(", re.MULTILINE)
_ENTITY_SUFFIXES = ("Request", "Response", "Dto", "DTO", "Entity", "Model", "Command", "Query")


def analyze_source_tree(root: str | Path, document, framework: str) -> dict:
    """Build a conservative, hash-only source inventory for route A.

    This is deliberately evidence-first: it records what can be located in
    source files and never executes project code or persists source contents.
    Deeper call-graph analysis can consume this stable shape later.
    """
    root = Path(root).resolve()
    files: list[dict] = []
    file_text: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
            continue
        language = _LANGUAGES.get(path.suffix.lower())
        if not language:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        relative = path.relative_to(root).as_posix()
        files.append({
            "path": relative,
            "language": language,
            "size_bytes": len(raw),
            "content_hash": digest,
        })
        if language in {"csharp", "java", "javascript", "typescript"}:
            file_text[relative] = raw.decode("utf-8-sig", errors="replace")

    revision_hash = hashlib.sha256(
        "\n".join(f"{item['path']}:{item['content_hash']}" for item in files).encode()
    ).hexdigest()
    symbols: list[dict] = []
    edges: list[dict] = []
    evidence: list[dict] = []
    symbol_names: set[str] = set()
    for relative, text in file_text.items():
        if relative.endswith((".js", ".ts")):
            owner = Path(relative).stem
            for function_match in _JS_FUNCTION.finditer(text):
                function_name = function_match.group(1) or function_match.group(2) or "anonymous"
                line = text.count("\n", 0, function_match.start()) + 1
                qualified = f"{owner}.{function_name}"
                symbols.append({"symbol_type": "method", "qualified_name": qualified, "file_path": relative, "line_start": line, "line_end": line, "metadata": {"language": "javascript", "confidence": "static"}})
                symbol_names.add(function_name)
            for sql in _SQL_WRITE.finditer(text):
                line = text.count("\n", 0, sql.start()) + 1
                edges.append({"source_symbol": owner, "target_symbol": f"db:{sql.group(2)}", "edge_type": "writes", "file_path": relative, "line_start": line, "metadata": {"confidence": "static", "operation": sql.group(1).upper(), "table": sql.group(2)}})
        classes: list[tuple[str, int]] = []
        for match in _CLASS.finditer(text):
            name = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            classes.append((name, line))
            symbol_names.add(name)
            symbols.append({
                "symbol_type": "entity" if name.endswith(_ENTITY_SUFFIXES) else "class",
                "qualified_name": name,
                "file_path": relative,
                "line_start": line,
                "line_end": line,
                "metadata": {"entity_candidate": name.endswith(_ENTITY_SUFFIXES)},
            })
        owner = classes[-1][0] if classes else Path(relative).stem
        methods: list[tuple[str, int]] = []
        for match in _METHOD.finditer(text):
            method_name = match.group(1)
            if method_name in {"if", "for", "while", "switch", "catch"}:
                continue
            line = text.count("\n", 0, match.start()) + 1
            methods.append((method_name, line))
            qualified = f"{owner}.{method_name}"
            symbols.append({
                "symbol_type": "method", "qualified_name": qualified,
                "file_path": relative, "line_start": line, "line_end": line,
                "metadata": {"parameter_text": match.group(2), "confidence": "static"},
            })
            symbol_names.add(method_name)
            body_start = match.end()
            body_end = text.find("}", body_start)
            body = text[body_start:body_end if body_end >= 0 else len(text)]
            for call in _CALL.finditer(body):
                target = call.group(1)
                if target in {method_name, "if", "for", "while", "return", "new", "catch"}:
                    continue
                edges.append({
                    "source_symbol": qualified, "target_symbol": target,
                    "edge_type": "method_call", "file_path": relative,
                    "line_start": line + body[:call.start()].count("\n"),
                    "metadata": {"confidence": "static", "reason": "method invocation evidence"},
                })
            for sql in _SQL_WRITE.finditer(body):
                table = sql.group(2)
                edges.append({
                    "source_symbol": qualified, "target_symbol": f"db:{table}",
                    "edge_type": "writes", "file_path": relative,
                    "line_start": line + body[:sql.start()].count("\n"),
                    "metadata": {"confidence": "static", "operation": sql.group(1).upper(), "table": table},
                })
            if _TRANSACTION.search(text[max(0, match.start() - 240):body_end if body_end >= 0 else len(text)]):
                evidence.append({
                    "evidence_type": "transaction_boundary", "file_path": relative,
                    "line_start": line, "line_end": line,
                    "content_hash": next((x["content_hash"] for x in files if x["path"] == relative), ""),
                    "details": {"symbol": qualified, "confidence": "static"},
                })
        for match in _SERVICE.finditer(text):
            target = match.group(1)
            if target in symbol_names or target.endswith(("Service", "Repository", "Manager", "Handler", "Dao")):
                line = text.count("\n", 0, match.start()) + 1
                edges.append({
                    "source_symbol": owner,
                    "target_symbol": target,
                    "edge_type": "dependency_reference",
                    "file_path": relative,
                    "line_start": line,
                    "metadata": {"confidence": "low", "reason": "conservative name-based evidence"},
                })

    for endpoint in getattr(document, "endpoints", []):
        location = str(getattr(endpoint, "source_location", ""))
        file_path, _, raw_line = location.rpartition(":")
        try:
            line = int(raw_line)
        except ValueError:
            line = 0
        evidence.append({
            "evidence_type": "endpoint_route",
            "file_path": file_path or location,
            "line_start": line,
            "line_end": line,
            "content_hash": next((x["content_hash"] for x in files if x["path"] == file_path), ""),
            "details": {
                "method": endpoint.method,
                "path": endpoint.path,
                "module": endpoint.module,
                "source": endpoint.source,
            },
        })

    return {
        "root_path": str(root),
        "name": root.name,
        "framework": framework,
        "analyzer": "builtin-source-inventory-v1",
        "files": files,
        "revision": {
            "revision_key": revision_hash,
            "content_hash": revision_hash,
            "metadata": {"file_count": len(files)},
        },
        "symbols": symbols,
        "edges": edges,
        "evidence": evidence,
        "summary": {
            "file_count": len(files),
            "symbol_count": len(symbols),
            "edge_count": len(edges),
            "evidence_count": len(evidence),
            "endpoint_count": len(getattr(document, "endpoints", [])),
        },
    }


def suggest_workflow(document, analysis: dict) -> dict:
    """Create a reviewable workflow candidate from discovered endpoints.

    Ordering is intentionally deterministic and conservative.  It is a draft,
    never an instruction to mutate a target system; a user must edit and
    confirm it before the workflow runner will execute it.
    """
    steps = []
    for index, endpoint in enumerate(getattr(document, "endpoints", []), 1):
        success = next((int(code) for code in (endpoint.responses or {}) if str(code).startswith("2") and str(code).isdigit()), 200)
        steps.append({
            "name": f"{endpoint.method.upper()} {endpoint.path}",
            "kind": "http",
            "request": {
                "method": endpoint.method.upper(),
                "path": endpoint.path,
                "headers": {},
                "query": {},
                "path_parameters": {},
                "body": None,
            },
            "assertions": [{"type": "status_code", "operator": "equals", "expected": success}],
            "extract": [],
            "compensation": [],
            "source": endpoint.source_location,
            "review_status": "draft",
        })
    workflow = {
        "name": f"{analysis.get('name', '源码项目')} · 业务流程草稿",
        "review_status": "draft",
        "requires_confirmation": True,
        "analysis_summary": analysis.get("summary", {}),
        "entities": [item["qualified_name"] for item in analysis.get("symbols", []) if item.get("symbol_type") == "entity"],
        "call_chain_candidates": [
            {key: item.get(key) for key in ("source_symbol", "target_symbol", "edge_type", "file_path", "line_start")}
            for item in analysis.get("edges", [])
        ],
        "steps": steps,
    }
    from testpilot.domain.process_script import build_process_script
    return build_process_script(workflow, analysis)
