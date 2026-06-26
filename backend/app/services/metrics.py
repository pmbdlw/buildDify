"""可观测:token 计量汇总(按当前用户聚合 app_message 的用量)。"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message


class MetricsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def token_usage(self, user_id: uuid.UUID) -> dict:
        """汇总该用户所有会话的助手消息 token 用量,并按模型分组。"""
        base = (
            select(
                Message.model,
                func.count().label("messages"),
                func.coalesce(func.sum(Message.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(Message.output_tokens), 0).label("output_tokens"),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.user_id == user_id, Message.role == "assistant")
            .group_by(Message.model)
        )
        rows = (await self.session.execute(base)).all()
        by_model = [
            {
                "model": r.model or "(default)",
                "messages": int(r.messages),
                "input_tokens": int(r.input_tokens),
                "output_tokens": int(r.output_tokens),
            }
            for r in rows
        ]
        total = {
            "messages": sum(m["messages"] for m in by_model),
            "input_tokens": sum(m["input_tokens"] for m in by_model),
            "output_tokens": sum(m["output_tokens"] for m in by_model),
        }
        return {"total": total, "by_model": by_model}
