"""LLM 统一抽象 —— 屏蔽 Anthropic 与 OpenAI 两种上游格式的差异。

上层(services / workflow / agent / 网关)只面向这里的统一类型,
经 factory.resolve_provider() / get_provider() 取得具体实现。
不在业务里直接 import 厂商 SDK。
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

# 统一的停止原因。各 provider 把厂商 stop/finish 映射到这里。
StopReason = str  # "end_turn" | "max_tokens" | "tool_use" | "stop"


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema(对应 OpenAI function.parameters / Anthropic input_schema)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ChatRequest:
    messages: list[Message]
    model: str | None = None
    system: str | None = None
    tools: list[ToolSpec] | None = None
    temperature: float | None = None
    max_tokens: int = 1024


@dataclass
class ChatResult:
    content: str
    model: str
    usage: Usage = field(default_factory=Usage)
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: StopReason = "end_turn"


class LLMProvider(Protocol):
    """上游模型 provider 协议。"""

    name: str
    default_model: str

    async def chat(self, req: ChatRequest) -> ChatResult:
        """非流式对话补全。"""
        ...

    def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        """流式对话补全,逐段产出文本增量(async generator)。"""
        ...

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        """文本向量化。"""
        ...
