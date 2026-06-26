"""知识库:文档解析单测 + 路由鉴权/注册(无需 DB)。"""

from app.main import app
from app.services import document_parser
from fastapi.testclient import TestClient

client = TestClient(app)


def test_detect_file_type():
    assert document_parser.detect_file_type("a.PDF") == "pdf"
    assert document_parser.detect_file_type("notes.md") == "md"
    assert document_parser.detect_file_type("readme.markdown") == "md"
    assert document_parser.detect_file_type("data.txt") == "txt"
    assert document_parser.detect_file_type("noext") == "txt"


def test_parse_text_utf8():
    assert document_parser.parse("你好 hello".encode(), "txt") == "你好 hello"


def test_knowledge_routes_require_auth():
    assert client.get("/api/knowledge/datasets").status_code in (401, 403)
    assert client.post("/api/knowledge/datasets", json={"name": "x"}).status_code in (401, 403)


def test_knowledge_routes_registered():
    paths = app.openapi()["paths"]
    assert "/api/knowledge/datasets" in paths
    assert "/api/knowledge/datasets/{dataset_id}/documents" in paths
    assert "/api/knowledge/datasets/{dataset_id}/retrieve" in paths
