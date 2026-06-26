"""LLM 线格式转换单测(纯函数,无网络)。"""

from app.llm.anthropic_provider import to_anthropic_tools
from app.llm.base import ChatResult, ToolCall, ToolSpec, Usage
from app.llm.factory import provider_for_model
from app.llm.openai_provider import to_openai_messages, to_openai_tools
from app.llm.wire import (
    anthropic_request_to_internal,
    internal_to_anthropic_response,
    internal_to_openai_response,
    openai_request_to_internal,
)


def test_openai_request_extracts_system_and_messages():
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好"},
        ],
        "temperature": 0.5,
        "stream": True,
    }
    req, stream = openai_request_to_internal(body)
    assert stream is True
    assert req.system == "你是助手"
    assert len(req.messages) == 1
    assert req.messages[0].role == "user"
    assert req.temperature == 0.5


def test_anthropic_request_handles_block_content():
    body = {
        "model": "claude-sonnet-4-6",
        "system": "be brief",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        "max_tokens": 256,
    }
    req, stream = anthropic_request_to_internal(body)
    assert stream is False
    assert req.system == "be brief"
    assert req.messages[0].content == "hi"
    assert req.max_tokens == 256


def test_tool_spec_round_trips_both_formats():
    tool = ToolSpec(name="get_weather", description="天气", parameters={"type": "object"})
    oai = to_openai_tools([tool])[0]
    assert oai["type"] == "function"
    assert oai["function"]["name"] == "get_weather"
    assert oai["function"]["parameters"] == {"type": "object"}

    ant = to_anthropic_tools([tool])[0]
    assert ant["name"] == "get_weather"
    assert ant["input_schema"] == {"type": "object"}


def test_internal_to_openai_response_shape():
    result = ChatResult(content="hi", model="gpt-4o-mini", usage=Usage(3, 5))
    out = internal_to_openai_response(result)
    assert out["object"] == "chat.completion"
    assert out["choices"][0]["message"]["content"] == "hi"
    assert out["choices"][0]["finish_reason"] == "stop"
    assert out["usage"]["total_tokens"] == 8


def test_internal_to_anthropic_response_with_tool_call():
    result = ChatResult(
        content="",
        model="claude-sonnet-4-6",
        usage=Usage(3, 5),
        tool_calls=[ToolCall(id="t1", name="f", arguments={"a": 1})],
        stop_reason="tool_use",
    )
    out = internal_to_anthropic_response(result)
    assert out["type"] == "message"
    assert out["stop_reason"] == "tool_use"
    assert out["content"][0]["type"] == "tool_use"
    assert out["content"][0]["input"] == {"a": 1}


def test_provider_routing_by_model_name():
    assert provider_for_model("claude-opus-4-8") == "anthropic"
    assert provider_for_model("gpt-4o-mini") == "openai"
    assert provider_for_model("deepseek-chat") == "openai"
    assert provider_for_model("text-embedding-3-small") == "openai"


def test_to_openai_messages_prepends_system():
    from app.llm.base import ChatRequest, Message

    req = ChatRequest(messages=[Message("user", "hi")], system="sys")
    msgs = to_openai_messages(req)
    assert msgs[0] == {"role": "system", "content": "sys"}
    assert msgs[1] == {"role": "user", "content": "hi"}
