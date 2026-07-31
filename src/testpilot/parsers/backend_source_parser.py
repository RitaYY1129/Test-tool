from __future__ import annotations

from pathlib import Path

from testpilot.parsers.aspnet_parser import AspNetCoreParser
from testpilot.parsers.spring_parser import SpringBootParser


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
        raise ValueError(
            "暂未识别该后端框架。目前自动解析支持 ASP.NET Core 和 Spring Boot；"
            "仍可使用 Codex 读取其他语言源码，并配合 OpenAPI/Apifox 导入接口。"
        )

    def parse_directory(self, directory: str | Path):
        framework = self.detect(directory)
        if framework == "aspnet":
            return AspNetCoreParser().parse_directory(directory)
        return SpringBootParser().parse_directory(directory)
