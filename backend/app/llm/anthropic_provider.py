"""Anthropic(Claude)上游适配 —— Messages API。"""

from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from app.core.config import settings
from app.llm.base import ChatRequest, ChatResult, ToolCall, ToolSpec, Usage

# Anthropic stop_reason → 统一 stop_reason
_STOP_MAP = {
    "end_turn": "end_turn",
    "max_tokens": "max_tokens",
    "tool_use": "tool_use",
    "stop_sequence": "stop",
}


def to_anthropic_tools(tools: list[ToolSpec] | None) -> list[dict] | None:
    if not tools:
        return None
    return [
        {"name": t.name, "description": t.description, "input_schema": t.parameters}
        for t in tools
    ]


def _messages_payload(req: ChatRequest) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in req.messages]


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        kwargs: dict = {"api_key": settings.anthropic_api_key}
        if settings.anthropic_base_url:
            kwargs["base_url"] = settings.anthropic_base_url
        self._client = AsyncAnthropic(**kwargs)
        self.default_model = settings.anthropic_default_model

    def _common(self, req: ChatRequest) -> dict:
        payload: dict = {
            "model": req.model or self.default_model,
            "max_tokens": req.max_tokens,
            "messages": _messages_payload(req),
        }
        if req.system:
            payload["system"] = req.system
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        tools = to_anthropic_tools(req.tools)
        if tools:
            payload["tools"] = tools
        return payload

    async def chat(self, req: ChatRequest) -> ChatResult:
        resp = await self._client.messages.create(**self._common(req))
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))
        return ChatResult(
            content="".join(text_parts),
            model=resp.model,
            usage=Usage(
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
            ),
            tool_calls=tool_calls,
            stop_reason=_STOP_MAP.get(resp.stop_reason or "", "end_turn"),
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        async with self._client.messages.stream(**self._common(req)) as stream:
            async for text in stream.text_stream:
                yield text

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        raise NotImplementedError(
            "Anthropic 无原生 embedding 接口,请将 llm embedding 配置为 OpenAI 兼容端点"
        )
