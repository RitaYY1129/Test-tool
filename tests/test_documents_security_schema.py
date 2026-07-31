import json

import pytest

from testpilot.cases.schema import validate_generation
from testpilot.common.security import SecretStore, split_sensitive
from testpilot.parsers.document_parser import DocumentParser
from testpilot.parsers.format_detector import detect_format


def test_document_and_excel(tmp_path):
    markdown = tmp_path / "api.md"
    markdown.write_text("# 用户查询\nGET https://api.example.test/users/{id}\nPOST /users", encoding="utf-8")
    document = DocumentParser().parse_file(markdown)
    assert [x.key for x in document.endpoints] == ["GET /users/{id}", "POST /users"]
    assert detect_format(markdown) == "document"

    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["方法", "路径", "接口名称", "模块"])
    sheet.append(["GET", "/orders", "订单列表", "订单"])
    excel = tmp_path / "api.xlsx"
    workbook.save(excel)
    assert DocumentParser().parse_file(excel).endpoints[0].module == "订单"


def test_secret_store(tmp_path):
    public, secret = split_sensitive({"baseUrl": "http://test", "token": "secret"})
    store = SecretStore(tmp_path / "master.key")
    encrypted = store.encrypt_dict(secret)
    assert "secret" not in encrypted
    assert store.decrypt_dict(encrypted) == {"token": "secret"}
    assert public == {"baseUrl": "http://test"}


def test_generation_schema_rejects_unknown_endpoint():
    value = {
        "plan": {"scope": [], "test_types": [], "requires_confirmation": True},
        "cases": [{
            "name": "bad", "priority": "P1", "request": {"method": "GET", "path": "/unknown"},
            "assertions": [], "source": "agent", "review_status": "draft",
        }],
    }
    with pytest.raises(ValueError):
        validate_generation(value, {"GET /known"})
