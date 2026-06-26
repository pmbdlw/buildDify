"""对话业务逻辑:建会话、存消息、构建 LLM 请求、落库助手回复。

流式场景下,用户消息在请求开始即落库并 commit;助手回复在流结束后用
独立会话落库(generator 跨越响应生命周期,不复用注入的会话)。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session
from app.llm.base import ChatRequest, Usage
from app.llm.base import Message as LLMMessage
from app.models.app import AppConfig
from app.models.conversation import Conversation
from app.repositories.conversation import ConversationRepository, MessageRepository
from app.services.retrieval import Citation, RetrievalService, build_rag_system_prompt


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
        dataset_id: uuid.UUID | None = None,
    ) -> tuple[Conversation, ChatRequest, list[Citation]]:
        """建/取会话 + 落库用户消息 + 构建 ChatRequest(含历史);选中知识库则做 RAG 检索。"""
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

        # RAG:基于本轮用户输入检索知识库,把片段注入 system,并回传引用
        citations: list[Citation] = []
        system = conv.system_prompt
        if dataset_id is not None:
            citations = await RetrievalService(self.session).retrieve(
                dataset_id=dataset_id, query=content
            )
            if citations:
                system = build_rag_system_prompt(conv.system_prompt, citations)

        history = await self.messages.list_for_conversation(conv.id)
        req = ChatRequest(
            messages=[LLMMessage(role=m.role, content=m.content) for m in history],
            model=model or conv.model,
            system=system,
        )
        return conv, req, citations

    async def start_app_turn(
        self,
        *,
        user_id: uuid.UUID,
        app_id: uuid.UUID,
        config: AppConfig,
        content: str,
        conversation_id: uuid.UUID | None,
    ) -> tuple[Conversation, ChatRequest, list[Citation]]:
        """按应用配置驱动一轮对话:模型/system/参数/绑定知识库均取自 config。"""
        if conversation_id is None:
            conv = await self.conversations.create(
                user_id=user_id,
                title=content[:30] or "新对话",
                model=config.model,
                system_prompt=config.system_prompt,
                app_id=app_id,
            )
        else:
            conv = await self.conversations.get_for_app(conversation_id, app_id)
            if conv is None:
                raise ValueError("会话不存在")

        await self.messages.add(conversation_id=conv.id, role="user", content=content)
        await self.session.commit()

        citations: list[Citation] = []
        system = conv.system_prompt
        if config.dataset_id is not None:
            citations = await RetrievalService(self.session).retrieve(
                dataset_id=config.dataset_id, query=content
            )
            if citations:
                system = build_rag_system_prompt(conv.system_prompt, citations)

        history = await self.messages.list_for_conversation(conv.id)
        req = ChatRequest(
            messages=[LLMMessage(role=m.role, content=m.content) for m in history],
            model=config.model,
            system=system,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        return conv, req, citations


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
