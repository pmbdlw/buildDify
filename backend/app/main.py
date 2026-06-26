"""FastAPI 应用入口。

各模块路由在 app/api/ 下定义后,在此用 app.include_router 注册。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, llm_gateway
from app.core.config import settings

app = FastAPI(title=settings.app_name)

# 开发期允许前端跨域(生产应收紧 allow_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api")
app.include_router(llm_gateway.router)  # 兼容网关:/v1/chat/completions、/v1/messages、/v1/embeddings

# 后续模块:chat / knowledge / app / workflow / agent
