"""Agent 业务逻辑:工具 CRUD + ReAct 运行(落库轨迹 + 助手消息)。

运行编排:
1. prepare_turn:建/取会话、落库用户消息、构建历史(用请求会话,先 commit)。
2. stream_agent:独立会话驱动 ReAct,逐步产出轨迹(供 SSE),回合结束统一落库
   助手消息(最终答复)与 agent_thought 轨迹。

工具挂在 app_id;knowledge_retrieval 若未单独配 dataset_id,回退用应用配置的 dataset_id。
"""

import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.react import AgentStep, RuntimeTool, run_react
from app.agent.tools import BUILTIN_TOOLS, ToolContext, get_builtin_tool
from app.core.config import settings
from app.core.db import async_session
from app.llm.base import Message as LLMMessage
from app.llm.base import Usage
from app.llm.factory import resolve_provider
from app.models.agent import THOUGHT_ANSWER, AgentTool
from app.models.app import AppConfig
from app.models.conversation import Conversation
from app.repositories.agent import AgentThoughtRepository, AgentToolRepository
from app.repositories.conversation import ConversationRepository, MessageRepository


class AgentError(Exception):
    """Agent 业务错误(未找到 / 非法工具)。"""


class AgentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tools = AgentToolRepository(session)
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)

    # ---- 内置工具目录 ----
    @staticmethod
    def builtin_catalog() -> list[dict]:
        return [
            {
                "type": t.type,
                "name": t.default_name,
                "description": t.default_description,
                "parameters": t.parameters,
            }
            for t in BUILTIN_TOOLS.values()
        ]

    # ---- 工具 CRUD ----
    async def list_tools(self, *, app_id: uuid.UUID) -> list[AgentTool]:
        return await self.tools.list_for_app(app_id)

    async def add_tool(
        self,
        *,
        user_id: uuid.UUID,
        app_id: uuid.UUID,
        type: str,
        name: str | None,
        description: str | None,
        config: dict,
    ) -> AgentTool:
        if type not in BUILTIN_TOOLS:
            raise AgentError(f"未知内置工具类型: {type}")
        builtin = get_builtin_tool(type)
        sort_order = await self.tools.max_sort_order(app_id) + 1
        tool = await self.tools.create(
            user_id=user_id,
            app_id=app_id,
            type=type,
            name=name or builtin.default_name,
            description=description,
            config=config or {},
            sort_order=sort_order,
        )
        await self.session.commit()
        await self.session.refresh(tool)
        return tool

    async def update_tool(
        self,
        *,
        app_id: uuid.UUID,
        tool_id: uuid.UUID,
        name: str | None,
        description: str | None,
        is_enabled: bool | None,
        config: dict | None,
    ) -> AgentTool:
        tool = await self.tools.get(tool_id, app_id)
        if tool is None:
            raise AgentError("工具不存在")
        if name is not None:
            tool.name = name
        if description is not None:
            tool.description = description
        if is_enabled is not None:
            tool.is_enabled = is_enabled
        if config is not None:
            tool.config = config
        await self.session.commit()
        await self.session.refresh(tool)
        return tool

    async def delete_tool(self, *, app_id: uuid.UUID, tool_id: uuid.UUID) -> None:
        tool = await self.tools.get(tool_id, app_id)
        if tool is None:
            raise AgentError("工具不存在")
        await self.tools.soft_delete(tool)
        await self.session.commit()

    async def get_message_thoughts(self, message_id: uuid.UUID):
        return await AgentThoughtRepository(self.session).list_for_message(message_id)

    # ---- 运行准备(请求会话内)----
    async def prepare_turn(
        self,
        *,
        user_id: uuid.UUID,
        app_id: uuid.UUID,
        config: AppConfig,
        content: str,
        conversation_id: uuid.UUID | None,
    ) -> tuple[Conversation, str | None, list[LLMMessage]]:
        """建/取会话 + 落库用户消息 + 构建历史。返回 (会话, system, 历史消息)。"""
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
                raise AgentError("会话不存在")

        await self.messages.add(conversation_id=conv.id, role="user", content=content)
        await self.session.commit()

        history_rows = await self.messages.list_for_conversation(conv.id)
        history = [LLMMessage(role=m.role, content=m.content) for m in history_rows]
        return conv, conv.system_prompt, history


def _build_runtime_tools(
    rows: list[AgentTool], *, session: AsyncSession, fallback_dataset_id: uuid.UUID | None
) -> dict[str, RuntimeTool]:
    """把启用的 agent_tool 行装配成运行期工具(按 type 去重,后者覆盖前者)。"""
    runtime: dict[str, RuntimeTool] = {}
    for row in rows:
        if not row.is_enabled or row.type not in BUILTIN_TOOLS:
            continue
        cfg = dict(row.config or {})
        if row.type == "knowledge_retrieval" and not cfg.get("dataset_id") and fallback_dataset_id:
            cfg["dataset_id"] = str(fallback_dataset_id)
        runtime[row.type] = RuntimeTool(
            tool=get_builtin_tool(row.type),
            ctx=ToolContext(session=session, config=cfg),
            description=row.description,
            display_name=row.name,
        )
    return runtime


async def stream_agent(
    *,
    conversation_id: uuid.UUID,
    app_id: uuid.UUID,
    system: str | None,
    history: list[LLMMessage],
    config_model: str | None,
    config_temperature: float | None,
    config_max_tokens: int,
    fallback_dataset_id: uuid.UUID | None,
) -> AsyncIterator[AgentStep]:
    """独立会话驱动 ReAct,逐步产出轨迹;回合结束落库助手消息 + 轨迹。"""
    async with async_session() as session:
        rows = await AgentToolRepository(session).list_for_app(app_id)
        runtime_tools = _build_runtime_tools(
            rows, session=session, fallback_dataset_id=fallback_dataset_id
        )
        provider = resolve_provider(config_model)

        steps: list[AgentStep] = []
        usage = Usage()
        answer = ""
        async for step in run_react(
            provider=provider,
            system=system,
            history=history,
            tools=runtime_tools,
            model=config_model,
            temperature=config_temperature,
            max_tokens=config_max_tokens,
            max_iterations=settings.agent_max_iterations,
        ):
            steps.append(step)
            usage.input_tokens += step.input_tokens
            usage.output_tokens += step.output_tokens
            if step.kind == THOUGHT_ANSWER:
                answer = step.content or ""
            yield step

        # 回合结束:落库助手消息(最终答复)+ 轨迹
        msg = await MessageRepository(session).add(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            model=config_model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        thought_repo = AgentThoughtRepository(session)
        for i, step in enumerate(steps):
            await thought_repo.add(
                conversation_id=conversation_id,
                message_id=msg.id,
                kind=step.kind,
                content=step.content,
                tool_name=step.tool_name,
                tool_input=step.tool_input,
                tool_output=step.tool_output,
                input_tokens=step.input_tokens,
                output_tokens=step.output_tokens,
                elapsed_ms=step.elapsed_ms,
                sort_order=i,
            )
        await ConversationRepository(session).touch(conversation_id)
        await session.commit()
        # 末尾用一个带 message_id 的“答复”步标记落库完成
        yield AgentStep(kind="_persisted", content=str(msg.id))
