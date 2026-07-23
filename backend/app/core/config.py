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
    app_version: str = "1.1.0-free-rc1"
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
    database_connection_mode: str = "transaction_pooler"  # direct | session_pooler | transaction_pooler
    database_transaction_pool_strategy: str = "small_queue_pool"  # small_queue_pool | null_pool
    database_pool_pre_ping: bool = True
    database_pool_size: int = 2
    database_max_overflow: int = 2
    database_direct_pool_size: int = 5
    database_direct_max_overflow: int = 10
    database_pool_recycle_seconds: int = 1800
    database_pool_timeout_seconds: float = 30.0
    database_command_timeout_seconds: float = 45.0
    database_sql_echo: bool = False
    database_sql_hide_parameters: bool = True
    auth_db_lookup_timeout_seconds: float = 10.0
    auth_db_connect_timeout_seconds: float = 10.0
    auth_db_query_timeout_seconds: float = 10.0
    auth_db_cleanup_timeout_seconds: float = 3.0
    auth_user_cache_ttl_seconds: int = 60
    auth_db_timeout_threshold: int = 3
    auth_circuit_open_seconds: float = 20.0

    # Company V2 RAG repository backend（Phase 6T-J1）
    # 合法值：database（默认，PostgreSQL 永久持久化）/ memory（仅隔离测试用，非永久）
    # database 初始化失败时抛结构化错误，禁止静默 fallback 到 memory。
    company_v2_rag_repository_backend: str = "database"
    company_v2_rag_chunk_batch_size: int = 200
    company_v2_rag_db_run_timeout_seconds: float = 60.0
    chat_runtime_mode: str = "legacy"  # legacy | layered_v1 | shadow
    chat_layered_intents: str = "financial_report,financial_comparison,official_report_pdf,financial_snapshot,quote_query"
    agent_executor_mode: str = "legacy"  # legacy | pi_compatible_shadow | pi_compatible
    pi_agent_max_turns: int = 3
    pi_agent_max_tool_calls: int = 4
    pi_agent_max_parallel_tools: int = 2
    pi_agent_default_deadline_ms: int = 5000
    pi_official_report_tool_timeout_ms: int = 10000
    pi_agent_shadow_enabled: bool = False
    pi_agent_allowed_agents: str = ""
    pi_agent_shadow_diagnostics_path: str = ""
    # ── Phase 6V-P1.7: staging canary proposal — everything defaults OFF ──
    # Formal enablement requires an approved, versioned authorization; these
    # defaults keep the canary fully disabled (proposal only).
    pi_executor_global_kill_switch: bool = False
    pi_canary_environment: str = "staging"          # staging only; production needs its own authorization
    pi_canary_authorization_status: str = "proposed"  # proposed|approved|rejected|revoked|disabled
    pi_canary_allowed_agents: str = ""              # exact agent ids, comma separated, no wildcards
    pi_canary_rollout_percent: float = 0.0
    pi_canary_max_rollout_percent: float = 5.0
    pi_canary_fallback_mode: str = "legacy"
    pi_canary_environment_kill_switch: bool = False
    pi_canary_agent_kill_switch: bool = False
    pi_canary_authorization_expires_at: str = ""
    pi_canary_config_version: int = 1
    pi_canary_stable_bucket_salt: str = "pi_v1"   # stable across config_version changes; ensures monotonic rollout
    pi_canary_approval_reference: str = ""
    pi_canary_auto_rollback_enabled: bool = True
    pi_canary_health_window_minutes: int = 30
    pi_canary_min_sample_size: int = 50
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
    # Phase 6A: Zero-cost data mode
    # DATA_MODE=free: skip Tushare Pro-only APIs, use BaoStock+AkShare
    data_mode: str = "standard"  # "standard" | "free"
    enable_tushare: bool = True   # Set False in free mode to disable Tushare Pro APIs
    enable_baostock: bool = False  # BaoStock primary for free mode
    enable_report_pdf: bool = False  # Report PDF attachment feature
    enable_report_rag: bool = False  # Phase 6F: PDF→pgvector RAG
    enable_company_v2_debug_api: bool = True
    debug_company_v2: bool = False
    company_v2_raw_preview_chars: int = 2000
    company_v2_provider_timeout_seconds: float = 8.0
    company_v2_provider_timeout_baostock_seconds: float = 20.0
    company_v2_provider_timeout_akshare_seconds: float = 12.0
    company_v2_provider_timeout_http_seconds: float = 8.0
    company_v2_debug_full_timeout_seconds: float = 45.0
    company_v2_debug_module_timeout_seconds: float = 20.0
    company_v2_debug_script_symbol_timeout_seconds: float = 90.0
    # Phase 6G: Report RAG embedding provider (separate from financial_rag embedding_provider)
    # mock (default, CI-safe, 0-cost) | local (sentence-transformers) | disabled
    report_embedding_provider: str = "mock"
    # Model name or local path for sentence-transformers (used when report_embedding_provider=local)
    # Recommended: BAAI/bge-small-zh-v1.5 (384d), intfloat/multilingual-e5-small (384d)
    report_embedding_model: str | None = None
    # Target embedding dimension — must match report_chunks.embedding vector(N)
    # Default 1536 matches current schema. Change requires new migration.
    report_embedding_dim: int = 384
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

    # AI Fundamental Analysis Agent (Phase 3)
    # ai_provider: which LLM provider to use for fundamental analysis
    #   "deepseek" (default) — uses DEEPSEEK_API_KEY
    #   "openai"             — uses OPENAI_API_KEY (future)
    # ai_enabled: master switch; set to false to always return partial=true
    ai_provider: str = "deepseek"
    ai_enabled: bool = True

    @property
    def ai_api_key(self) -> str | None:
        """Unified API key lookup based on ai_provider."""
        if self.ai_provider == "deepseek":
            return self.deepseek_api_key
        if self.ai_provider == "openai":
            return self.openai_api_key
        return None

    # Phase 6K: Report Chat Cache
    report_chat_cache_ttl_seconds: int = 1800        # 30 min default
    enable_report_chat_cache: bool = True
    report_chat_cache_version: str = "v1"

    # Phase 6K: Report Chat Rate Limit
    report_chat_rate_limit_per_minute: int = 10
    report_chat_rate_limit_per_hour: int = 100
    enable_report_chat_rate_limit: bool = True

    # Phase 6K: Report Chat Session Memory
    report_chat_memory_ttl_seconds: int = 3600       # 1 hour
    report_chat_memory_max_turns: int = 5
    enable_report_chat_memory: bool = True

    # Phase 6T-H: Financial Evidence Fusion Rollout
    company_v2_financial_fusion_enabled: bool = False
    company_v2_financial_fusion_rollout_percent: int = 0
    company_v2_financial_fusion_symbol_allowlist: str = ""
    company_v2_financial_fusion_auto_run: bool = False
    company_v2_financial_fusion_max_fields_per_request: int = 10
    company_v2_financial_fusion_timeout_seconds: int = 60
    company_v2_financial_fusion_cache_ttl_seconds: int = 86400
    company_v2_financial_fusion_cache_version: str = "v1"
    company_v2_financial_fusion_structured_data_version: str = "v1"
    company_v2_financial_fusion_field_definition_registry_version: str = "v1"
    company_v2_financial_fusion_tolerance_version: str = "v1"
    company_v2_financial_fusion_singleflight_ttl_seconds: int = 60
    company_v2_financial_fusion_stage3_authorized: bool = False
    company_v2_financial_fusion_worker_mode: str = "shadow"
    company_v2_financial_fusion_worker_enabled: bool = False
    company_v2_financial_fusion_worker_lease_seconds: int = 60
    company_v2_financial_fusion_worker_heartbeat_seconds: int = 15

    # Auth
    secret_key: str = Field(..., min_length=16)
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30


settings = Settings()


def get_settings() -> Settings:
    """Return the singleton settings instance."""
    return settings
