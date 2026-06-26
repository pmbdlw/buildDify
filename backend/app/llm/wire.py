"""下游网关的线格式转换 —— 在 OpenAI / Anthropic 客户端格式与内部统一表示间互转。

全部为纯函数,便于离线单测。id/时间戳由调用方或此处生成(普通 Python,无副作用依赖)。
"""

import time
import uuid

from app.llm.base import ChatRequest, ChatResult, Message, ToolSpec

# 统一 stop_reason → OpenAI finish_reason
_TO_OPENAI_FINISH = {
    "end_turn": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "stop": "stop",
}
# 统一 stop_reason → Anthropic stop_reason
_TO_ANTHROPIC_STOP = {
    "end_turn": "end_turn",
    "max_tokens": "max_tokens",
    "tool_use": "tool_use",
    "stop": "end_turn",
}


def _now() -> int:
    return int(time.time())


# ----------------------------------------------------------------------------
# OpenAI 格式(/v1/chat/completions)
# ----------------------------------------------------------------------------
def openai_request_to_internal(body: dict) -> tuple[ChatRequest, bool]:
    """OpenAI Chat Completions 请求 → (ChatRequest, stream?)。

    system 角色消息被抽出合并为 ChatRequest.system。
    """
    system_parts: list[str] = []
    messages: list[Message] = []
    for m in body.get("messages", []):
        role = m.get("role")
        content = m.get("content")
        # content 可能是字符串或多模态分块列表;MVP 仅取文本
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        content = content or ""
        if role == "system":
            system_parts.append(content)
        elif role in ("user", "assistant"):
            messages.append(Message(role=role, content=content))

    tools = None
    if body.get("tools"):
        tools = [
            ToolSpec(
                name=t["function"]["name"],
                description=t["function"].get("description", ""),
                parameters=t["function"].get("parameters", {}),
            )
            for t in body["tools"]
            if t.get("type") == "function"
        ]

    req = ChatRequest(
        messages=messages,
        model=body.get("model"),
        system="\n\n".join(system_parts) if system_parts else None,
        tools=tools,
        temperature=body.get("temperature"),
        max_tokens=body.get("max_tokens") or 1024,
    )
    return req, bool(body.get("stream"))


def internal_to_openai_response(result: ChatResult) -> dict:
    message: dict = {"role": "assistant", "content": result.content or None}
    if result.tool_calls:
        message["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": _dumps(tc.arguments)},
            }
            for tc in result.tool_calls
        ]
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": _now(),
        "model": result.model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": _TO_OPENAI_FINISH.get(result.stop_reason, "stop"),
            }
        ],
        "usage": {
            "prompt_tokens": result.usage.input_tokens,
            "completion_tokens": result.usage.output_tokens,
            "total_tokens": result.usage.input_tokens + result.usage.output_tokens,
        },
    }


def openai_stream_chunk(chunk_id: str, model: str, *, delta: dict, finish_reason=None) -> dict:
    return {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": _now(),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


# ----------------------------------------------------------------------------
# Anthropic 格式(/v1/messages)
# ----------------------------------------------------------------------------
def anthropic_request_to_internal(body: dict) -> tuple[ChatRequest, bool]:
    """Anthropic Messages 请求 → (ChatRequest, stream?)。"""
    messages: list[Message] = []
    for m in body.get("messages", []):
        role = m.get("role")
        content = m.get("content")
        if isinstance(content, list):
            content = "".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
        messages.append(Message(role=role, content=content or ""))

    system = body.get("system")
    if isinstance(system, list):  # Anthropic system 也可为分块
        system = "".join(b.get("text", "") for b in system if isinstance(b, dict))

    tools = None
    if body.get("tools"):
        tools = [
            ToolSpec(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("input_schema", {}),
            )
            for t in body["tools"]
        ]

    req = ChatRequest(
        messages=messages,
        model=body.get("model"),
        system=system or None,
        tools=tools,
        temperature=body.get("temperature"),
        max_tokens=body.get("max_tokens") or 1024,
    )
    return req, bool(body.get("stream"))


def internal_to_anthropic_response(result: ChatResult) -> dict:
    content: list[dict] = []
    if result.content:
        content.append({"type": "text", "text": result.content})
    for tc in result.tool_calls:
        content.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
    return {
        "id": f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "role": "assistant",
        "model": result.model,
        "content": content,
        "stop_reason": _TO_ANTHROPIC_STOP.get(result.stop_reason, "end_turn"),
        "stop_sequence": None,
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
        },
    }


def _dumps(obj: dict) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
