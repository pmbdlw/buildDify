"""ORM 基类与公共字段 mixin。

遵循命名规范:每张表含 id / created_at / updated_at(UTC),软删除 deleted_at。
表名由各模型显式指定(单数 + 模块前缀,如 app_conversation)。
"""

from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 约束/索引命名约定 —— 让 Alembic 自动生成 pk_/uk_/fk_/idx_ 名,符合项目规范。
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "uq": "uk_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "ix": "idx_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """created_at / updated_at(UTC)。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SoftDeleteMixin:
    """deleted_at(UTC,可空)—— 逻辑删除标记。"""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
