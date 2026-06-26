# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目目标

定制化 LLM 应用开发平台,对标 **Dify** 的能力模型,但**不使用 Dify 源码**、从零构建。一周内配合 AI 编程工具产出可运行 MVP,覆盖四大能力:对话应用(Chatbot)、知识库 RAG、可视化工作流、Agent + 工具调用。

## 技术栈

- 后端:Python 3.12 + FastAPI + SQLAlchemy 2.0(async)+ Alembic + Celery + Redis
- 数据库:PostgreSQL 16 + **pgvector**(向量检索,不另起独立向量库)
- 前端:Next.js 15(App Router)+ TypeScript + Tailwind + React Flow(工作流编辑器)+ AG Grid 社区版
- LLM:首选 Claude(`claude-opus-4-8` / `claude-sonnet-4-6`),用官方 Anthropic SDK;所有调用经 `app/llm` provider 抽象层,**不在业务代码里硬编码某厂商 SDK**
- 基础设施:docker compose(**不写 `version` 头**),服务:`api` / `worker` / `web` / `db` / `redis`
- 包管理:后端 `uv`,前端 `pnpm`

## 目录结构(Monorepo)

```
backend/
  app/api/           路由层(HTTP,薄;只解析校验 + 调 service)
  app/services/      业务逻辑层
  app/repositories/  数据访问层(SQLAlchemy,不在别处写 SQL)
  app/models/        ORM 模型
  app/schemas/       Pydantic 输入/输出
  app/core/          配置、鉴权、依赖注入
  app/llm/           模型 provider 抽象 + Claude 实现
  app/workflow/      工作流节点执行引擎
  alembic/           数据库迁移
web/                 Next.js 前端
docker-compose.yml
```

## 后端架构分层

请求严格单向流动:**api → services → repositories → models**。
- 路由层只做 HTTP 解析/校验(Pydantic schema)与调用 service,不写业务逻辑。
- service 不直接写 SQL,一律经 repository。
- LLM 调用走 `app/llm` provider 抽象,不在 service 里直接 import 某厂商 SDK。
- 新增功能用 `/scaffold-slice` 生成纵切片,保持分层一致。

## 数据库命名规范(强制)

- snake_case;表名**单数** + **模块前缀**(如 `app_conversation`、`kb_document`、`wf_node`)。
- 每张表必须有 `id`、`created_at`、`updated_at`(UTC);逻辑删除用 `deleted_at`(UTC)。
- 外键 `{目标表}_id`;布尔 `is_`/`has_` 前缀;排序 `sort_order`;状态 `status`。
- 约束命名:主键 `pk_{table}`、唯一 `uk_{table}_{col}`、外键 `fk_{table}_{col}`、索引 `idx_{table}_{col}`。
- 外键统一命名但**不强制物理约束**。
- 生成迁移用 `/db-migration` 技能,不手写 raw SQL 迁移。

## 常用命令

```
docker compose up -d              启动全部服务
docker compose up -d db redis     只起依赖,后端/前端本地跑
# 后端(在 backend/ 下)
uv run uvicorn app.main:app --reload
uv run pytest                     全部测试
uv run pytest -k "test_name"      单个测试
uv run alembic upgrade head       应用迁移
# 前端(在 web/ 下)
pnpm dev / pnpm test / pnpm build
```

## 约定

- 时间一律 UTC。
- 构建 AI 功能默认用最新 Claude 模型(见上方 model id)。
- AG Grid 只用社区版功能;企业版功能自行封装二次开发。
- 流式响应用 SSE;长任务(文档分块/embedding)走 Celery worker。
