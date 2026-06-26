# 实施计划 —— 一周冲刺

> 配合 AI 编程工具,7 天产出可运行 MVP。每天一个**纵切片**:可独立运行、可演示、可验证。详见 [架构设计](./architecture.md)。

## 原则

- **纵切而非横切**:每天交付一条贯穿前后端的可用链路,而非"先写完所有 model 再写所有 API"。
- **可验证**:每天结束有明确验收标准(能跑通的命令/能点的页面)。
- **AI 协作**:用 `/scaffold-slice` 起骨架、`/db-migration` 出迁移,人审关键设计与验收。
- **先打通再优化**:MVP 阶段容忍 TODO,优先把四条能力链路串起来。

## 里程碑

| 里程碑 | 时点 | 标志 |
|---|---|---|
| M1 地基就绪 | D1 末 | compose 起得来,迁移能跑,能登录 |
| M2 对话可用 | D2 末 | 前端能与 Claude 流式对话并存历史 |
| M3 RAG 可用 | D3 末 | 上传文档后能基于知识库问答并附引用 |
| M4 应用 + 工作流 | D5 末 | 能创建 chatbot 应用;能跑一个多节点工作流 |
| M5 Agent + 收尾 | D7 末 | Agent 工具调用可用;compose 端到端跑通 |

---

## D1 — 地基(脚手架 + 鉴权)

**目标**:把骨架立起来,服务能起、库能迁、人能登录。

- [x] `git init` + `.gitignore`
- [x] backend 骨架(`uv init`,按架构文档建 `app/` 分层目录)
- [x] web 骨架(`pnpm create next-app`,Tailwind + App Router)
- [x] `docker-compose.yml`:db(pg16+pgvector,宿主机 **5433**)/ redis,本地起依赖
- [x] SQLAlchemy async 引擎 + Alembic 初始化;`auth_user` 表 + 首个迁移
- [x] JWT 鉴权:注册/登录/me 接口 + `core/` 鉴权依赖
- [x] 前端登录页打通(`web/app/login`)

**验收**:✅ `docker compose up -d db redis` + `uv run alembic upgrade head` 成功;注册→登录→拿 token→`/me` 全链路 curl 通过;`uv run pytest` 3 passed;前后端 `build` 通过。

> 备注:宿主机 5432 被既有容器占用,本项目 db 映射到 **5433**(见 `.env` / `docker-compose.yml`)。

## D2 — 对话应用(Chatbot 链路)

**目标**:前端与 Claude 流式对话,历史落库。

- [x] `llm/` provider 抽象 + **双格式上游**(`AnthropicProvider` + `OpenAIProvider`,chat/stream/embed)+ 工厂路由
- [x] **双格式下游网关**:`/v1/chat/completions`(OpenAI)、`/v1/messages`(Anthropic)、`/v1/embeddings`,跨格式互通(讯飞 MaaS 实测)
- [x] `app_conversation` / `app_message` 表 + 迁移(`idx_` 命名自动生效)
- [x] 对话 service:建会话、存消息、构建历史请求(流式落库用独立会话)
- [x] SSE 流式接口 `POST /api/chat` + `GET /api/conversations`、`/conversations/{id}/messages`
- [x] 前端对话 UI(侧边栏会话列表 + 流式渲染 + Enter 发送)

**验收**:✅ 浏览器实测 —— 登录→发消息→流式回复→新会话自动建标题→刷新后会话列表与完整历史均在(讯飞 `xopqwen36v35b`)。后端 18 passed,前端 build 通过。

## D3 — 知识库 RAG

**目标**:上传文档后能基于知识库问答并附引用。

- [x] `kb_dataset` / `kb_document` / `kb_segment`(含 `vector(768)` 列 + 索引)+ 迁移(`CREATE EXTENSION vector`)
- [x] 文档上传接口 + 解析(PDF/MD/TXT,上传时同步解析为文本落库)
- [x] Celery worker:分块 → embedding → 入库;文档状态机 `pending→processing→ready/error`
- [x] 检索 service:query embedding + pgvector 余弦 top-k
- [x] 对话链路接入 RAG:`ChatIn.dataset_id` → 检索 → 拼接 system 上下文 → 生成 → SSE meta 返回引用
- [x] 前端:知识库管理页(建库/上传/状态轮询)+ 对话页数据集选择 + 引用来源折叠展示

