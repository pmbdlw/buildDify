"""应用构建器路由。

- /api/apps        授权用户:应用 CRUD、配置版本化、发布、调试 SSE、API Key 管理
- /v1/apps/{id}/chat  对外:按 API Key 鉴权,按已发布配置运行
"""

import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.llm.base import ChatRequest, Usage
from app.llm.factory import resolve_provider
from app.models.app import App, AppConfig
from app.models.user import User
from app.schemas.app import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    AppChatIn,
    AppConfigIn,
    AppConfigOut,
    AppCreate,
    AppOut,
    AppUpdate,
)
from app.services.app import ApiKeyService, AppError, AppService
from app.services.conversation import ConversationService, persist_assistant_message

router = APIRouter(prefix="/apps", tags=["apps"])
public_router = APIRouter(prefix="/v1/apps", tags=["apps-public"])


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _run_app_chat(conv_id: uuid.UUID, req: ChatRequest, citations) -> StreamingResponse:
    """复用对话链路的 SSE 流式运行,助手回复在流结束后落库。"""
    provider = resolve_provider(req.model)
    model_name = req.model or provider.default_model
    citations_payload = [
        {
            "index": c.index,
            "document_id": str(c.document_id),
            "content": c.content,
            "score": c.score,
        }
        for c in citations
    ]

    async def gen():
        yield _sse(
            {
                "type": "meta",
                "conversation_id": str(conv_id),
                "model": model_name,
                "citations": citations_payload,
            }
        )
        parts: list[str] = []
        try:
            async for text in provider.stream(req):
                parts.append(text)
                yield _sse({"type": "delta", "content": text})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)})
            return
        full = "".join(parts)
        msg_id = await persist_assistant_message(
            conversation_id=conv_id, content=full, model=model_name, usage=Usage()
        )
        yield _sse({"type": "done", "message_id": str(msg_id)})

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---- 应用 CRUD ----
@router.post("", response_model=AppOut, status_code=status.HTTP_201_CREATED)
async def create_app(
    data: AppCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    app = await AppService(session).create_app(
        user_id=current_user.id, name=data.name, description=data.description, mode=data.mode
    )
    return app


@router.get("", response_model=list[AppOut])
async def list_apps(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await AppService(session).list_apps(current_user.id)


@router.get("/{app_id}", response_model=AppOut)
async def get_app(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await AppService(session).get_app(app_id, current_user.id)
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{app_id}", response_model=AppOut)
async def update_app(
    app_id: uuid.UUID,
    data: AppUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await AppService(session).update_app(
            app_id=app_id, user_id=current_user.id, name=data.name, description=data.description
        )
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_app(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        await AppService(session).delete_app(app_id=app_id, user_id=current_user.id)
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---- 配置(版本化)----
@router.get("/{app_id}/config", response_model=AppConfigOut)
async def get_config(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await AppService(session).get_latest_config(app_id, current_user.id)
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/{app_id}/config", response_model=AppConfigOut)
async def save_config(
    app_id: uuid.UUID,
    data: AppConfigIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await AppService(session).save_config(
            app_id=app_id,
            user_id=current_user.id,
            model=data.model,
            system_prompt=data.system_prompt,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            dataset_id=data.dataset_id,
        )
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{app_id}/publish", response_model=AppOut)
async def publish_app(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await AppService(session).publish(app_id=app_id, user_id=current_user.id)
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ---- 调试对话 ----
@router.post("/{app_id}/chat")
async def debug_chat(
    app_id: uuid.UUID,
    data: AppChatIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """调试窗:用最新配置版本运行对话(无需发布)。"""
    app_service = AppService(session)
    try:
        config = await app_service.get_debug_config(app_id, current_user.id)
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    conv_service = ConversationService(session)
    try:
        conv, req, citations = await conv_service.start_app_turn(
            user_id=current_user.id,
            app_id=app_id,
            config=config,
            content=data.content,
            conversation_id=data.conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _run_app_chat(conv.id, req, citations)


# ---- API Key 管理 ----
@router.post("/{app_id}/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    app_id: uuid.UUID,
    data: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        key, raw = await ApiKeyService(session).create_key(
            app_id=app_id, user_id=current_user.id, name=data.name
        )
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiKeyCreated(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        last_used_at=key.last_used_at,
        created_at=key.created_at,
        key=raw,
    )


@router.get("/{app_id}/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await ApiKeyService(session).list_keys(app_id=app_id, user_id=current_user.id)
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{app_id}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    app_id: uuid.UUID,
    key_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        await ApiKeyService(session).revoke_key(
            app_id=app_id, key_id=key_id, user_id=current_user.id
        )
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---- 对外运行接口(API Key 鉴权)----
def _extract_api_key(authorization: str | None, x_api_key: str | None) -> str:
    if x_api_key:
        return x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 API Key"
    )


async def _authenticate_app(
    app_id: uuid.UUID, session: AsyncSession, raw: str
) -> tuple[App, AppConfig]:
    try:
        _, app, config = await ApiKeyService(session).authenticate(raw)
    except AppError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    if app.id != app_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="API Key 与应用不匹配"
        )
    return app, config


@public_router.post("/{app_id}/chat")
async def public_app_chat(
    app_id: uuid.UUID,
    data: AppChatIn,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
):
    """对外运行:按 API Key 鉴权,按已发布配置驱动对话(SSE)。"""
    raw = _extract_api_key(authorization, x_api_key)
    app, config = await _authenticate_app(app_id, session, raw)

    conv_service = ConversationService(session)
    try:
        conv, req, citations = await conv_service.start_app_turn(
            user_id=app.user_id,  # 对外调用归属应用所有者
            app_id=app.id,
            config=config,
            content=data.content,
            conversation_id=data.conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _run_app_chat(conv.id, req, citations)
