# 部署文档

## 一、Docker Compose 一键全栈

适用于演示与小规模自托管。

```bash
cp backend/.env.example backend/.env     # 填 LLM 密钥
docker compose up -d --build
docker compose ps                        # 看健康状态
docker compose logs -f api               # 跟踪 api 日志(含结构化请求日志)
```

服务拓扑:

| 服务 | 镜像/构建 | 端口(宿主机) | 说明 |
|---|---|---|---|
| `db` | pgvector/pgvector:pg16 | 5433→5432 | PostgreSQL + pgvector |
| `redis` | redis:7 | 6379 | Celery broker / backend |
| `api` | `backend/Dockerfile` | 8000 | FastAPI;启动前自动 `alembic upgrade head` |
| `worker` | `backend/Dockerfile` | — | Celery worker(文档分块/embedding) |
| `web` | `web/Dockerfile` | 3000 | Next.js standalone |

容器内服务互联用服务名(`db:5432` / `redis:6379`),compose 已在 `api`/`worker` 的 `environment` 覆盖 `DATABASE_URL`/`REDIS_URL`;`backend/.env` 里指向 `localhost:5433` 的本地值只用于本地直跑。

### 前端 API 地址

`NEXT_PUBLIC_API_BASE` 在前端 **构建时** 内联进客户端包,默认 `http://localhost:8000`(浏览器经宿主机访问 api)。若部署到域名,改 `web` 服务的 build arg 并重建:

```yaml
web:
  build:
    context: ./web
    args:
      NEXT_PUBLIC_API_BASE: https://api.example.com
```

## 二、常用运维

```bash
docker compose up -d --build api worker     # 仅重建后端
docker compose exec api uv run alembic upgrade head   # 手动迁移
docker compose exec db psql -U postgres -d builddify  # 进库
docker compose down                          # 停止(保留数据卷)
docker compose down -v                        # 连数据卷一起删(慎用)
```

数据持久化在命名卷 `pg_data` / `redis_data`。

## 三、生产加固清单(MVP 未做,部署前补)

- **密钥**:`JWT_SECRET` 换 32+ 字节随机串;LLM 密钥用密钥管理而非明文 `.env`。
- **CORS**:`app/main.py` 现为开发期放开 `localhost`,生产收紧为固定域名。
- **数据库**:`db` 不必对外暴露端口;改强口令;开启定期备份。
- **HTTPS**:api/web 前置反向代理(Nginx/Caddy)终止 TLS。
- **可观测**:`GET /api/metrics` 为进程内计数,生产接 Prometheus/OTel;日志已是结构化 JSON,接入采集即可。
- **工作流/Agent**:`code` 节点与 `code_exec` 工具用受限 builtins,生产建议进一步沙箱化(子进程/容器隔离);`http_request` 工具按需加 `allow_url_prefix` 限制目标。
- **伸缩**:`worker` 可水平扩容(`docker compose up -d --scale worker=3`);`api` 无状态可多副本。

## 四、健康检查与排错

| 现象 | 排查 |
|---|---|
| api 起不来 | `docker compose logs api`;多为 `.env` 缺失或迁移失败 |
| 上传文档卡 `processing` | 看 `worker` 日志;确认 embedding 端点可达、维度=`EMBEDDING_DIM` |
| 对话/Agent 报错 | api 日志按 `X-Request-ID` 关联;多为 LLM 上游鉴权/模型名问题 |
| 前端调不通 | 确认 `NEXT_PUBLIC_API_BASE` 与实际 api 地址一致(构建时生效) |
