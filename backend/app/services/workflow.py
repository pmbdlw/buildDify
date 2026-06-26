"""工作流业务逻辑:工作流 CRUD(版本化)+ 运行编排(执行引擎 → 落库运行记录)。

运行同步执行(MVP):建运行记录 → 调引擎 → 落各节点执行记录 → 回填运行状态/产物。
长流程可后续改为 Celery 异步;接口契约不变。
"""

import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import RUN_FAILED, RUN_SUCCEEDED, Workflow, WorkflowRun
from app.repositories.workflow import (
    WorkflowNodeRunRepository,
    WorkflowRepository,
    WorkflowRunRepository,
)
from app.workflow import WorkflowError, execute_workflow


class WorkflowServiceError(Exception):
    """工作流业务错误(未找到 / 图非法)。"""


class WorkflowService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workflows = WorkflowRepository(session)
        self.runs = WorkflowRunRepository(session)
        self.node_runs = WorkflowNodeRunRepository(session)

    # ---- CRUD ----
    async def create(
        self, *, user_id: uuid.UUID, name: str, description: str | None, graph: dict | None
    ) -> Workflow:
        wf = await self.workflows.create(
            user_id=user_id, name=name, description=description, graph=graph or _blank_graph()
        )
        await self.session.commit()
        await self.session.refresh(wf)
        return wf

    async def list_workflows(self, user_id: uuid.UUID) -> list[Workflow]:
        return await self.workflows.list_for_user(user_id)

    async def get(self, workflow_id: uuid.UUID, user_id: uuid.UUID) -> Workflow:
        wf = await self.workflows.get(workflow_id, user_id)
        if wf is None:
            raise WorkflowServiceError("工作流不存在")
        return wf

    async def update(
        self,
        *,
        workflow_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None,
        description: str | None,
        graph: dict | None,
    ) -> Workflow:
        wf = await self.get(workflow_id, user_id)
        if name is not None:
            wf.name = name
        if description is not None:
            wf.description = description
        if graph is not None:
            wf.graph = graph
            wf.version += 1  # 每次保存画布自增版本
        await self.session.commit()
        await self.session.refresh(wf)
        return wf

    async def delete(self, *, workflow_id: uuid.UUID, user_id: uuid.UUID) -> None:
        wf = await self.get(workflow_id, user_id)
        await self.workflows.soft_delete(wf)
        await self.session.commit()

    # ---- 运行 ----
    async def run(
        self, *, workflow_id: uuid.UUID, user_id: uuid.UUID, inputs: dict
    ) -> WorkflowRun:
        wf = await self.get(workflow_id, user_id)
        run = await self.runs.create(workflow_id=wf.id, user_id=user_id, inputs=inputs)
        await self.session.commit()

        started_at = datetime.now(UTC)
        t0 = time.perf_counter()
        try:
            result = await execute_workflow(wf.graph, inputs, self.session)
        except WorkflowError as exc:
            elapsed = int((time.perf_counter() - t0) * 1000)
            await self.runs.finish(
                run, status=RUN_FAILED, outputs=None, error=str(exc),
                elapsed_ms=elapsed, started_at=started_at,
                finished_at=datetime.now(UTC),
            )
            await self.session.commit()
            await self.session.refresh(run)
            return run

        elapsed = int((time.perf_counter() - t0) * 1000)
        for rec in result.node_runs:
            await self.node_runs.add(
                run_id=run.id,
                node_id=rec.node_id,
                node_type=rec.node_type,
                status=rec.status,
                inputs=rec.inputs,
                outputs=rec.outputs,
                error=rec.error,
                elapsed_ms=rec.elapsed_ms,
                sort_order=rec.sort_order,
            )
        await self.runs.finish(
            run,
            status=RUN_SUCCEEDED if result.status == "succeeded" else RUN_FAILED,
            outputs=result.outputs,
            error=result.error,
            elapsed_ms=elapsed,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_run(self, *, run_id: uuid.UUID, user_id: uuid.UUID) -> WorkflowRun:
        run = await self.runs.get(run_id, user_id)
        if run is None:
            raise WorkflowServiceError("运行记录不存在")
        return run

    async def list_runs(
        self, *, workflow_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[WorkflowRun]:
        await self.get(workflow_id, user_id)  # 鉴权 + 存在性
        return await self.runs.list_for_workflow(workflow_id)

    async def list_node_runs(self, run_id: uuid.UUID):
        return await self.node_runs.list_for_run(run_id)


def _blank_graph() -> dict:
    """新建工作流的默认画布:一个 start + 一个 end。"""
    return {
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 80, "y": 160},
                "data": {"label": "开始", "variables": [{"name": "query", "type": "string"}]},
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 560, "y": 160},
                "data": {"label": "结束", "outputs": [{"name": "result", "value": "{{ start.query }}"}]},
            },
        ],
        "edges": [{"id": "e-start-end", "source": "start", "target": "end"}],
    }
