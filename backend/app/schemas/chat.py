"""对话相关 Pydantic schema。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatIn(BaseModel):
    content: str = Field(min_length=1)
    conversation_id: uuid.UUID | None = None
    model: str | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    model: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    model: str | None
    input_tokens: int
    output_tokens: int
    created_at: datetime
