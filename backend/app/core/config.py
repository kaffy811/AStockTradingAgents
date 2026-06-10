from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "TradingAgents Backend"
    app_env: str = "development"
    app_title: str = "TradingAgents API"
    app_version: str = "0.1.0"
    debug: bool = True
    cors_origins: list[str] = ["*"]

    # LLM
    llm_provider: str = "deepseek"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_default_model: str = "deepseek-v4-flash"
    deepseek_pro_model: str = "deepseek-v4-pro"
    deepseek_model: str = "deepseek-v4-flash"
    openai_api_key: str | None = None

    # Database
    database_url: str = Field(..., description="postgresql+asyncpg://...")
    redis_url: str | None = "redis://localhost:6379"
    # Set to False in production to skip Base.metadata.create_all at startup.
    # Production deployments should run: uv run alembic upgrade head
    enable_create_all: bool = True

    # Analysis Run Registry（M40-b）
    # 合法值：memory（默认，进程内，重启清空）/ redis（跨进程，支持多 worker）
    # 设置 ANALYSIS_RUN_REGISTRY=redis 并确保 REDIS_URL 可用后生效。
    analysis_run_registry: str = "memory"
    # Redis 模式下 run 键的 TTL（秒）。默认 6 小时。
    analysis_run_ttl_seconds: int = 21600
    # Redis 模式下每个 run 保留的最大事件条数（LTRIM 截断）。
    analysis_run_event_maxlen: int = 200

    # Default Analysis Engine（M42）
    # 合法值：custom_coordinator（默认，稳定路径）/ langgraph（LangGraph 灰度路径）
    # 仅当请求未显式传 engine 字段时生效；显式 engine 始终优先。
    # 设置 DEFAULT_ANALYSIS_ENGINE=langgraph 可将 staging 灰度至 LangGraph。
    # 非法值自动 fallback 至 custom_coordinator，不影响服务启动。
    default_analysis_engine: str = "custom_coordinator"

    # Auth
    secret_key: str = Field(..., min_length=16)
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30


settings = Settings()
