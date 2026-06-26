"""可观测:结构化请求日志中间件 + 全局异常兜底。

- 日志:每个请求一行 JSON(method/path/status/耗时/请求 id),便于采集与排查。
- 异常:未捕获异常记完整堆栈并返回统一 JSON 500,避免泄漏内部细节。
- 简单进程内计数:累计请求数 / 错误数 / 各路由耗时,供 /api/metrics 暴露。
"""

import json
import logging
import time
import uuid
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("builddify.request")


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(level)


class _Counters:
    """进程内累计指标(MVP;生产可换 Prometheus / OTel)。"""

    def __init__(self) -> None:
        self.requests = 0
        self.errors = 0
        self.total_ms = 0.0
        self.by_status: dict[int, int] = defaultdict(int)

    def observe(self, status_code: int, elapsed_ms: float) -> None:
        self.requests += 1
        self.total_ms += elapsed_ms
        self.by_status[status_code] += 1
        if status_code >= 500:
            self.errors += 1

    def snapshot(self) -> dict:
        avg = round(self.total_ms / self.requests, 2) if self.requests else 0.0
        return {
            "requests": self.requests,
            "errors": self.errors,
            "avg_latency_ms": avg,
            "by_status": dict(self.by_status),
        }


COUNTERS = _Counters()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        request_id = uuid.uuid4().hex[:12]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 —— 兜底:记堆栈并返回统一 500
            elapsed_ms = (time.perf_counter() - start) * 1000
            COUNTERS.observe(500, elapsed_ms)
            logger.exception(
                json.dumps(
                    {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": 500,
                        "elapsed_ms": round(elapsed_ms, 2),
                    },
                    ensure_ascii=False,
                )
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "服务器内部错误", "request_id": request_id},
            )
        elapsed_ms = (time.perf_counter() - start) * 1000
        COUNTERS.observe(response.status_code, elapsed_ms)
        logger.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "elapsed_ms": round(elapsed_ms, 2),
                },
                ensure_ascii=False,
            )
        )
        response.headers["X-Request-ID"] = request_id
        return response
