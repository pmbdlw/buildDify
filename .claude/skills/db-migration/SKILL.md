---
name: db-migration
description: 生成 Alembic 数据库迁移,强制套用本项目的命名规范(单数表名+模块前缀、id/created_at/updated_at/deleted_at、pk_/uk_/fk_/idx_ 约束命名)。当需要新增/修改表、字段、索引时使用。
---

为本项目生成符合命名规范的 Alembic 迁移。

## 流程

1. 先确认要做的变更(新表 / 加字段 / 加索引 / 改约束),以及涉及的模块前缀。
2. 若是新表或改 ORM:先在 `backend/app/models/` 写/改 SQLAlchemy 模型。
3. 生成迁移骨架:`cd backend && uv run alembic revision --autogenerate -m "<简短描述>"`。
4. **逐行审查生成的迁移文件**,按下面的规范修正自动生成内容(autogenerate 不会自动遵守命名约定)。
5. 应用:`uv run alembic upgrade head`,并确认 `downgrade` 可回滚。

## 命名规范(必须满足)

- 表名:snake_case、**单数**、带模块前缀。例:`app_conversation`、`kb_document`、`wf_node_run`。
- 每张表必含:
  - `id`(主键)
  - `created_at`、`updated_at`(UTC,timestamptz,默认 now())
  - 需要软删除时加 `deleted_at`(UTC,可空)
- 字段:外键 `{目标表}_id`;布尔 `is_`/`has_` 前缀;排序 `sort_order`;状态 `status`。
- 约束/索引显式命名:
  - 主键 `pk_{table}`
  - 唯一 `uk_{table}_{col}`
  - 外键 `fk_{table}_{col}`(统一命名,但**不强制创建物理外键约束**)
  - 普通索引 `idx_{table}_{col}`
- 向量列用 pgvector 的 `vector(N)` 类型;检索字段建 `idx_{table}_{col}` 或对应向量索引。

## 检查清单

- [ ] 表名单数 + 模块前缀
- [ ] id / created_at / updated_at 齐全
- [ ] 所有约束/索引按 pk_/uk_/fk_/idx_ 命名
- [ ] 时间字段为 UTC(timestamptz)
- [ ] downgrade 能完整回滚
