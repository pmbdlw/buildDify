# 架构设计文档 —— 定制化 LLM 应用平台

> 对标 Dify 能力模型,**不使用 Dify 源码**,从零构建。本文档描述系统的目标、技术栈、分层架构、核心数据模型与关键子系统设计。

## 1. 目标与范围

构建一个 LLM 应用开发平台,一周内产出可运行 MVP,覆盖四大能力:

| 能力 | 说明 |
|---|---|
| 对话应用(Chatbot) | 流式对话、Prompt 配置、会话/消息历史 |
| 知识库 RAG | 文档上传 → 分块 → embedding → pgvector 检索 → 引用注入 |
| 可视化工作流 | 节点编排引擎 + React Flow 编辑器(LLM / 检索 / 条件 / 代码 节点) |
| Agent + 工具调用 | Function calling、内置工具、ReAct 循环 |

**非目标(MVP 之外)**:多租户计费、企业 SSO、模型微调、插件市场。

## 2. 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · Alembic · Pydantic v2 |
| 异步任务 | Celery + Redis(文档分块、embedding、长任务) |
| 数据库 | PostgreSQL 16 + **pgvector**(关系数据与向量同库,少一个服务) |
| 缓存/队列 | Redis 7 |
| 前端 | Next.js 15 (App Router) · TypeScript · Tailwind · React Flow · AG Grid 社区版 |
| LLM | 首选 Claude(`claude-opus-4-8` / `claude-sonnet-4-6`),Anthropic SDK;经 provider 抽象 |
| 包管理 | 后端 `uv`,前端 `pnpm` |
| 部署 | docker compose(无 `version` 头):`api` / `worker` / `web` / `db` / `redis` |

## 3. 系统架构

```mermaid
flowchart LR
  subgraph Client
    Web[Next.js Web]
    SDK[已发布应用 API Key 调用方]
  end
  Web -->|REST / SSE| API
  SDK -->|REST / SSE| API
  subgraph Backend
    API[FastAPI api]
    API --> SVC[services 业务层]
    SVC --> REPO[repositories 数据层]
    SVC --> LLM[llm provider 抽象]
    SVC --> WF[workflow 引擎]
    API -. enqueue .-> Q[(Redis 队列)]
    Q --> Worker[Celery worker]
    Worker --> REPO
    Worker --> LLM
  end
  REPO --> PG[(PostgreSQL + pgvector)]
  LLM -->|HTTPS| Anthropic[(Anthropic API)]
```

## 4. 后端分层架构

请求严格单向流动:**api → services → repositories → models**。

```
backend/app/
  api/           # 路由层:HTTP 解析/校验(Pydantic),依赖注入,调 service。薄,无业务逻辑。
  services/      # 业务逻辑层:编排 repository / llm / workflow。
  repositories/  # 数据访问层:封装 SQLAlchemy 查询。唯一写 SQL 的地方。
  models/        # ORM 模型(SQLAlchemy)。
  schemas/       # Pydantic 输入/输出 DTO。
  core/          # 配置、鉴权、依赖、异常、日志。
  llm/           # 模型 provider 抽象 + Claude 实现。
  workflow/      # 工作流节点执行引擎。
  tasks/         # Celery 任务。
  main.py        # FastAPI 应用入口。
alembic/         # 数据库迁移。
```

**铁律**:路由层不得直接访问 repository/model;service 不写裸 SQL;LLM 调用一律走 `llm/` 抽象,不在业务里硬编码厂商 SDK。

## 5. 核心数据模型

遵循命名规范:snake_case、表名单数 + 模块前缀、每表含 `id`/`created_at`/`updated_at`(UTC)、软删除 `deleted_at`、约束 `pk_`/`uk_`/`fk_`/`idx_`。下为关键表(字段从略,仅示意结构):

| 模块 | 表 | 说明 |
|---|---|---|
| 鉴权 | `auth_user` | 用户 |
| | `auth_api_key` | 已发布应用的访问密钥 |
| 应用 | `app_app` | 应用(类型:chatbot / workflow / agent) |
| | `app_app_config` | 应用配置(prompt、模型、参数,版本化) |
| | `app_conversation` | 会话 |
| | `app_message` | 消息(role、content、token 统计、引用) |
| 知识库 | `kb_dataset` | 知识库 |
| | `kb_document` | 文档 |
| | `kb_segment` | 分块,含 `embedding vector(1536)` 列 + `idx_kb_segment_embedding` |
| 工作流 | `wf_workflow` | 工作流定义(graph JSON) |
| | `wf_node_run` | 节点执行记录(输入/输出/耗时/状态) |
| | `wf_run` | 工作流运行实例 |
| Agent | `agent_tool` | 工具定义(name、schema、handler 类型) |
| | `agent_thought` | ReAct 思考/动作/观察轨迹 |

