"""Agent 工具 / 思考轨迹数据访问。"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentThought, AgentTool


class AgentToolRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        app_id: uuid.UUID,
        type: str,
        name: str,
        description: str | None,
        config: dict,
        sort_order: int,
    ) -> AgentTool:
        tool = AgentTool(
            user_id=user_id,
            app_id=app_id,
            type=type,
            name=name,
            description=description,
            config=config,
            sort_order=sort_order,
        )
        self.session.add(tool)
        await self.session.flush()
        await self.session.refresh(tool)
        return tool

    async def get(self, tool_id: uuid.UUID, app_id: uuid.UUID) -> AgentTool | None:
        result = await self.session.execute(
            select(AgentTool).where(
                AgentTool.id == tool_id,
                AgentTool.app_id == app_id,
                AgentTool.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_app(self, app_id: uuid.UUID) -> list[AgentTool]:
        result = await self.session.execute(
            select(AgentTool)
            .where(AgentTool.app_id == app_id, AgentTool.deleted_at.is_(None))
            .order_by(AgentTool.sort_order.asc(), AgentTool.created_at.asc())
        )
        return list(result.scalars().all())

    async def max_sort_order(self, app_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(AgentTool.sort_order), -1)).where(
                AgentTool.app_id == app_id, AgentTool.deleted_at.is_(None)
            )
        )
        return int(result.scalar_one())

    async def soft_delete(self, tool: AgentTool) -> None:
        tool.deleted_at = func.now()
        await self.session.flush()


class AgentThoughtRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID | None,
        kind: str,
        content: str | None,
        tool_name: str | None,
        tool_input: dict | None,
        tool_output: str | None,
        input_tokens: int,
        output_tokens: int,
        elapsed_ms: int | None,
        sort_order: int,
    ) -> AgentThought:
        thought = AgentThought(
            conversation_id=conversation_id,
            message_id=message_id,
            kind=kind,
            content=content,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            elapsed_ms=elapsed_ms,
            sort_order=sort_order,
        )
        self.session.add(thought)
        await self.session.flush()
        return thought

    async def list_for_message(self, message_id: uuid.UUID) -> list[AgentThought]:
        result = await self.session.execute(
            select(AgentThought)
            .where(AgentThought.message_id == message_id)
            .order_by(AgentThought.sort_order.asc())
        )
        return list(result.scalars().all())
