"""工作流相关 Pydantic schema。

graph 为自由 JSON(React Flow 的 nodes/edges),不在 schema 里强约束结构,
由执行引擎在运行时校验,保持画布演进灵活。
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    graph: dict[str, Any] | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    graph: dict[str, Any] | None = None


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    version: int
    app_id: uuid.UUID | None
    graph: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WorkflowListItem(BaseModel):
    """列表项不带 graph,减小载荷。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class WorkflowRunIn(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class NodeRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    node_id: str
    node_type: str
    status: str
    inputs: dict[str, Any] | None
    outputs: dict[str, Any] | None
    error: str | None
    elapsed_ms: int | None
    sort_order: int


class WorkflowRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    status: str
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None
    error: str | None
    elapsed_ms: int | None
    created_at: datetime


class WorkflowRunDetail(WorkflowRunOut):
    """运行详情:含各节点执行记录(运行回放)。"""

    node_runs: list[NodeRunOut] = Field(default_factory=list)
