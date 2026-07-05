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
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]

    # LLM
    llm_provider: str = "deepseek"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_default_model: str = "deepseek-v4-flash"
    deepseek_pro_model: str = "deepseek-v4-pro"
    deepseek_reasoner_model: str = "deepseek-reasoner"  # C32: R1-series reasoning model
    deepseek_model: str = "deepseek-v4-flash"
    openai_api_key: str | None = None
    # C32: When True, FinancialAgent uses deepseek-reasoner for streaming responses.
    # The model produces reasoning_content (思维链) which the frontend displays in
    # the collapsible raw-chain drawer.  Set ENABLE_DEEPSEEK_REASONER=false in .env to disable.
    enable_deepseek_reasoner: bool = True

    # Embedding (Phase 2C / 2D.5)
    # Supported values: mock (default, CI-safe) | openai | deepseek
    embedding_provider: str = "mock"
    embedding_model: str | None = None          # override default model per provider
    embedding_batch_size: int = 64              # max texts per embed_texts() API call
    # Batch-level retry for OpenAI provider (Phase 2D.5)
    embedding_batch_retry_count: int = 2        # retries per batch (0 = no retry)
    embedding_batch_retry_backoff_seconds: float = 1.5  # initial backoff; doubles each retry
    embedding_batch_timeout_seconds: float = 30.0       # per-batch HTTP timeout

    # RAG hybrid search weights (Phase 2D)
    # combined = vector_weight*v + keyword_weight*k + source_boost + recency_boost
    # When one score is absent the weights are auto-normalised (see financial_rag_tool.py)
    rag_vector_weight: float = 0.6
    rag_keyword_weight: float = 0.3
    rag_source_boost_weight: float = 0.07       # max additive boost for official sources
    rag_recency_boost_weight: float = 0.03      # max additive boost for very recent docs
    rag_mmr_enabled: bool = True                # Maximal Marginal Relevance diversity
    rag_mmr_lambda: float = 0.7                 # relevance/diversity trade-off (0=diverse,1=relevant)
    rag_mmr_max_per_doc: int = 2               # max chunks per document in MMR output

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

    # ETL（Phase 2B）
    # True（默认）：ETL 功能可用，industry_rank 从 PostgreSQL industry_rank_snapshot 读取。
    # False：ETL 关闭，industry_rank 立即返回 partial=True（不影响主服务）。
    etl_enabled: bool = True

    # Stock Fundamental Service（Phase 1）
    # Tushare Pro token — 申请地址 tushare.pro，免费注册后获取
    # 生产环境通过 Docker secrets 注入，禁止硬编码
    tushare_token: str | None = None
    # AkShare 备用数据源开关（默认关闭）
    # 设置 ENABLE_AKSHARE=true 后 Tushare 失败时自动降级到 AkShare
    enable_akshare: bool = False
    # Tushare 令牌桶速率限制（积分/分钟）；基础账户 500，付费账户可调高
    tushare_rate_limit_per_min: int = 500
    # Tushare API 调用超时（秒）
    tushare_timeout_seconds: float = 15.0
    # Fundamental Service 缓存版本号（修改数据结构时递增，自动清空旧缓存）
    fs_cache_version: str = "v1"

    # Multi-Agent Orchestrator (Phase 2E-1)
    # 默认关闭。设置 ENABLE_MULTI_AGENT_ORCHESTRATOR=true 后对复杂金融研究问题
    # 启用多 Agent 编排（FundamentalAgent / MarketAgent / NewsAgent / RiskReview / Synthesis）。
    # 简单行情查询仍走原 FinancialAgent 单 Agent 路径。
    # Orchestrator 内部异常时自动 fallback 至原 FinancialAgent。
    enable_multi_agent_orchestrator: bool = False

    # Auth
    secret_key: str = Field(..., min_length=16)
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30


settings = Settings()
