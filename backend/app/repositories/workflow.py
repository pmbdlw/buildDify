"""工作流 / 运行 / 节点运行数据访问。"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow, WorkflowNodeRun, WorkflowRun


class WorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        name: str,
        description: str | None,
        graph: dict,
        app_id: uuid.UUID | None = None,
    ) -> Workflow:
        wf = Workflow(
            user_id=user_id, name=name, description=description, graph=graph, app_id=app_id
        )
        self.session.add(wf)
        await self.session.flush()
        await self.session.refresh(wf)
        return wf

    async def get(self, workflow_id: uuid.UUID, user_id: uuid.UUID) -> Workflow | None:
        result = await self.session.execute(
            select(Workflow).where(
                Workflow.id == workflow_id,
                Workflow.user_id == user_id,
                Workflow.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[Workflow]:
        result = await self.session.execute(
            select(Workflow)
            .where(Workflow.user_id == user_id, Workflow.deleted_at.is_(None))
            .order_by(Workflow.updated_at.desc())
        )
        return list(result.scalars().all())

    async def soft_delete(self, wf: Workflow) -> None:
        wf.deleted_at = func.now()
        await self.session.flush()


class WorkflowRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, *, workflow_id: uuid.UUID, user_id: uuid.UUID, inputs: dict
    ) -> WorkflowRun:
        run = WorkflowRun(workflow_id=workflow_id, user_id=user_id, inputs=inputs)
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def get(self, run_id: uuid.UUID, user_id: uuid.UUID) -> WorkflowRun | None:
        result = await self.session.execute(
            select(WorkflowRun).where(
                WorkflowRun.id == run_id, WorkflowRun.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_workflow(
        self, workflow_id: uuid.UUID, *, limit: int = 50
    ) -> list[WorkflowRun]:
        result = await self.session.execute(
            select(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def finish(
        self,
        run: WorkflowRun,
        *,
        status: str,
        outputs: dict | None,
        error: str | None,
        elapsed_ms: int,
        started_at: Any,
        finished_at: Any,
    ) -> None:
        run.status = status
        run.outputs = outputs
        run.error = error
        run.elapsed_ms = elapsed_ms
        run.started_at = started_at
        run.finished_at = finished_at
        await self.session.flush()


class WorkflowNodeRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        run_id: uuid.UUID,
        node_id: str,
        node_type: str,
        status: str,
        inputs: dict | None,
        outputs: dict | None,
        error: str | None,
        elapsed_ms: int,
        sort_order: int,
    ) -> WorkflowNodeRun:
        nr = WorkflowNodeRun(
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            status=status,
            inputs=inputs,
            outputs=outputs,
            error=error,
            elapsed_ms=elapsed_ms,
            sort_order=sort_order,
        )
        self.session.add(nr)
        await self.session.flush()
        return nr

    async def list_for_run(self, run_id: uuid.UUID) -> list[WorkflowNodeRun]:
        result = await self.session.execute(
            select(WorkflowNodeRun)
            .where(WorkflowNodeRun.run_id == run_id)
            .order_by(WorkflowNodeRun.sort_order.asc())
        )
        return list(result.scalars().all())
