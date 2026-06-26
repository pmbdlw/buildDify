"""可观测路由:进程指标(公开)+ 当前用户 token 用量(需鉴权)。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.core.observability import COUNTERS
from app.models.user import User
from app.services.metrics import MetricsService

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def process_metrics() -> dict:
    """进程内请求计数 / 平均时延 / 状态码分布(无鉴权,便于探活/采集)。"""
    return COUNTERS.snapshot()


@router.get("/metrics/usage")
async def token_usage(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """当前用户的 token 用量汇总(按模型分组)。"""
    return await MetricsService(session).token_usage(current_user.id)