> 所有迁移用 `/db-migration` 技能生成,确保命名规范不跑偏。

## 6. LLM Provider 抽象

`llm/` 定义统一接口,屏蔽厂商差异,便于后续接入更多模型:

```python
class LLMProvider(Protocol):
    async def chat(self, messages, *, model, tools=None, stream=False) -> ChatResult | AsyncIterator[Chunk]: ...
    async def embed(self, texts: list[str], *, model) -> list[list[float]]: ...
```

- 默认实现 `AnthropicProvider`(Claude),embedding 可用 Anthropic 或独立 embedding 服务。
- 上层(service / workflow / agent)只依赖 `LLMProvider`,通过工厂按配置注入具体实现。
- 流式统一为 SSE 输出到前端。

## 7. RAG 管线

```mermaid
flowchart LR
  Upload[文档上传] --> Parse[解析 PDF/MD/TXT]
  Parse --> Chunk[分块 + 重叠]
  Chunk --> Embed[embedding]
  Embed --> Store[(pgvector 存储)]
  Query[用户提问] --> QEmbed[query embedding]
  QEmbed --> Search[向量检索 top-k]
  Store --> Search
  Search --> Rerank[可选 rerank]
  Rerank --> Inject[拼接上下文 + 引用]
  Inject --> LLM[LLM 生成]
```

- 解析/分块/embedding 为重任务,走 **Celery worker** 异步;文档状态机:`pending → parsing → embedding → ready / failed`。
- 检索用 pgvector `<=>`(cosine)+ `idx_kb_segment_embedding`(HNSW/IVFFlat)。
- 回答附 `kb_segment` 引用,前端可溯源。

## 8. 工作流引擎

- 工作流以 **有向图**(节点 + 边)存储为 JSON(`wf_workflow.graph`)。
- 执行器做拓扑排序后逐节点执行,节点间用变量池传递数据(`{{node_id.output}}`)。
- MVP 节点类型:`start` / `end` / `llm` / `knowledge_retrieval` / `condition`(if-else)/ `code`(沙箱执行)/ `template`。
- 每个节点实现统一接口 `async def run(inputs, context) -> outputs`;新增节点类型只加一个执行器 + 一个 React Flow 节点组件。
- 运行记录落 `wf_run` / `wf_node_run`,前端可回放每个节点的输入输出。
- 前端用 **React Flow** 做拖拽编排,图结构与后端 `graph` JSON 双向同步。

## 9. Agent 设计

- 基于 **ReAct 循环**:LLM 决策 → 选择工具 → 执行 → 观察 → 迭代,直到产出最终答案或达最大轮次。
- 工具经 Claude **function calling**(tool use)暴露;工具定义存 `agent_tool`,含 JSON schema。
- 内置工具:知识库检索、HTTP 请求、代码执行;轨迹落 `agent_thought` 便于调试。

## 10. 鉴权与发布

- 平台内部:JWT(登录态),`core/` 提供依赖注入式鉴权。
- 已发布应用对外:`auth_api_key`,按 key 限流与计量。
- 应用配置版本化(`app_app_config`),发布即锁定一个版本。

## 11. 部署

`docker compose`(无 `version` 头)五服务:

| 服务 | 镜像/构建 | 职责 |
|---|---|---|
| `db` | postgres:16 + pgvector | 关系数据 + 向量 |
| `redis` | redis:7 | 缓存 + Celery broker/backend |
| `api` | backend Dockerfile | FastAPI |
| `worker` | backend Dockerfile | Celery worker |
| `web` | web Dockerfile | Next.js |

本地开发:`docker compose up -d db redis`,api/web 本地热重载;迁移 `uv run alembic upgrade head`。

## 12. 关键设计权衡

| 决策 | 取舍 |
|---|---|
| pgvector 而非独立向量库 | 一周内少运维一个服务;数据量上来后可换 Qdrant/Weaviate |
| FastAPI(async)而非 Flask | 流式 SSE + 高并发友好,生态现代 |
| Claude 优先 + provider 抽象 | 默认最强模型,又保留多模型扩展口 |
| Celery 处理重任务 | 文档/embedding 不阻塞请求,可水平扩展 worker |
| 工作流图存 JSON | 灵活、前后端同构;牺牲部分查询能力 |
