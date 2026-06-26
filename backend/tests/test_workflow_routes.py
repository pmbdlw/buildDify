"""工作流路由的鉴权与注册测试(无需 DB —— 鉴权先于业务执行)。"""

import uuid

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
_WF_ID = uuid.uuid4()
_RUN_ID = uuid.uuid4()


def test_workflow_crud_requires_auth():
    assert client.get("/api/workflows").status_code in (401, 403)
    assert client.post("/api/workflows", json={"name": "x"}).status_code in (401, 403)
    assert client.get(f"/api/workflows/{_WF_ID}").status_code in (401, 403)
    assert client.put(f"/api/workflows/{_WF_ID}", json={"name": "y"}).status_code in (401, 403)
    assert client.delete(f"/api/workflows/{_WF_ID}").status_code in (401, 403)


def test_workflow_run_requires_auth():
    assert client.post(f"/api/workflows/{_WF_ID}/run", json={"inputs": {}}).status_code in (
        401,
        403,
    )
    assert client.get(f"/api/workflows/{_WF_ID}/runs").status_code in (401, 403)
    assert client.get(f"/api/workflows/{_WF_ID}/runs/{_RUN_ID}").status_code in (401, 403)


def test_workflow_routes_registered():
    paths = app.openapi()["paths"]
    assert "/api/workflows" in paths
    assert "/api/workflows/{workflow_id}" in paths
    assert "/api/workflows/{workflow_id}/run" in paths
    assert "/api/workflows/{workflow_id}/runs" in paths
    assert "/api/workflows/{workflow_id}/runs/{run_id}" in paths
