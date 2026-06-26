"""Agent 路由的鉴权与注册测试(无需 DB —— 鉴权先于业务执行)。"""

import uuid

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
_APP_ID = uuid.uuid4()
_TOOL_ID = uuid.uuid4()
_CONV_ID = uuid.uuid4()
_MSG_ID = uuid.uuid4()


def test_agent_tools_require_auth():
    assert client.get(f"/api/apps/{_APP_ID}/agent/tools").status_code in (401, 403)
    assert client.get(f"/api/apps/{_APP_ID}/agent/tools/catalog").status_code in (401, 403)
    assert client.post(
        f"/api/apps/{_APP_ID}/agent/tools", json={"type": "code_exec"}
    ).status_code in (401, 403)
    assert client.patch(
        f"/api/apps/{_APP_ID}/agent/tools/{_TOOL_ID}", json={"name": "x"}
    ).status_code in (401, 403)
    assert client.delete(
        f"/api/apps/{_APP_ID}/agent/tools/{_TOOL_ID}"
    ).status_code in (401, 403)


def test_agent_chat_requires_auth():
    r = client.post(f"/api/apps/{_APP_ID}/agent/chat", json={"content": "hi"})
    assert r.status_code in (401, 403)


def test_agent_thoughts_require_auth():
    r = client.get(f"/api/conversations/{_CONV_ID}/messages/{_MSG_ID}/thoughts")
    assert r.status_code in (401, 403)


def test_agent_routes_registered():
    paths = app.openapi()["paths"]
    assert "/api/apps/{app_id}/agent/tools" in paths
    assert "/api/apps/{app_id}/agent/tools/catalog" in paths
    assert "/api/apps/{app_id}/agent/tools/{tool_id}" in paths
    assert "/api/apps/{app_id}/agent/chat" in paths
    assert "/api/conversations/{conversation_id}/messages/{message_id}/thoughts" in paths
