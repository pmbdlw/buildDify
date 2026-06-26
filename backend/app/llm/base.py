"""LLM provider 抽象 —— 屏蔽厂商差异。

上层(services / workflow / agent)只依赖 LLMProvider 协议,
经 get_provider() 工厂按配置注入具体实现。不在业务里硬编码厂商 SDK。
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ChatResult:
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> ChatResult | AsyncIterator[str]:
        """对话补全。stream=True 时返回文本增量的异步迭代器。"""
        ...

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        """文本向量化。"""
        ...
