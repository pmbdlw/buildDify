"""工作流节点实现与统一接口。

每种节点是一个 async 处理函数,签名统一为:
    async def handler(node: dict, ctx: ExecutionContext) -> NodeOutput

- node:画布节点 {"id", "type", "data": {...配置...}}
- 返回 NodeOutput:outputs(写入变量池的产物 dict)+ branch(条件节点选择的出边 handle)

节点类型:start / end / llm / knowledge_retrieval / condition / code / template。
风险控制:先打通线性流程,condition/code 为增量;code 用受限命名空间执行。
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.llm.base import ChatRequest
from app.llm.base import Message as LLMMessage
from app.llm.factory import resolve_provider
from app.workflow.context import ExecutionContext


class NodeError(Exception):
    """节点执行错误。"""


@dataclass
class NodeOutput:
    outputs: dict[str, Any] = field(default_factory=dict)
    # 条件节点产出的出边 handle(如 "true"/"false");None 表示走全部出边
    branch: str | None = None


Handler = Callable[[dict, ExecutionContext], Awaitable[NodeOutput]]


def _data(node: dict) -> dict:
    return node.get("data") or {}


# ---- start:把运行入参暴露为 start 节点的输出 ----
async def run_start(node: dict, ctx: ExecutionContext) -> NodeOutput:
    # start 输出已在引擎启动时预置(见 engine),这里直接回传变量池中的值
    return NodeOutput(outputs=ctx.pool.get_outputs(node["id"]))


# ---- end:收集声明的输出变量,作为整个运行的最终产物 ----
async def run_end(node: dict, ctx: ExecutionContext) -> NodeOutput:
    outputs: dict[str, Any] = {}
    for item in _data(node).get("outputs") or []:
        name = item.get("name")
        if not name:
            continue
        outputs[name] = ctx.pool.resolve_value(item.get("value"))
    return NodeOutput(outputs=outputs)


# ---- template:纯文本模板拼接,产出 text ----
async def run_template(node: dict, ctx: ExecutionContext) -> NodeOutput:
    text = ctx.pool.resolve_text(_data(node).get("template"))
    return NodeOutput(outputs={"text": text})


# ---- llm:模板化 prompt + system,调用 provider.chat,产出 text ----
async def run_llm(node: dict, ctx: ExecutionContext) -> NodeOutput:
    data = _data(node)
    prompt = ctx.pool.resolve_text(data.get("prompt"))
    system = ctx.pool.resolve_text(data.get("system_prompt")) or None
    model = data.get("model") or None
    temperature = data.get("temperature")
    max_tokens = int(data.get("max_tokens") or 1024)

    provider = resolve_provider(model)
    req = ChatRequest(
        messages=[LLMMessage(role="user", content=prompt)],
        model=model,
        system=system,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    result = await provider.chat(req)
    return NodeOutput(
        outputs={
            "text": result.content,
            "model": result.model,
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
        }
    )


# ---- knowledge_retrieval:模板化 query + dataset_id 检索,产出 text/chunks/citations ----
async def run_knowledge_retrieval(node: dict, ctx: ExecutionContext) -> NodeOutput:
    from app.services.retrieval import RetrievalService

    data = _data(node)
    query = ctx.pool.resolve_text(data.get("query"))
    dataset_id_raw = data.get("dataset_id")
    if not dataset_id_raw:
        raise NodeError("知识检索节点未配置 dataset_id")
    if not query.strip():
        raise NodeError("知识检索节点 query 为空")
    top_k = data.get("top_k")
    try:
        dataset_id = uuid.UUID(str(dataset_id_raw))
    except ValueError as exc:
        raise NodeError(f"非法 dataset_id: {dataset_id_raw}") from exc

    citations = await RetrievalService(ctx.session).retrieve(
        dataset_id=dataset_id, query=query, top_k=int(top_k) if top_k else None
    )
    text = "\n\n".join(f"[{c.index}] {c.content}" for c in citations)
    chunks = [
        {
            "index": c.index,
            "document_id": str(c.document_id),
            "content": c.content,
            "score": c.score,
        }
        for c in citations
    ]
    return NodeOutput(outputs={"text": text, "chunks": chunks, "count": len(chunks)})


# ---- condition:对变量做比较,命中走 "true" 出边,否则 "false" ----
def _as_number(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _eval_condition(left: Any, operator: str, right: Any) -> bool:
    ls = "" if left is None else str(left)
    rs = "" if right is None else str(right)
    if operator in ("eq", "=="):
        return ls == rs
    if operator in ("ne", "!="):
        return ls != rs
    if operator == "contains":
        return rs in ls
    if operator == "not_contains":
        return rs not in ls
    if operator == "empty":
        return ls == ""
    if operator == "not_empty":
        return ls != ""
    if operator in ("gt", "lt", "gte", "lte"):
        ln, rn = _as_number(left), _as_number(right)
        if ln is None or rn is None:
            return False
        return {
            "gt": ln > rn,
            "lt": ln < rn,
            "gte": ln >= rn,
            "lte": ln <= rn,
        }[operator]
    raise NodeError(f"未知条件运算符: {operator}")


async def run_condition(node: dict, ctx: ExecutionContext) -> NodeOutput:
    data = _data(node)
    logic = (data.get("logic") or "and").lower()
    conditions = data.get("conditions") or []
    results: list[bool] = []
    for cond in conditions:
        left = ctx.pool.resolve_value(cond.get("variable"))
        right = ctx.pool.resolve_value(cond.get("value")) if cond.get("value") is not None else None
        results.append(_eval_condition(left, cond.get("operator", "eq"), right))
    if not results:
        passed = True
    elif logic == "or":
        passed = any(results)
    else:
        passed = all(results)
    branch = "true" if passed else "false"
    return NodeOutput(outputs={"result": passed}, branch=branch)


# ---- code:受限命名空间执行 Python,读 inputs、写 outputs ----
_SAFE_BUILTINS = {
    "len": len, "range": range, "min": min, "max": max, "sum": sum, "abs": abs,
    "round": round, "sorted": sorted, "str": str, "int": int, "float": float,
    "bool": bool, "list": list, "dict": dict, "set": set, "tuple": tuple,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter, "any": any,
    "all": all, "reversed": reversed, "json": __import__("json"),
}


async def run_code(node: dict, ctx: ExecutionContext) -> NodeOutput:
    data = _data(node)
    code = data.get("code") or ""
    # 把声明的输入变量解析后注入 inputs(默认从模板引用取原始值)
    inputs: dict[str, Any] = {}
    for item in data.get("inputs") or []:
        name = item.get("name")
        if name:
            inputs[name] = ctx.pool.resolve_value(item.get("value"))
    ns: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "inputs": inputs,
        "outputs": {},
    }
    try:
        exec(code, ns)  # noqa: S102 —— MVP 本地工具,受限 builtins
    except Exception as exc:  # noqa: BLE001
        raise NodeError(f"代码执行失败: {exc}") from exc
    outputs = ns.get("outputs")
    if not isinstance(outputs, dict):
        raise NodeError("代码节点须把结果写入 outputs(dict)")
    return NodeOutput(outputs=outputs)


HANDLERS: dict[str, Handler] = {
    "start": run_start,
    "end": run_end,
    "llm": run_llm,
    "knowledge_retrieval": run_knowledge_retrieval,
    "condition": run_condition,
    "code": run_code,
    "template": run_template,
}


def get_handler(node_type: str) -> Handler:
    handler = HANDLERS.get(node_type)
    if handler is None:
        raise NodeError(f"未知节点类型: {node_type}")
    return handler
