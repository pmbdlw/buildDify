"""ReAct 循环:模型自主决定调用工具,执行后把观测回灌,直至产出最终答复。

驱动方式(function calling):
1. 带工具规格调用 provider.chat。
2. 若返回 tool_use:把(可选的)思考文本记为 thought,逐个执行工具记 tool_call/observation,
   将 assistant(tool_calls)与 tool(结果)消息追加进上下文,进入下一轮。
3. 若无工具调用:返回内容即最终 answer,结束。
4. 达到 max_iterations 仍未收敛:用最后一次内容兜底为 answer。

以异步生成器逐步产出 AgentStep,便于上层 SSE 实时推送轨迹并落库。
"""

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.agent.tools import BuiltinTool, ToolContext
from app.llm.base import ChatRequest, Message, ToolCall
from app.llm.base import Message as LLMMessage
from app.models.agent import (
    THOUGHT_ANSWER,
    THOUGHT_OBSERVATION,
    THOUGHT_THINK,
    THOUGHT_TOOL_CALL,
)


@dataclass
class AgentStep:
    kind: str  # thought | tool_call | observation | answer
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: int | None = None


@dataclass
class RuntimeTool:
    """运行期工具:内置工具定义 + 该 Agent 的执行上下文(配置/会话)+ 展示用描述。"""

    tool: BuiltinTool
    ctx: ToolContext
    description: str | None = None
    display_name: str | None = None


async def run_react(
    *,
    provider: Any,
    system: str | None,
    history: list[Message],
    tools: dict[str, RuntimeTool],
    model: str | None,
    temperature: float | None,
    max_tokens: int,
    max_iterations: int = 6,
) -> AsyncIterator[AgentStep]:
    """运行一轮 ReAct,异步产出轨迹步骤。history 已含本轮用户输入。"""
    messages: list[Message] = list(history)
    specs = [rt.tool.to_spec(rt.description) for rt in tools.values()]

    last_text = ""
    for _ in range(max_iterations):
        started = time.perf_counter()
        result = await provider.chat(
            ChatRequest(
                messages=messages,
                model=model,
                system=system,
                tools=specs or None,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )
        elapsed = int((time.perf_counter() - started) * 1000)
        last_text = result.content or last_text

        if result.tool_calls and result.stop_reason == "tool_use":
            # 工具调用前的思考文本(如有)
            if result.content and result.content.strip():
                yield AgentStep(
                    kind=THOUGHT_THINK,
                    content=result.content,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    elapsed_ms=elapsed,
                )
            # 记录这一 assistant 轮(含 tool_calls)到上下文
            messages.append(
                LLMMessage(
                    role="assistant", content=result.content or "", tool_calls=result.tool_calls
                )
            )
            for tc in result.tool_calls:
                yield AgentStep(
                    kind=THOUGHT_TOOL_CALL,
                    tool_name=tc.name,
                    tool_input=tc.arguments,
                )
                output = await _run_tool(tc, tools)
                yield AgentStep(
                    kind=THOUGHT_OBSERVATION,
                    tool_name=tc.name,
                    tool_output=output,
                )
                messages.append(
                    LLMMessage(role="tool", content=output, tool_call_id=tc.id)
                )
            continue

        # 无工具调用 → 最终答复
        yield AgentStep(
            kind=THOUGHT_ANSWER,
            content=result.content,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            elapsed_ms=elapsed,
        )
        return

    # 迭代用尽仍未收敛:兜底答复
    yield AgentStep(
        kind=THOUGHT_ANSWER,
        content=last_text or "(已达到最大推理步数,未能得到最终答复)",
    )


async def _run_tool(tc: ToolCall, tools: dict[str, RuntimeTool]) -> str:
    rt = tools.get(tc.name)
    if rt is None:
        return f"错误:未启用的工具 {tc.name}"
    try:
        return await rt.tool.execute(tc.arguments or {}, rt.ctx)
    except Exception as exc:  # noqa: BLE001 —— 工具失败作为观测回灌,让模型自行纠偏
        return f"工具执行出错:{exc}"
