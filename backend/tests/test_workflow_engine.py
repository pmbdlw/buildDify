"""工作流执行引擎单元测试 —— 不触网/不连库的节点(template/condition/code)。

knowledge_retrieval/llm 走外部依赖,在此用不依赖它们的图覆盖引擎核心:
变量池解析、拓扑排序、条件分支跳过、代码节点、环检测、缺 start 报错。
"""

import pytest
from app.workflow import WorkflowError, execute_workflow
from app.workflow.context import VariablePool


def test_variable_pool_resolution():
    pool = VariablePool()
    pool.set_output("start", {"query": "你好", "n": 3})
    assert pool.resolve_text("问题:{{ start.query }}") == "问题:你好"
    # 整段单引用取原始值(保留类型)
    assert pool.resolve_value("{{ start.n }}") == 3
    # 混合模板得到字符串
    assert pool.resolve_text("{{ start.query }}-{{ start.n }}") == "你好-3"
    # 未知引用解析为空串
    assert pool.resolve_text("{{ missing.x }}!") == "!"


async def test_linear_template_flow():
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": [{"name": "query"}]}},
            {
                "id": "tpl",
                "type": "template",
                "data": {"template": "回声:{{ start.query }}"},
            },
            {
                "id": "end",
                "type": "end",
                "data": {"outputs": [{"name": "answer", "value": "{{ tpl.text }}"}]},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "tpl"},
            {"id": "e2", "source": "tpl", "target": "end"},
        ],
    }
    result = await execute_workflow(graph, {"query": "世界"}, session=None)
    assert result.status == "succeeded"
    assert result.outputs == {"answer": "回声:世界"}
    # 三个节点均 succeeded,顺序记录
    assert [r.node_id for r in result.node_runs] == ["start", "tpl", "end"]
    assert all(r.status == "succeeded" for r in result.node_runs)


async def test_condition_branch_skips_untaken_path():
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": [{"name": "score"}]}},
            {
                "id": "cond",
                "type": "condition",
                "data": {
                    "conditions": [
                        {"variable": "{{ start.score }}", "operator": "gte", "value": "60"}
                    ]
                },
            },
            {"id": "pass", "type": "template", "data": {"template": "及格"}},
            {"id": "fail", "type": "template", "data": {"template": "不及格"}},
            {
                "id": "end",
                "type": "end",
                "data": {
                    "outputs": [
                        {"name": "p", "value": "{{ pass.text }}"},
                        {"name": "f", "value": "{{ fail.text }}"},
                    ]
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "cond"},
            {"id": "e2", "source": "cond", "target": "pass", "sourceHandle": "true"},
            {"id": "e3", "source": "cond", "target": "fail", "sourceHandle": "false"},
            {"id": "e4", "source": "pass", "target": "end"},
            {"id": "e5", "source": "fail", "target": "end"},
        ],
    }
    result = await execute_workflow(graph, {"score": 75}, session=None)
    assert result.status == "succeeded"
    statuses = {r.node_id: r.status for r in result.node_runs}
    assert statuses["pass"] == "succeeded"
    assert statuses["fail"] == "skipped"
    assert result.outputs["p"] == "及格"
    assert result.outputs["f"] is None  # fail 未执行,单引用解析为 None


async def test_code_node():
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": [{"name": "n"}]}},
            {
                "id": "code",
                "type": "code",
                "data": {
                    "inputs": [{"name": "n", "value": "{{ start.n }}"}],
                    "code": "outputs = {'double': inputs['n'] * 2}",
                },
            },
            {
                "id": "end",
                "type": "end",
                "data": {"outputs": [{"name": "r", "value": "{{ code.double }}"}]},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "code"},
            {"id": "e2", "source": "code", "target": "end"},
        ],
    }
    result = await execute_workflow(graph, {"n": 21}, session=None)
    assert result.status == "succeeded"
    assert result.outputs == {"r": 42}


async def test_cycle_detected():
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            {"id": "a", "type": "template", "data": {"template": "x"}},
            {"id": "b", "type": "template", "data": {"template": "y"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "a"},
            {"id": "e2", "source": "a", "target": "b"},
            {"id": "e3", "source": "b", "target": "a"},  # 环
        ],
    }
    with pytest.raises(WorkflowError):
        await execute_workflow(graph, {}, session=None)


async def test_missing_start_raises():
    graph = {"nodes": [{"id": "tpl", "type": "template", "data": {}}], "edges": []}
    with pytest.raises(WorkflowError):
        await execute_workflow(graph, {}, session=None)


async def test_node_failure_marks_run_failed():
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            # code 引用未定义变量 -> 抛错 -> 节点失败
            {"id": "code", "type": "code", "data": {"code": "outputs = boom"}},
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "code"},
            {"id": "e2", "source": "code", "target": "end"},
        ],
    }
    result = await execute_workflow(graph, {}, session=None)
    assert result.status == "failed"
    assert result.error is not None
    statuses = {r.node_id: r.status for r in result.node_runs}
    assert statuses["code"] == "failed"
    assert "end" not in statuses  # 失败即中止,end 未记录
