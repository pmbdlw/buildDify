"""应用构建器路由的鉴权与注册测试(无需 DB —— 鉴权先于业务执行)。"""

import uuid

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
_APP_ID = uuid.uuid4()


def test_apps_crud_requires_auth():
    assert client.get("/api/apps").status_code in (401, 403)
    assert client.post("/api/apps", json={"name": "x"}).status_code in (401, 403)
    assert client.get(f"/api/apps/{_APP_ID}").status_code in (401, 403)
    assert client.get(f"/api/apps/{_APP_ID}/config").status_code in (401, 403)
    assert client.post(f"/api/apps/{_APP_ID}/publish").status_code in (401, 403)


def test_app_debug_chat_requires_auth():
    r = client.post(f"/api/apps/{_APP_ID}/chat", json={"content": "hi"})
    assert r.status_code in (401, 403)


def test_api_key_management_requires_auth():
    assert client.get(f"/api/apps/{_APP_ID}/api-keys").status_code in (401, 403)
    assert client.post(f"/api/apps/{_APP_ID}/api-keys", json={"name": "k"}).status_code in (
        401,
        403,
    )


def test_public_chat_requires_api_key():
    # 缺少 API Key 头时应 401,而非进入业务
    r = client.post(f"/v1/apps/{_APP_ID}/chat", json={"content": "hi"})
    assert r.status_code == 401


def test_app_routes_registered():
    paths = app.openapi()["paths"]
    assert "/api/apps" in paths
    assert "/api/apps/{app_id}" in paths
    assert "/api/apps/{app_id}/config" in paths
    assert "/api/apps/{app_id}/publish" in paths
    assert "/api/apps/{app_id}/chat" in paths
    assert "/api/apps/{app_id}/api-keys" in paths
    assert "/api/apps/{app_id}/api-keys/{key_id}" in paths
    assert "/v1/apps/{app_id}/chat" in paths
