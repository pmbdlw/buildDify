"""对话业务逻辑:建会话、存消息、构建 LLM 请求、落库助手回复。

流式场景下,用户消息在请求开始即落库并 commit;助手回复在流结束后用
独立会话落库(generator 跨越响应生命周期,不复用注入的会话)。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session
from app.llm.base import ChatRequest, Usage
from app.llm.base import Message as LLMMessage
from app.models.conversation import Conversation
from app.repositories.conversation import ConversationRepository, MessageRepository


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)

    async def start_turn(
        self,
        *,
        user_id: uuid.UUID,
        content: str,
        conversation_id: uuid.UUID | None,
        model: str | None,
    ) -> tuple[Conversation, ChatRequest]:
        """建/取会话 + 落库用户消息 + 构建 ChatRequest(含历史)。"""
        if conversation_id is None:
            conv = await self.conversations.create(
                user_id=user_id,
                title=content[:30] or "新对话",
                model=model,
                system_prompt=None,
            )
        else:
            conv = await self.conversations.get(conversation_id, user_id)
            if conv is None:
                raise ValueError("会话不存在")

        await self.messages.add(conversation_id=conv.id, role="user", content=content)
        await self.session.commit()

        history = await self.messages.list_for_conversation(conv.id)
        req = ChatRequest(
            messages=[LLMMessage(role=m.role, content=m.content) for m in history],
            model=model or conv.model,
            system=conv.system_prompt,
        )
        return conv, req


async def persist_assistant_message(
    *, conversation_id: uuid.UUID, content: str, model: str | None, usage: Usage
) -> uuid.UUID:
    """流结束后用独立会话落库助手消息,并刷新会话时间。"""
    async with async_session() as session:
        repo = MessageRepository(session)
        msg = await repo.add(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        await ConversationRepository(session).touch(conversation_id)
        await session.commit()
        return msg.id
