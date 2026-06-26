"""LLM 兼容网关 —— 对外同时暴露 OpenAI 与 Anthropic 两种格式的端点。

请求格式与上游 provider 解耦:客户端用 OpenAI SDK 请求 model="claude-*" 也会被路由到
Anthropic 上游(反之亦然),由 factory.resolve_provider 按模型名决定。

TODO(D4):用 auth_api_key 保护这些端点 + 限流计量。当前为 MVP,未鉴权。
"""

import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.llm import wire
from app.llm.factory import provider_for_model, resolve_provider

router = APIRouter(prefix="/v1", tags=["llm-gateway"])


def _sse(data: dict, event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ----------------------------------------------------------------------------
# OpenAI 兼容
# ----------------------------------------------------------------------------
@router.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    req, stream = wire.openai_request_to_internal(body)
    provider = resolve_provider(req.model)
    model = req.model or provider.default_model

    if not stream:
        result = await provider.chat(req)
        return JSONResponse(wire.internal_to_openai_response(result))

    async def gen():
        chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
        yield _sse(wire.openai_stream_chunk(chunk_id, model, delta={"role": "assistant"}))
        async for text in provider.stream(req):
            yield _sse(wire.openai_stream_chunk(chunk_id, model, delta={"content": text}))
        yield _sse(wire.openai_stream_chunk(chunk_id, model, delta={}, finish_reason="stop"))
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    model = body.get("model")
    raw = body.get("input", [])
    texts = [raw] if isinstance(raw, str) else list(raw)
    provider = resolve_provider(model)
    vectors = await provider.embed(texts, model=model)
    return JSONResponse(
        {
            "object": "list",
            "model": model,
            "data": [
                {"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)
            ],
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        }
    )


# ----------------------------------------------------------------------------
# Anthropic 兼容
# ----------------------------------------------------------------------------
@router.post("/messages")
async def messages(request: Request):
    body = await request.json()
    req, stream = wire.anthropic_request_to_internal(body)
    provider = resolve_provider(req.model)
    model = req.model or provider.default_model

    if not stream:
        result = await provider.chat(req)
        return JSONResponse(wire.internal_to_anthropic_response(result))

    async def gen():
        msg_id = f"msg_{uuid.uuid4().hex}"
        start = {
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        }
        yield _sse(start, event="message_start")
        yield _sse(
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            event="content_block_start",
        )
        async for text in provider.stream(req):
            yield _sse(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": text},
                },
                event="content_block_delta",
            )
        yield _sse({"type": "content_block_stop", "index": 0}, event="content_block_stop")
        yield _sse(
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 0},
            },
            event="message_delta",
        )
        yield _sse({"type": "message_stop"}, event="message_stop")

    return StreamingResponse(gen(), media_type="text/event-stream")


# provider_for_model 复导出,便于其他模块/测试引用
__all__ = ["router", "provider_for_model"]
