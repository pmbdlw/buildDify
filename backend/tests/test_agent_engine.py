"""Agent 引擎单测 —— 内置工具(代码执行)+ ReAct 循环(stub provider,不触网/不连库)。"""

import pytest
from app.agent.react import RuntimeTool, run_react
from app.agent.tools import BUILTIN_TOOLS, AgentToolError, ToolContext, get_builtin_tool
from app.llm.base import ChatResult, ToolCall, Usage


async def test_code_exec_tool_returns_result():
    tool = BUILTIN_TOOLS["code_exec"]
    out = await tool.execute({"code": "result = 2 + 3"}, ToolContext(session=None))
    assert out == "5"


async def test_code_exec_tool_requires_code():
    tool = BUILTIN_TOOLS["code_exec"]
    with pytest.raises(AgentToolError):
        await tool.execute({"code": "   "}, ToolContext(session=None))


async def test_http_tool_rejects_non_http():
    tool = BUILTIN_TOOLS["http_request"]
    with pytest.raises(AgentToolError):
        await tool.execute({"url": "ftp://x"}, ToolContext(session=None))


class _StubProvider:
    default_model = "stub-model"

    def __init__(self, scripted: list[ChatResult]) -> None:
        self._scripted = scripted
        self.calls = 0

    async def chat(self, req):  # noqa: ANN001
        result = self._scripted[self.calls]
        self.calls += 1
        return result


async def test_react_tool_then_answer():
    scripted = [
        ChatResult(
            content="让我算一下",
            model="stub-model",
            usage=Usage(input_tokens=10, output_tokens=5),
            tool_calls=[ToolCall(id="t1", name="code_exec", arguments={"code": "result = 21 * 2"})],
            stop_reason="tool_use",
        ),
        ChatResult(
            content="答案是 42",
            model="stub-model",
            usage=Usage(input_tokens=8, output_tokens=4),
            tool_calls=[],
            stop_reason="end_turn",
        ),
    ]
    provider = _StubProvider(scripted)
    tools = {
        "code_exec": RuntimeTool(
            tool=get_builtin_tool("code_exec"), ctx=ToolContext(session=None)
        )
    }
    steps = []
    async for step in run_react(
        provider=provider,
        system=None,
        history=[],
        tools=tools,
        model=None,
        temperature=None,
        max_tokens=256,
        max_iterations=4,
    ):
        steps.append(step)

    kinds = [s.kind for s in steps]
    assert kinds == ["thought", "tool_call", "observation", "answer"]
    assert steps[1].tool_name == "code_exec"
    assert steps[2].tool_output == "42"
    assert steps[3].content == "答案是 42"
    # token 累计来自两次模型调用
    assert sum(s.input_tokens for s in steps) == 18


async def test_react_unknown_tool_is_observed_not_raised():
    scripted = [
        ChatResult(
            content="",
            model="stub-model",
            usage=Usage(),
            tool_calls=[ToolCall(id="t1", name="nope", arguments={})],
            stop_reason="tool_use",
        ),
        ChatResult(content="收到", model="stub-model", usage=Usage(), stop_reason="end_turn"),
    ]
    provider = _StubProvider(scripted)
    steps = [s async for s in run_react(
        provider=provider, system=None, history=[], tools={}, model=None,
        temperature=None, max_tokens=64, max_iterations=4,
    )]
    obs = [s for s in steps if s.kind == "observation"]
    assert obs and "未启用" in (obs[0].tool_output or "")
