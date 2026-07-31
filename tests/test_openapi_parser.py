import json
from pathlib import Path

from testpilot.parsers.completeness_checker import check_completeness
from testpilot.parsers.openapi_parser import OpenApiParser


def test_parse_openapi_example():
    document = OpenApiParser().parse_file(Path("examples/openapi/petstore.json"))
    assert document.title == "TestPilot 示例 API"
    assert document.base_urls == ["https://example.test/api"]
    assert len(document.endpoints) == 1
    endpoint = document.endpoints[0]
    assert endpoint.key == "GET /pets/{petId}"
    assert endpoint.parameters[0].required is True
    report = check_completeness(document)
    assert report.endpoint_count == 1
    assert report.module_count == 1


def test_parse_swagger_2():
    data = {
        "swagger": "2.0", "info": {"title": "Legacy", "version": "1"},
        "host": "localhost:8000", "basePath": "/api", "schemes": ["http"],
        "paths": {"/users": {"get": {"responses": {"200": {"description": "ok", "schema": {"type": "array"}}}}}},
    }
    document = OpenApiParser().parse_text(json.dumps(data))
    assert document.specification == "Swagger 2.0"
    assert document.base_urls == ["http://localhost:8000/api"]
    assert document.endpoints[0].path == "/users"

