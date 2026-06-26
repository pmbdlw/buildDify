"""兼容网关集成测试 —— 用 FakeProvider 替换上游,无需 API key / 网络。

验证:OpenAI SDK 与 Anthropic SDK 两种请求格式都能打通,且与上游 provider 解耦。
"""

from collections.abc import AsyncIterator

import pytest
from app.llm.base import ChatRequest, ChatResult, Usage
from app.main import app
from fastapi.testclient import TestClient


class FakeProvider:
    name = "fake"
    default_model = "fake-model"

    async def chat(self, req: ChatRequest) -> ChatResult:
        # 回显最后一条用户消息,便于断言
        last = req.messages[-1].content if req.messages else ""
        return ChatResult(content=f"echo:{last}", model=req.model or self.default_model, usage=Usage(2, 3))

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        for piece in ["hel", "lo"]:
            yield piece

    async def embed(self, texts, *, model=None):
        return [[0.1, 0.2, 0.3] for _ in texts]


@pytest.fixture(autouse=True)
def _patch_provider(monkeypatch):
    monkeypatch.setattr("app.api.llm_gateway.resolve_provider", lambda model=None: FakeProvider())


client = TestClient(app)


def test_openai_chat_completions_non_stream():
    r = client.post(
        "/v1/chat/completions",
        json={"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "echo:hi"


def test_openai_chat_completions_stream():
    r = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "x"}], "stream": True},
    )
    assert r.status_code == 200
    body = r.text
    assert "chat.completion.chunk" in body
    assert '"content": "hel"' in body
    assert "data: [DONE]" in body


def test_anthropic_messages_non_stream():
    r = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "message"
    assert data["content"][0]["text"] == "echo:hi"


def test_anthropic_messages_stream_event_sequence():
    r = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "x"}],
            "stream": True,
        },
    )
    assert r.status_code == 200
    body = r.text
    for ev in ["message_start", "content_block_delta", "message_stop"]:
        assert f"event: {ev}" in body
    assert '"text": "hel"' in body


def test_embeddings_openai_format():
    r = client.post("/v1/embeddings", json={"model": "text-embedding-3-small", "input": ["a", "b"]})
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 2
    assert data["data"][0]["embedding"] == [0.1, 0.2, 0.3]
