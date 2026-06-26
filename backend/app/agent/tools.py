"""Agent 内置工具:知识库检索 / HTTP 请求 / 代码执行。

每个内置工具声明:
- type:工具键(同时作为 function calling 的函数名,Agent 内每种类型至多启用一个)。
- default_name / default_description:展示与提示给模型的说明。
- parameters:JSON Schema(模型据此产出调用入参)。
- execute(args, ctx):实际执行,返回字符串「观测结果」回灌给模型。

工具是 LLM 决策的"手";执行受限(代码用受限 builtins、HTTP 仅 http/https),
config 来自 agent_tool 行(如 dataset_id / top_k / 允许的 url 前缀)。
"""

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import ToolSpec

# 工具类型键(与 models.agent 保持一致)
TOOL_KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
TOOL_HTTP_REQUEST = "http_request"
TOOL_CODE_EXEC = "code_exec"


class AgentToolError(Exception):
    """工具执行错误(配置缺失 / 调用失败)。"""


@dataclass
class ToolContext:
    """工具执行上下文:DB 会话 + 该工具的固定配置(来自 agent_tool.config)。"""

    session: AsyncSession | None
    config: dict[str, Any] = field(default_factory=dict)


# ---- 知识库检索 ----
async def _exec_knowledge_retrieval(args: dict, ctx: ToolContext) -> str:
    from app.services.retrieval import RetrievalService

    query = (args.get("query") or "").strip()
    if not query:
        raise AgentToolError("检索工具缺少 query")
    dataset_id_raw = ctx.config.get("dataset_id")
    if not dataset_id_raw:
        raise AgentToolError("检索工具未绑定知识库(dataset_id)")
    if ctx.session is None:
        raise AgentToolError("检索工具需要数据库会话")
    try:
        dataset_id = uuid.UUID(str(dataset_id_raw))
    except ValueError as exc:
        raise AgentToolError(f"非法 dataset_id: {dataset_id_raw}") from exc
    top_k = ctx.config.get("top_k")
    citations = await RetrievalService(ctx.session).retrieve(
        dataset_id=dataset_id, query=query, top_k=int(top_k) if top_k else None
    )
    if not citations:
        return "未检索到相关资料。"
    return "\n\n".join(f"[{c.index}] {c.content}" for c in citations)


# ---- HTTP 请求 ----
async def _exec_http_request(args: dict, ctx: ToolContext) -> str:
    url = (args.get("url") or "").strip()
    if not url:
        raise AgentToolError("HTTP 工具缺少 url")
    if not url.startswith(("http://", "https://")):
        raise AgentToolError("仅允许 http/https 请求")
    allow_prefix = ctx.config.get("allow_url_prefix")
    if allow_prefix and not url.startswith(allow_prefix):
        raise AgentToolError(f"url 不在允许的前缀 {allow_prefix} 内")
    method = (args.get("method") or "GET").upper()
    if method not in ("GET", "POST"):
        raise AgentToolError("仅支持 GET / POST")
    body = args.get("body")
    timeout = float(ctx.config.get("timeout") or 15)
    max_chars = int(ctx.config.get("max_chars") or 4000)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method == "GET":
                resp = await client.get(url)
            else:
                if isinstance(body, (dict, list)):
                    resp = await client.post(url, json=body)
                else:
                    resp = await client.post(url, content=(body or ""))
    except httpx.HTTPError as exc:
        raise AgentToolError(f"HTTP 请求失败: {exc}") from exc
    text = resp.text or ""
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n…(已截断,共 {len(resp.text)} 字符)"
    return f"HTTP {resp.status_code}\n{text}"


# ---- 代码执行(受限 builtins)----
_SAFE_BUILTINS = {
    "len": len, "range": range, "min": min, "max": max, "sum": sum, "abs": abs,
    "round": round, "sorted": sorted, "str": str, "int": int, "float": float,
    "bool": bool, "list": list, "dict": dict, "set": set, "tuple": tuple,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter, "any": any,
    "all": all, "reversed": reversed, "json": json, "print": print,
}


async def _exec_code(args: dict, ctx: ToolContext) -> str:
    code = args.get("code") or ""
    if not code.strip():
        raise AgentToolError("代码工具缺少 code")
    ns: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS, "result": None}
    try:
        exec(code, ns)  # noqa: S102 —— 受限 builtins,MVP 本地工具
    except Exception as exc:  # noqa: BLE001
        raise AgentToolError(f"代码执行失败: {exc}") from exc
    result = ns.get("result")
    if result is None:
        return "(代码已执行,但未设置 result 变量)"
    try:
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(result)


@dataclass
class BuiltinTool:
    type: str
    default_name: str
    default_description: str
    parameters: dict
    executor: Any  # async (args, ctx) -> str

    def to_spec(self, description: str | None = None) -> ToolSpec:
        return ToolSpec(
            name=self.type,
            description=description or self.default_description,
            parameters=self.parameters,
        )

    async def execute(self, args: dict, ctx: ToolContext) -> str:
        return await self.executor(args, ctx)


BUILTIN_TOOLS: dict[str, BuiltinTool] = {
    TOOL_KNOWLEDGE_RETRIEVAL: BuiltinTool(
        type=TOOL_KNOWLEDGE_RETRIEVAL,
        default_name="知识库检索",
        default_description="在已绑定的知识库中检索与问题相关的资料片段,返回带编号的内容,可用于据实回答并标注引用。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或问题"}
            },
            "required": ["query"],
        },
        executor=_exec_knowledge_retrieval,
    ),
    TOOL_HTTP_REQUEST: BuiltinTool(
        type=TOOL_HTTP_REQUEST,
        default_name="HTTP 请求",
        default_description="发起一次 HTTP(GET/POST)请求并返回响应文本,用于获取实时网页/接口数据。",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "请求地址(http/https)"},
                "method": {"type": "string", "enum": ["GET", "POST"], "description": "请求方法,默认 GET"},
                "body": {"description": "POST 请求体(对象将以 JSON 发送)"},
            },
            "required": ["url"],
        },
        executor=_exec_http_request,
    ),
    TOOL_CODE_EXEC: BuiltinTool(
        type=TOOL_CODE_EXEC,
        default_name="代码执行",
        default_description="执行一段 Python 代码做计算/数据处理,把最终结果赋给变量 result,将返回 result 的内容。",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 代码,需把结果赋给 result 变量"}
            },
            "required": ["code"],
        },
        executor=_exec_code,
    ),
}


def get_builtin_tool(tool_type: str) -> BuiltinTool:
    tool = BUILTIN_TOOLS.get(tool_type)
    if tool is None:
        raise AgentToolError(f"未知内置工具类型: {tool_type}")
    return tool
