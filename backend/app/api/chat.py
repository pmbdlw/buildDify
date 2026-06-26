"""对话路由:流式聊天 + 会话/历史查询。"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.llm.base import Usage
from app.llm.factory import resolve_provider
from app.models.user import User
from app.repositories.conversation import ConversationRepository, MessageRepository
from app.schemas.chat import ChatIn, ConversationOut, MessageOut
from app.services.conversation import ConversationService, persist_assistant_message

router = APIRouter(tags=["chat"])


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(
    data: ChatIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """发送一条消息,SSE 流式返回助手回复;用户消息即时落库,助手消息流结束后落库。"""
    service = ConversationService(session)
    try:
        conv, req, citations = await service.start_turn(
            user_id=current_user.id,
            content=data.content,
            conversation_id=data.conversation_id,
            model=data.model,
            dataset_id=data.dataset_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    provider = resolve_provider(req.model)
    model_name = req.model or provider.default_model
    conv_id = conv.id
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
        # 用量在流式下未必可得,这里以 0 落库(后续可改用非流式或 message_delta 统计)
        msg_id = await persist_assistant_message(
            conversation_id=conv_id, content=full, model=model_name, usage=Usage()
        )
        yield _sse({"type": "done", "message_id": str(msg_id)})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ConversationRepository(session).list_for_user(current_user.id)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def conversation_messages(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = await ConversationRepository(session).get(conversation_id, current_user.id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return await MessageRepository(session).list_for_conversation(conversation_id)
