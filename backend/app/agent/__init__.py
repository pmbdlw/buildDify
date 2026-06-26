"""Agent 引擎:内置工具注册表 + ReAct(function calling)循环。

对外暴露:
- BUILTIN_TOOLS / get_builtin_tool:内置工具注册表。
- run_react:驱动一轮 ReAct,异步产出轨迹步骤(thought/tool_call/observation/answer)。
"""

from app.agent.react import AgentStep, run_react
from app.agent.tools import BUILTIN_TOOLS, AgentToolError, ToolContext, get_builtin_tool

__all__ = [
    "BUILTIN_TOOLS",
    "AgentStep",
    "AgentToolError",
    "ToolContext",
    "get_builtin_tool",
    "run_react",
]
