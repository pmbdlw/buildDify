"""对话路由的鉴权与注册测试(无需 DB —— 鉴权依赖先于业务执行)。"""

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_chat_requires_auth():
    r = client.post("/api/chat", json={"content": "hi"})
    assert r.status_code in (401, 403)


def test_list_conversations_requires_auth():
    r = client.get("/api/conversations")
    assert r.status_code in (401, 403)


def test_chat_routes_registered():
    paths = app.openapi()["paths"]
    assert "/api/chat" in paths
    assert "/api/conversations" in paths
    assert "/api/conversations/{conversation_id}/messages" in paths
