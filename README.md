# buildDify

定制化 LLM 应用开发平台,对标 **Dify** 的能力模型,从零构建(不使用 Dify 源码)。覆盖四大能力:

- 💬 **对话应用(Chatbot)** —— 与 Claude 流式对话,历史落库
- 📚 **知识库 RAG** —— 上传文档 → 分块 → embedding → pgvector 检索 → 带引用问答
- 🔀 **可视化工作流** —— React Flow 编排,拓扑执行引擎 + 条件分支 + 运行回放
- 🤖 **Agent + 工具调用** —— ReAct 循环 + function calling,内置知识检索 / HTTP / 代码执行,思考轨迹可视化

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12 · FastAPI · SQLAlchemy 2.0(async)· Alembic · Celery · Redis |
| 数据库 | PostgreSQL 16 + **pgvector**(向量检索,不另起独立向量库) |
| 前端 | Next.js 16(App Router)· TypeScript · Tailwind · React Flow · AG Grid 社区版 |
| LLM | Anthropic / OpenAI 兼容双格式,经 `app/llm` provider 抽象;默认 Claude |
| 包管理 | 后端 `uv` · 前端 `pnpm` |

## 架构分层

请求严格单向流动:**api → services → repositories → models**。

```
backend/app/
  api/           路由层(HTTP 解析/校验 + 调 service)
  services/      业务逻辑
  repositories/  数据访问(SQLAlchemy)
  models/        ORM 模型
  schemas/       Pydantic 输入/输出
  llm/           模型 provider 抽象 + Anthropic/OpenAI 实现
  workflow/      工作流执行引擎
  agent/         Agent 内置工具 + ReAct 循环
  core/          配置 / 鉴权 / 依赖注入 / 可观测
web/             Next.js 前端(对话/知识库/应用/工作流四模块)
```

详见 [架构设计](docs/architecture.md) 与 [实施计划](docs/implementation-plan.md)。

## 快速开始

### 方式一:一键全栈(Docker Compose)

```bash
cp backend/.env.example backend/.env   # 填入 LLM 密钥(见下)
docker compose up -d --build           # 起 db / redis / api / worker / web
```

- 前端:http://localhost:3000
- 后端 API / 文档:http://localhost:8000 · http://localhost:8000/docs
- api 容器启动时自动执行 `alembic upgrade head`。

### 方式二:本地开发(热重载)

```bash
docker compose up -d db redis          # 只起依赖(db 映射宿主机 5433)

# 后端(backend/)
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run celery -A app.tasks.celery_app worker -l info   # 另开一个终端,处理文档分块/embedding

# 前端(web/)
pnpm install
pnpm dev
```

## 环境变量(`backend/.env`)

最少需配置一个可用的 LLM 上游。本项目实测对接讯飞 MaaS(OpenAI 兼容端点 + 768 维 embedding):

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=<your-key>
OPENAI_BASE_URL=<openai-兼容端点,如讯飞 MaaS>
OPENAI_DEFAULT_MODEL=<对话模型>
EMBEDDING_MODEL=<embedding 模型>
EMBEDDING_DIM=768            # 须与 kb_segment.embedding 列宽一致
```

或用官方 Claude:`LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`。完整项见 `backend/.env.example`。

> 模型按名路由:`claude*` 走 Anthropic,`gpt*/deepseek/text-embedding*` 走 OpenAI 兼容;留空用默认 provider。

## 主要接口

| 能力 | 接口 |
|---|---|
| 鉴权 | `POST /api/auth/register` · `/login` · `GET /api/auth/me` |
| 对话(SSE) | `POST /api/chat` · `GET /api/conversations` |
| 知识库 | `POST /api/knowledge/datasets` · `.../documents`(上传) |
| 应用构建器 | `/api/apps`(CRUD/配置/发布)· `POST /v1/apps/{id}/chat`(API Key 对外) |
| 工作流 | `/api/workflows`(CRUD)· `POST /api/workflows/{id}/run` |
| Agent | `/api/apps/{id}/agent/tools*` · `POST /api/apps/{id}/agent/chat`(SSE 轨迹) |
| 兼容网关 | `POST /v1/chat/completions` · `/v1/messages` · `/v1/embeddings` |
| 可观测 | `GET /api/metrics`(进程指标)· `GET /api/metrics/usage`(token 用量) |

## 测试与质量

```bash
# 后端(backend/)
uv run pytest          # 全部用例
uv run ruff check app tests

# 前端(web/)
pnpm lint
pnpm build
```

## 部署

### 部署到自己的服务器(纯 IP 演示)

用 `docker-compose.prod.yml`,改动相比开发版:前端 API 地址用 `${SERVER_HOST}` 注入(替代写死的 localhost)、db/redis 不对外暴露、web/api 走 3000/8000 避开 80/443。

```bash
git clone https://github.com/pmbdlw/buildDify.git && cd buildDify

cp .env.example .env                    # 把 SERVER_HOST 改成服务器公网 IP
cp backend/.env.example backend/.env    # 填入 LLM 密钥(见上方环境变量)

docker compose -f docker-compose.prod.yml up -d --build
```

- 前端:`http://<SERVER_HOST>:3000` · 后端:`http://<SERVER_HOST>:8000`
- `SERVER_HOST` 在构建时被内联进前端包,**改了 IP 要重新 `--build`**。
- 云服务器需在安全组放行入站 **3000 / 8000**。
- 更新:`git pull` 后再跑一次 `up -d --build`。

> 此配置面向演示:无 HTTPS、沿用占位密钥。正式上线请换强密钥并在前面挂 Nginx/Caddy 做反代与 TLS。

完整说明见 [部署文档](docs/deployment.md)。
