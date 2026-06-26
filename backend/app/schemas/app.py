"""应用构建器相关 Pydantic schema。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.app import APP_MODE_CHATBOT


class AppCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    mode: str = APP_MODE_CHATBOT


class AppUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class AppOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    mode: str
    status: str
    published_config_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AppConfigIn(BaseModel):
    model: str | None = None
    system_prompt: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int = Field(default=1024, ge=1, le=32000)
    dataset_id: uuid.UUID | None = None


class AppConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    app_id: uuid.UUID
    version: int
    model: str | None
    system_prompt: str | None
    temperature: float | None
    max_tokens: int
    dataset_id: uuid.UUID | None
    created_at: datetime


class AppChatIn(BaseModel):
    content: str = Field(min_length=1)
    conversation_id: uuid.UUID | None = None


class ApiKeyCreate(BaseModel):
    name: str = Field(default="", max_length=100)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    """创建时一次性返回明文 key。"""

    key: str
