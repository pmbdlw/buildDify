---
name: scaffold-slice
description: 按本项目四层架构脚手架一个功能纵切片(ORM model + repository + service + FastAPI 路由 + Pydantic schema + 前端 API 调用),保证分层与命名一致。当新增一个功能/资源/端点时使用。
---

为一个新功能生成贯穿前后端的纵切片,严格遵循 `api → services → repositories → models` 单向分层。

## 输入

向我确认:资源名(如 `conversation`)、所属模块前缀(如 `app_`)、需要的字段、需要哪些端点(list/get/create/update/delete 或自定义)。

## 后端产物(backend/app/)

按依赖顺序生成,**每层只依赖下一层**:

1. `models/<resource>.py` — SQLAlchemy 模型,遵循 DB 命名规范(单数表名+前缀、id/created_at/updated_at、必要时 deleted_at)。新表需配合 `/db-migration` 出迁移。
2. `schemas/<resource>.py` — Pydantic 输入/输出 schema(Create / Update / Read 分开)。
3. `repositories/<resource>.py` — 数据访问,封装 SQLAlchemy 查询;service 只通过它访问 DB。
4. `services/<resource>.py` — 业务逻辑;不写裸 SQL,不直接 import 厂商 LLM SDK(走 `app/llm`)。
5. `api/<resource>.py` — FastAPI 路由,薄;只解析校验 + 依赖注入 + 调 service;在 `app/api` 注册 router。

## 前端产物(web/)

6. 对应的 API 调用封装(fetch/SWR)+ TypeScript 类型,字段与后端 schema 对齐。

## 约束

- 流式端点用 SSE。
- 时间字段 UTC。
- 生成后跑 `uv run pytest` 与 `pnpm build` 自检(若已有测试)。
- 不要跨层调用(路由层不得直接碰 repository/model)。
