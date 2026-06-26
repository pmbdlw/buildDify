"""OpenAI / OpenAI 兼容上游适配 —— Chat Completions API。

改 base_url 即可对接任意 OpenAI 兼容服务(DeepSeek、vLLM、Ollama、本地等)。
"""

import json
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.core.config import settings
from app.llm.base import ChatRequest, ChatResult, ToolCall, ToolSpec, Usage

# OpenAI finish_reason → 统一 stop_reason
_STOP_MAP = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
}


def to_openai_tools(tools: list[ToolSpec] | None) -> list[dict] | None:
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
        }
        for t in tools
    ]


def to_openai_messages(req: ChatRequest) -> list[dict]:
    msgs: list[dict] = []
    if req.system:
        msgs.append({"role": "system", "content": req.system})
    msgs.extend({"role": m.role, "content": m.content} for m in req.messages)
    return msgs


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key or "sk-noop",
            base_url=settings.openai_base_url,
        )
        self.default_model = settings.openai_default_model

    def _common(self, req: ChatRequest) -> dict:
        payload: dict = {
            "model": req.model or self.default_model,
            "messages": to_openai_messages(req),
            "max_tokens": req.max_tokens,
        }
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        tools = to_openai_tools(req.tools)
        if tools:
            payload["tools"] = tools
        return payload

    async def chat(self, req: ChatRequest) -> ChatResult:
        resp = await self._client.chat.completions.create(**self._common(req))
        choice = resp.choices[0]
        msg = choice.message
        tool_calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        usage = resp.usage
        return ChatResult(
            content=msg.content or "",
            model=resp.model,
            usage=Usage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
            tool_calls=tool_calls,
            stop_reason=_STOP_MAP.get(choice.finish_reason or "", "end_turn"),
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(**self._common(req), stream=True)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        resp = await self._client.embeddings.create(
            model=model or settings.embedding_model, input=texts
        )
        return [d.embedding for d in resp.data]
