"""工作流执行引擎:拓扑排序 + 变量池 + 条件分支 + 节点执行记录。

执行模型:
1. 解析 graph(nodes / edges),Kahn 拓扑排序(检测环)。
2. start 节点预置运行入参为其输出;从 start 出发按激活集推进。
3. 普通节点执行后激活全部出边的目标;condition 节点只激活命中 handle 的出边。
4. 未被激活的节点记为 skipped(分支未命中)。
5. end 节点的输出汇总为整个运行的最终产物。

引擎只读 DB(检索节点),不写库;节点执行记录作为结构化结果返回,由 service 落库。
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from app.models.workflow import (
    NODE_FAILED,
    NODE_SKIPPED,
    NODE_SUCCEEDED,
)
from app.workflow.context import VAR_RE, ExecutionContext
from app.workflow.nodes import get_handler


class WorkflowError(Exception):
    """图结构非法 / 执行失败。"""


@dataclass
class NodeRunRecord:
    node_id: str
    node_type: str
    status: str
    inputs: dict[str, Any] | None
    outputs: dict[str, Any] | None
    error: str | None
    elapsed_ms: int
    sort_order: int


@dataclass
class RunResult:
    status: str  # succeeded | failed
    outputs: dict[str, Any]
    error: str | None
    node_runs: list[NodeRunRecord] = field(default_factory=list)


def _topo_sort(node_ids: list[str], edges: list[dict]) -> list[str]:
    """Kahn 拓扑排序;存在环则抛错。"""
    indeg: dict[str, int] = {nid: 0 for nid in node_ids}
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in indeg and t in indeg:
            adj[s].append(t)
            indeg[t] += 1
    queue = deque(sorted(nid for nid in node_ids if indeg[nid] == 0))
    order: list[str] = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for nxt in adj[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(node_ids):
        raise WorkflowError("工作流存在环,无法拓扑排序")
    return order


def _resolve_inputs_snapshot(data: dict, ctx: ExecutionContext) -> dict[str, Any]:
    """把节点配置里含变量引用的字段解析为实际值,作为「输入」快照存档。"""
    snapshot: dict[str, Any] = {}
    for key, value in (data or {}).items():
        if isinstance(value, str) and VAR_RE.search(value):
            snapshot[key] = ctx.pool.resolve_text(value)
    return snapshot


def find_start_node(nodes: list[dict]) -> dict | None:
    for n in nodes:
        if n.get("type") == "start":
            return n
    return None


async def execute_workflow(
    graph: dict, inputs: dict[str, Any], session: Any
) -> RunResult:
    """执行一张工作流图,返回最终产物与各节点执行记录。"""
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        raise WorkflowError("工作流为空")
    nodes_by_id = {n["id"]: n for n in nodes}
    if len(nodes_by_id) != len(nodes):
        raise WorkflowError("存在重复的节点 id")

    start = find_start_node(nodes)
    if start is None:
        raise WorkflowError("缺少 start 节点")

    out_edges: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        if e.get("source") in nodes_by_id:
            out_edges[e["source"]].append(e)

    ctx = ExecutionContext(session)
    # start 输出 = 运行入参(仅保留 start 声明的变量;未声明则透传全部)
    declared = [v.get("name") for v in (start.get("data") or {}).get("variables") or []]
    start_outputs = (
        {name: inputs.get(name) for name in declared if name}
        if declared
        else dict(inputs)
    )
    ctx.pool.set_output(start["id"], start_outputs)

    order = _topo_sort(list(nodes_by_id.keys()), edges)
    active: set[str] = {start["id"]}

    records: list[NodeRunRecord] = []
    final_outputs: dict[str, Any] = {}

    for sort_order, node_id in enumerate(order):
        node = nodes_by_id[node_id]
        node_type = node.get("type", "")
        if node_id not in active:
            records.append(
                NodeRunRecord(
                    node_id=node_id, node_type=node_type, status=NODE_SKIPPED,
                    inputs=None, outputs=None, error=None, elapsed_ms=0,
                    sort_order=sort_order,
                )
            )
            continue

        inputs_snapshot = _resolve_inputs_snapshot(node.get("data") or {}, ctx)
        started = time.perf_counter()
        try:
            handler = get_handler(node_type)
            result = await handler(node, ctx)
        except Exception as exc:  # noqa: BLE001 —— 任何节点异常都记为该节点失败并中止运行
            elapsed = int((time.perf_counter() - started) * 1000)
            records.append(
                NodeRunRecord(
                    node_id=node_id, node_type=node_type, status=NODE_FAILED,
                    inputs=inputs_snapshot, outputs=None, error=str(exc),
                    elapsed_ms=elapsed, sort_order=sort_order,
                )
            )
            return RunResult(
                status="failed",
                outputs=final_outputs,
                error=f"节点 {node_id} 执行失败: {exc}",
                node_runs=records,
            )

        elapsed = int((time.perf_counter() - started) * 1000)
        ctx.pool.set_output(node_id, result.outputs)
        records.append(
            NodeRunRecord(
                node_id=node_id, node_type=node_type, status=NODE_SUCCEEDED,
                inputs=inputs_snapshot, outputs=result.outputs, error=None,
                elapsed_ms=elapsed, sort_order=sort_order,
            )
        )
        if node_type == "end":
            final_outputs.update(result.outputs)

        # 激活下游:condition 仅走命中 handle 的出边,其余走全部出边
        for e in out_edges.get(node_id, []):
            if result.branch is not None:
                handle = e.get("sourceHandle") or e.get("source_handle")
                if handle is not None and handle != result.branch:
                    continue
            active.add(e["target"])

    return RunResult(
        status="succeeded", outputs=final_outputs, error=None, node_runs=records
    )
