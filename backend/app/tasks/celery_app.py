"""Celery 应用 —— broker/backend 走 Redis。

启动 worker:
    uv run celery -A app.tasks.celery_app worker -l info
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "builddify",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.document"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
