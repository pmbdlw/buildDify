"""FastAPI 应用入口。

各模块路由在 app/api/ 下定义后,在此用 app.include_router 注册。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, apps, auth, chat, knowledge, llm_gateway, metrics, workflows
from app.core.config import settings
from app.core.observability import RequestLoggingMiddleware, setup_logging

setup_logging(settings.debug)

app = FastAPI(title=settings.app_name)

# 请求日志 + 异常兜底(最外层中间件,覆盖全部路由)
app.add_middleware(RequestLoggingMiddleware)

# 跨域来源由 settings.cors_origin_regex 控制(默认仅本机;IP/域名访问经环境变量放行)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(apps.router, prefix="/api")
app.include_router(apps.public_router)  # 对外运行:/v1/apps/{id}/chat(API Key 鉴权)
app.include_router(workflows.router, prefix="/api")
app.include_router(agent.router, prefix="/api")  # Agent:工具 CRUD + ReAct 调试 + 轨迹回放
app.include_router(metrics.router, prefix="/api")  # 可观测:/api/metrics、/api/metrics/usage
app.include_router(
    llm_gateway.router
)  # 兼容网关:/v1/chat/completions、/v1/messages、/v1/embeddings
