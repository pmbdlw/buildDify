"""应用配置 —— 从环境变量 / .env 加载。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "buildDify"
    debug: bool = False

    # 数据库 / Redis
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/builddify"
    redis_url: str = "redis://localhost:6379/0"

    # 鉴权
    jwt_secret: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # LLM
    anthropic_api_key: str = ""
    default_model: str = "claude-sonnet-4-6"
    embedding_model: str = "claude-sonnet-4-6"


settings = Settings()
