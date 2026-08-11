from __future__ import annotations

from pathlib import Path

from testpilot.parsers.aspnet_parser import AspNetCoreParser
from testpilot.parsers.spring_parser import SpringBootParser
from testpilot.parsers.node_source_parser import NodeExpressParser
from testpilot.parsers.source_analysis import analyze_source_tree, suggest_workflow


class BackendSourceParser:
    """Detect the backend framework and route to a conservative source parser."""

    def detect(self, directory: str | Path) -> str:
        root = Path(directory).resolve()
        if not root.is_dir():
            raise ValueError("源码目录不存在")
        if any(root.rglob("*.csproj")) and any(root.rglob("*Controller.cs")):
            return "aspnet"
        if any(root.rglob("pom.xml")) or any(root.rglob("build.gradle")):
            return "spring"
        if any(root.rglob("*.java")):
            return "spring"
        if (root / "server.js").is_file() and (root / "routes").is_dir():
            return "node_express"
        raise ValueError(
            "暂未识别该后端框架。目前自动解析支持 ASP.NET Core 和 Spring Boot；"
            "仍可使用 Codex 读取其他语言源码，并配合 OpenAPI/Apifox 导入接口。"
        )

    def parse_directory(self, directory: str | Path):
        return self.analyze_directory(directory)["document"]

    def analyze_directory(self, directory: str | Path) -> dict:
        framework = self.detect(directory)
        if framework == "aspnet":
            document = AspNetCoreParser().parse_directory(directory)
        elif framework == "spring":
            document = SpringBootParser().parse_directory(directory)
        else:
            document = NodeExpressParser().parse_directory(directory)
        return {
            "document": document,
            **analyze_source_tree(directory, document, framework),
        }

    def suggest_workflow(self, directory: str | Path) -> tuple[dict, dict]:
        analysis = self.analyze_directory(directory)
        return analysis, suggest_workflow(analysis["document"], analysis)
