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
    deepseek_model: str = "deepseek-chat"
    openai_api_key: str | None = None

    # Database
    database_url: str = Field(..., description="postgresql+asyncpg://...")
    redis_url: str | None = "redis://localhost:6379"

    # Auth
    secret_key: str = Field(..., min_length=16)
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30


settings = Settings()
