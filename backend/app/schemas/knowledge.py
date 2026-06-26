"""知识库相关 Pydantic schema。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    embedding_model: str
    created_at: datetime
    updated_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    name: str
    file_type: str
    status: str
    error: str | None
    char_count: int
    segment_count: int
    created_at: datetime
    updated_at: datetime


class RetrieveIn(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)


class CitationOut(BaseModel):
    index: int
    document_id: uuid.UUID
    content: str
    score: float
