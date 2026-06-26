# 后端镜像:api 与 worker 共用(命令在 compose 里区分)。
FROM python:3.12-slim

# uv:快速依赖安装(官方静态二进制)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 先装依赖(利用缓存层):仅在依赖清单变化时重装
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev || uv sync --no-install-project --no-dev

# 再拷源码并安装项目自身
COPY . .
RUN uv sync --no-dev || true

EXPOSE 8000

# 默认起 API;worker 在 compose 覆盖 command
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
