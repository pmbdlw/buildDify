"""Agent 相关 Pydantic schema。"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentToolIn(BaseModel):
    type: str = Field(description="内置工具类型:knowledge_retrieval / http_request / code_exec")
    name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class AgentToolUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    is_enabled: bool | None = None
    config: dict[str, Any] | None = None


class AgentToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    app_id: uuid.UUID
    type: str
    name: str
    description: str | None
    is_enabled: bool
    config: dict[str, Any]
    sort_order: int
    created_at: datetime


class BuiltinToolOut(BaseModel):
    """可选内置工具目录项(供前端展示与添加)。"""

    type: str
    name: str
    description: str
    parameters: dict[str, Any]


class AgentChatIn(BaseModel):
    content: str = Field(min_length=1)
    conversation_id: uuid.UUID | None = None


class AgentThoughtOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID | None
    kind: str
    content: str | None
    tool_name: str | None
    tool_input: dict[str, Any] | None
    tool_output: str | None
    input_tokens: int
    output_tokens: int
    elapsed_ms: int | None
    sort_order: int
