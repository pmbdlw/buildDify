"""知识库 RAG 模型:kb_dataset / kb_document / kb_segment。

外键(user_id / dataset_id / document_id)按规范统一命名但不建物理约束,仅加索引。
kb_segment.embedding 为 pgvector 向量列,维度对齐 settings.embedding_dim(讯飞 768)。
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.models.base import Base, SoftDeleteMixin, TimestampMixin

# 文档处理状态机
DOC_PENDING = "pending"
DOC_PROCESSING = "processing"
DOC_READY = "ready"
DOC_ERROR = "error"


class Dataset(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "kb_dataset"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)


class Document(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "kb_document"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pdf | md | txt
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=DOC_PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # 解析后的全文
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class Segment(Base, TimestampMixin):
    __tablename__ = "kb_segment"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim), nullable=False)
