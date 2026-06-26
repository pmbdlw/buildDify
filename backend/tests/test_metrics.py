"""可观测路由测试:进程指标公开可读;用量需鉴权。"""

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_process_metrics_public():
    r = client.get("/api/metrics")
    assert r.status_code == 200
    body = r.json()
    assert "requests" in body and "by_status" in body


def test_usage_requires_auth():
    assert client.get("/api/metrics/usage").status_code in (401, 403)


def test_request_id_header_present():
    r = client.get("/health")
    assert r.headers.get("X-Request-ID")
