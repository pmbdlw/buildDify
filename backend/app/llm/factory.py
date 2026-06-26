"""Provider 工厂 —— 按名称或模型解析具体上游实现(带缓存)。"""

from functools import cache

from app.core.config import settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.openai_provider import OpenAIProvider

_BUILDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


@cache
def get_provider(name: str) -> LLMProvider:
    try:
        return _BUILDERS[name]()
    except KeyError as exc:
        raise ValueError(f"未知 LLM provider: {name}") from exc


def provider_for_model(model: str | None) -> str:
    """按模型名推断上游 provider。"""
    if model:
        m = model.lower()
        if m.startswith("claude"):
            return "anthropic"
        if m.startswith(("gpt", "o1", "o3", "o4", "text-embedding", "deepseek")):
            return "openai"
    return settings.llm_provider


def resolve_provider(model: str | None = None) -> LLMProvider:
    """网关 / 业务取 provider:优先按模型名路由,否则用默认配置。"""
    return get_provider(provider_for_model(model))


def default_provider() -> LLMProvider:
    return get_provider(settings.llm_provider)
