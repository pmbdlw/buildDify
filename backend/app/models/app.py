"""应用构建器模型:app_app / app_app_config(版本化)/ auth_api_key。

把"对话"产品化为可配置、可发布的应用:
- app_app:应用本体,published_config_id 指向当前已发布的配置版本。
- app_app_config:配置版本快照,每次保存自增 version;调试用最新版,对外用已发布版。
- auth_api_key:应用对外调用凭证,仅存哈希,明文只在创建时返回一次。

外键(user_id / app_id / published_config_id / dataset_id)按规范统一命名但不建物理约束,仅加索引。
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

# 应用类型(MVP 仅 chatbot;后续 workflow / agent)
APP_MODE_CHATBOT = "chatbot"

# 应用状态
APP_DRAFT = "draft"
APP_PUBLISHED = "published"


class App(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "app_app"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, server_default=APP_MODE_CHATBOT)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=APP_DRAFT)
    # 已发布的配置版本 id;为空表示尚未发布(仅可调试)
    published_config_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class AppConfig(Base, TimestampMixin):
    __tablename__ = "app_app_config"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1024")
    # 绑定的知识库(为空表示不启用 RAG)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class ApiKey(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "auth_api_key"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    # 展示用前缀(如 bd-AbC12…)与全量哈希;明文不落库
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
