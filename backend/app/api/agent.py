"""Agent 路由:工具目录/CRUD + 调试运行(SSE 轨迹) + 轨迹回放。

- /api/apps/{id}/agent/tools*  授权用户:内置工具目录、应用工具 CRUD
- /api/apps/{id}/agent/chat    调试:用最新配置驱动 ReAct,SSE 推送思考/工具/答复轨迹
- /api/conversations/{cid}/messages/{mid}/thoughts  按消息回放轨迹
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.llm.factory import resolve_provider
from app.models.user import User
from app.repositories.agent import AgentThoughtRepository
from app.repositories.conversation import ConversationRepository
from app.schemas.agent import (
    AgentChatIn,
    AgentThoughtOut,
    AgentToolIn,
    AgentToolOut,
    AgentToolUpdate,
    BuiltinToolOut,
)
from app.services.agent import AgentError, AgentService, stream_agent
from app.services.app import AppError, AppService

router = APIRouter(tags=["agent"])


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _ensure_app(session: AsyncSession, app_id: uuid.UUID, user_id: uuid.UUID):
    try:
        return await AppService(session).get_app(app_id, user_id)
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---- 内置工具目录 ----
@router.get("/apps/{app_id}/agent/tools/catalog", response_model=list[BuiltinToolOut])
async def builtin_catalog(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_app(session, app_id, current_user.id)
    return AgentService.builtin_catalog()


# ---- 应用工具 CRUD ----
@router.get("/apps/{app_id}/agent/tools", response_model=list[AgentToolOut])
async def list_tools(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_app(session, app_id, current_user.id)
    return await AgentService(session).list_tools(app_id=app_id)


@router.post(
    "/apps/{app_id}/agent/tools",
    response_model=AgentToolOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_tool(
    app_id: uuid.UUID,
    data: AgentToolIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_app(session, app_id, current_user.id)
    try:
        return await AgentService(session).add_tool(
            user_id=current_user.id,
            app_id=app_id,
            type=data.type,
            name=data.name,
            description=data.description,
            config=data.config,
        )
    except AgentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/apps/{app_id}/agent/tools/{tool_id}", response_model=AgentToolOut)
async def update_tool(
    app_id: uuid.UUID,
    tool_id: uuid.UUID,
    data: AgentToolUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_app(session, app_id, current_user.id)
    try:
        return await AgentService(session).update_tool(
            app_id=app_id,
            tool_id=tool_id,
            name=data.name,
            description=data.description,
            is_enabled=data.is_enabled,
            config=data.config,
        )
    except AgentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/apps/{app_id}/agent/tools/{tool_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_tool(
    app_id: uuid.UUID,
    tool_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_app(session, app_id, current_user.id)
    try:
        await AgentService(session).delete_tool(app_id=app_id, tool_id=tool_id)
    except AgentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---- 调试运行(SSE 轨迹)----
@router.post("/apps/{app_id}/agent/chat")
async def agent_debug_chat(
    app_id: uuid.UUID,
    data: AgentChatIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """用最新配置驱动 ReAct,SSE 实时推送思考/工具调用/观测/答复轨迹。"""
    app_service = AppService(session)
    try:
        config = await app_service.get_debug_config(app_id, current_user.id)
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    agent_service = AgentService(session)
    try:
        conv, system, history = await agent_service.prepare_turn(
            user_id=current_user.id,
            app_id=app_id,
            config=config,
            content=data.content,
            conversation_id=data.conversation_id,
        )
    except AgentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    conv_id = conv.id
    model_name = config.model or resolve_provider(config.model).default_model
    cfg_model = config.model
    cfg_temp = config.temperature
    cfg_max = config.max_tokens
    dataset_id = config.dataset_id

    async def gen():
        yield _sse({"type": "meta", "conversation_id": str(conv_id), "model": model_name})
        try:
            async for step in stream_agent(
                conversation_id=conv_id,
                app_id=app_id,
                system=system,
                history=history,
                config_model=cfg_model,
                config_temperature=cfg_temp,
                config_max_tokens=cfg_max,
                fallback_dataset_id=dataset_id,
            ):
                if step.kind == "_persisted":
                    yield _sse({"type": "done", "message_id": step.content})
                elif step.kind == "thought":
                    yield _sse({"type": "thought", "content": step.content})
                elif step.kind == "tool_call":
                    yield _sse(
                        {"type": "tool_call", "tool": step.tool_name, "input": step.tool_input}
                    )
                elif step.kind == "observation":
                    yield _sse(
                        {"type": "observation", "tool": step.tool_name, "output": step.tool_output}
                    )
                elif step.kind == "answer":
                    yield _sse({"type": "answer", "content": step.content})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---- 轨迹回放 ----
@router.get(
    "/conversations/{conversation_id}/messages/{message_id}/thoughts",
    response_model=list[AgentThoughtOut],
)
async def message_thoughts(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = await ConversationRepository(session).get(conversation_id, current_user.id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return await AgentThoughtRepository(session).list_for_message(message_id)
