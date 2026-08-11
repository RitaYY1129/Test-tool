from __future__ import annotations

from testpilot.parsers.backend_source_parser import BackendSourceParser
from testpilot.parsers.node_source_parser import NodeExpressParser


def test_node_express_backend_routes_and_auth_are_discovered(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    (tmp_path / "server.js").write_text("""
    const express = require('express');
    app.use('/api/diaries', require('./routes/diary'));
    """, encoding="utf-8")
    routes = tmp_path / "routes"; routes.mkdir()
    (routes / "diary.js").write_text("""
    const router = require('express').Router();
    const { authenticate } = require('../middleware/auth');
    router.get('/', authenticate, getDiaries);
    router.post('/:id', authenticate, updateDiary);
    module.exports = router;
    """, encoding="utf-8")
    parser = BackendSourceParser()
    assert parser.detect(tmp_path) == "node_express"
    document = parser.parse_directory(tmp_path)
    assert [item.key for item in document.endpoints] == ["GET /api/diaries", "POST /api/diaries/:id"]
    assert document.endpoints[0].security
    analysis = parser.analyze_directory(tmp_path)
    assert any(item["language"] == "javascript" for item in analysis["files"])


def test_node_express_discovers_direct_app_health_route(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    (tmp_path / "server.js").write_text("""
    const express = require('express');
    const app = express();
    app.get('/api/health', (req, res) => { res.json({status: 'ok'}); });
    """, encoding="utf-8")
    (tmp_path / "routes").mkdir()
    document = NodeExpressParser().parse_directory(tmp_path)
    assert [(item.method, item.path) for item in document.endpoints] == [("GET", "/api/health")]
