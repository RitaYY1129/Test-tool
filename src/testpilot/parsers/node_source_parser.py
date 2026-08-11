from __future__ import annotations

import re
from pathlib import Path

from testpilot.domain.api import ApiDocument, ApiEndpoint, ApiParameter


MOUNT = re.compile(r"app\.use\(\s*['\"]([^'\"]*)['\"]\s*,\s*require\(['\"]\.\/([^'\"]+)['\"]\)\s*\)")
ROUTE = re.compile(r"router\.(get|post|put|patch|delete|head|options)\(\s*['\"]([^'\"]*)['\"]\s*,([\s\S]*?)\);", re.IGNORECASE)
ROUTE_CHAIN = re.compile(r"router\.route\(\s*['\"]([^'\"]*)['\"]\s*\)((?:\.(?:get|post|put|patch|delete|head|options)\([^;]+\))+)", re.IGNORECASE)
CHAIN_METHOD = re.compile(r"\.(get|post|put|patch|delete|head|options)\(", re.IGNORECASE)
APP_ROUTE = re.compile(r"app\.(get|post|put|patch|delete|head|options)\(\s*['\"]([^'\"]*)['\"]\s*,([\s\S]*?)\);", re.IGNORECASE)


class NodeExpressParser:
    """Conservative Express router parser with route/middleware evidence."""

    def parse_directory(self, directory: str | Path) -> ApiDocument:
        root = Path(directory).resolve()
        server = root / "server.js"
        if not server.is_file():
            raise ValueError("Node 项目缺少 server.js")
        server_text = server.read_text(encoding="utf-8", errors="replace")
        mounts = {Path(file_name).stem: prefix.rstrip("/") for prefix, file_name in MOUNT.findall(server_text)}
        endpoints: list[ApiEndpoint] = []
        for match in APP_ROUTE.finditer(server_text):
            method, path, handlers = match.group(1).upper(), match.group(2), match.group(3)
            line = server_text.count("\n", 0, match.start()) + 1
            endpoints.append(self._endpoint(method, self._join("", path), "server", server, line, "authenticate" in handlers))
        for route_file in sorted((root / "routes").glob("*.js")):
            module = route_file.stem
            prefix = mounts.get(module, "")
            text = route_file.read_text(encoding="utf-8", errors="replace")
            router_auth = bool(re.search(r"router\.use\(\s*authenticate\s*\)", text))
            for match in ROUTE.finditer(text):
                method, path, handlers = match.group(1).upper(), match.group(2), match.group(3)
                full_path = self._join(prefix, path)
                line = text.count("\n", 0, match.start()) + 1
                endpoints.append(self._endpoint(method, full_path, module, route_file, line, router_auth or "authenticate" in handlers))
            for match in ROUTE_CHAIN.finditer(text):
                path, chain = match.group(1), match.group(2)
                for method_match in CHAIN_METHOD.finditer(chain):
                    method = method_match.group(1).upper()
                    full_path = self._join(prefix, path)
                    line = text.count("\n", 0, match.start()) + 1
                    endpoints.append(self._endpoint(method, full_path, module, route_file, line, router_auth or "authenticate" in chain))
        return ApiDocument(root.name, "", "Node.js Express source", [], endpoints, {"bearerAuth": {"type": "http", "scheme": "bearer"}})

    @staticmethod
    def _join(prefix: str, path: str) -> str:
        parts = [part.strip("/") for part in (prefix, path) if part.strip("/")]
        return "/" + "/".join(parts) if parts else "/"

    @staticmethod
    def _endpoint(method: str, path: str, module: str, route_file: Path, line: int, secured: bool) -> ApiEndpoint:
        params = [ApiParameter(name, "path", True, {"type": "string"}) for name in re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", path)]
        return ApiEndpoint(
            method=method, path=path, summary=f"Express {module} {method}", operation_id=f"{module}_{method}_{line}",
            module=module, parameters=params, responses={"200": {"description": "Express route response"}},
            security=[{"bearerAuth": []}] if secured else [], source="source_code",
            source_location=f"{route_file.name}:{line}",
        )
