"""工作流路由:工作流 CRUD、运行、运行记录回放。

api 层只做 HTTP 解析/校验与调 service;执行编排在 WorkflowService。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.workflow import (
    NodeRunOut,
    WorkflowCreate,
    WorkflowListItem,
    WorkflowOut,
    WorkflowRunDetail,
    WorkflowRunIn,
    WorkflowRunOut,
    WorkflowUpdate,
)
from app.services.workflow import WorkflowService, WorkflowServiceError

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _svc(session: AsyncSession) -> WorkflowService:
    return WorkflowService(session)


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    data: WorkflowCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _svc(session).create(
        user_id=current_user.id, name=data.name, description=data.description, graph=data.graph
    )


@router.get("", response_model=list[WorkflowListItem])
async def list_workflows(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _svc(session).list_workflows(current_user.id)


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await _svc(session).get(workflow_id, current_user.id)
    except WorkflowServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/{workflow_id}", response_model=WorkflowOut)
async def update_workflow(
    workflow_id: uuid.UUID,
    data: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await _svc(session).update(
            workflow_id=workflow_id,
            user_id=current_user.id,
            name=data.name,
            description=data.description,
            graph=data.graph,
        )
    except WorkflowServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        await _svc(session).delete(workflow_id=workflow_id, user_id=current_user.id)
    except WorkflowServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---- 运行 ----
@router.post("/{workflow_id}/run", response_model=WorkflowRunDetail)
async def run_workflow(
    workflow_id: uuid.UUID,
    data: WorkflowRunIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = _svc(session)
    try:
        run = await svc.run(workflow_id=workflow_id, user_id=current_user.id, inputs=data.inputs)
    except WorkflowServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    node_runs = await svc.list_node_runs(run.id)
    return _run_detail(run, node_runs)


@router.get("/{workflow_id}/runs", response_model=list[WorkflowRunOut])
async def list_runs(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await _svc(session).list_runs(workflow_id=workflow_id, user_id=current_user.id)
    except WorkflowServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{workflow_id}/runs/{run_id}", response_model=WorkflowRunDetail)
async def get_run(
    workflow_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = _svc(session)
    try:
        run = await svc.get_run(run_id=run_id, user_id=current_user.id)
    except WorkflowServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    node_runs = await svc.list_node_runs(run.id)
    return _run_detail(run, node_runs)


def _run_detail(run, node_runs) -> WorkflowRunDetail:
    detail = WorkflowRunDetail.model_validate(run)
    detail.node_runs = [NodeRunOut.model_validate(nr) for nr in node_runs]
    return detail
