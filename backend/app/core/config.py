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

    # LLM —— 默认上游 provider:anthropic | openai
    llm_provider: str = "anthropic"

    # Anthropic(Claude)
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""  # 留空用官方默认
    anthropic_default_model: str = "claude-sonnet-4-6"

    # OpenAI / OpenAI 兼容(GPT、DeepSeek、vLLM、本地 等,改 base_url 即可)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_default_model: str = "gpt-4o-mini"

    # embedding(默认走 OpenAI 兼容端点;Anthropic 无原生 embedding)
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 768  # 讯飞 xop3qwen8bembedding 输出维度;kb_segment.embedding 列宽

    # 知识库 RAG
    kb_chunk_size: int = 500  # 分块目标字符数
    kb_chunk_overlap: int = 80  # 相邻分块重叠字符数
    kb_retrieval_top_k: int = 4  # 检索默认召回条数

    # Agent
    agent_max_iterations: int = 6  # ReAct 单回合最大推理步数(防止工具调用死循环)


settings = Settings()