**验收**:✅ 浏览/curl 实测 —— 上传 MD→worker 处理至 ready(讯飞 768 维 embedding)→选库提问"数据库映射到哪个端口",回答"5433,因 5432 常被占用 [1]"并带 1 条引用。后端 26 passed,前后端 build 通过。

> worker 启动:`uv run celery -A app.tasks.celery_app worker -l info`(需 redis)。

## D4 — 应用构建器(Chatbot 应用类型)

**目标**:把"对话"产品化为可配置、可发布的应用。

- [x] `app_app` / `app_app_config`(版本化,published_config_id 指向已发布版)/ `auth_api_key` + 迁移;`app_conversation` 加 `app_id`
- [x] 应用 CRUD + 配置(prompt、模型、temperature/max_tokens、绑定知识库);每次保存自增 version
- [x] 运行接口按应用配置驱动对话/检索(调试用最新版,对外用已发布版;复用 RAG 链路)
- [x] `auth_api_key`(sha256 哈希,明文仅创建时返回一次)+ 对外运行接口 `POST /v1/apps/{id}/chat`(X-API-Key / Bearer 鉴权)
- [x] 前端:应用列表、应用配置页(含 API Key 管理)、调试对话窗(SSE)

**验收**:✅ curl 实测 —— 新建 chatbot 应用→存配置(system_prompt 生效:"喵")→发布→调试窗流式对话通过;创建 API Key→`/v1/apps/{id}/chat` 带 key 调通、无/错 key 401、吊销后失效、last_used_at 更新。后端 33 passed,前后端 build 通过。

## D5 — 工作流引擎

**目标**:节点编排引擎 + 可视化编辑器,跑通多节点工作流。

- [ ] `wf_workflow` / `wf_run` / `wf_node_run` + 迁移
- [ ] 执行引擎:拓扑排序 + 变量池 + 统一节点接口
- [ ] 节点:`start`/`end`/`llm`/`knowledge_retrieval`/`condition`/`code`/`template`
- [ ] 运行接口 + 运行记录回放
- [ ] 前端:React Flow 编辑器(拖拽节点、连线、配置面板、运行可视化)

**验收**:用编辑器搭一个"输入 → 检索 → LLM → 输出"的流程并成功运行,能看到每个节点的输入输出。

## D6 — 前端打磨 + 联调

**目标**:四条链路在 UI 上顺畅可用。

- [ ] 统一布局/导航/鉴权态;AG Grid(社区版)做列表页
- [ ] 对话/知识库/应用/工作流四个模块 UI 收口
- [ ] 错误处理、loading、空态
- [ ] 端到端联调,修主链路 bug

**验收**:从登录到使用四大能力,全程无阻断性 bug。

## D7 — Agent + 部署收尾

**目标**:Agent 工具调用可用;整套 compose 端到端跑通。

- [ ] `agent_tool` / `agent_thought` + 迁移
- [ ] ReAct 循环 + function calling;内置工具(知识库检索 / HTTP / 代码执行)
- [ ] Agent 应用类型 + 前端轨迹展示
- [ ] 可观测:请求日志、token 计量、错误上报
- [ ] backend/web Dockerfile + 完整 `docker compose up` 端到端验证
- [ ] README + 部署文档

**验收**:`docker compose up -d` 一键起全栈;Agent 能自主调用工具完成一个任务并展示思考轨迹。

---

## 风险与应对

| 风险 | 应对 |
|---|---|
| 工作流引擎(D5)最复杂,易超时 | 先做线性流程(无分支)打通,condition/code 节点作为增量 |
| RAG 解析多格式耗时 | MVP 先支持 TXT/MD,PDF 用成熟库快速接入,复杂格式留后 |
| 流式 SSE + 前端渲染联调坑多 | D2 就把流式跑通,后续链路复用 |
| 范围过大(四能力)挤压打磨 | 严格按纵切交付,每天宁可砍深度不砍链路完整性 |
| 模型成本/限流 | 开发用 `claude-sonnet-4-6` 控成本,演示关键路径用 `claude-opus-4-8` |
