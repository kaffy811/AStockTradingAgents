import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.database import close_redis, connect_redis, init_db
from app.agent_runtime.canary_policy import get_effective_shadow_config_snapshot
from app.datasource.tushare_client import init_tushare_client
from app.routers import router
from app.routers.fundamentals import router as fundamentals_router
from app.routers.fundamentals_compat import compat_router
from app.routers.company_v2_debug import router as company_v2_debug_router
from app.routers.company_v2_financial_fusion import router as company_v2_financial_fusion_router
from app.routers.company_v2_report_rag import router as company_v2_report_rag_router
from app.routers.report_discovery import router as report_discovery_router
from app.routers.report_rag import router as report_rag_router
from app.routers.report_chat import report_chat_router
from app.services.cache_service import set_event_loop
from app.core.structured_debug_logger import CompanyV2RequestIdMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()       # Creates tables; raises clearly if Postgres is unreachable
    await connect_redis() # Best-effort; logs a warning if Redis is down
    # 注入 event loop 供 sync_* cache 方法使用（to_thread / ThreadPoolExecutor 场景）
    set_event_loop(asyncio.get_running_loop())
    # 初始化 Tushare 客户端（TUSHARE_TOKEN 未配置时仅记录 warning，不阻断启动）
    await init_tushare_client()
    # Phase 6V-P1.22+: log effective shadow config via formal runtime loader for provenance.
    # Snapshot is sanitized — no secrets, no user data, no auth headers.
    _shadow_snap = get_effective_shadow_config_snapshot(settings)
    import logging as _logging
    _log = _logging.getLogger("app.canary")
    _log.info(
        "pi_canary_runtime_snapshot loaded: rollout=%.1f config_version=%d "
        "salt_version=%s status=%s fail_closed=%s evidence_mode=%s pid=%d deployment_sha=%s",
        _shadow_snap["rollout_percent"],
        _shadow_snap["config_version"],
        _shadow_snap["stable_bucket_salt_version"],
        _shadow_snap["authorization_status"],
        _shadow_snap["fail_closed"],
        _shadow_snap["evidence_mode"],
        _shadow_snap["process_id"],
        _shadow_snap["deployment_sha"],
    )
    # Phase 6V-P1.24: persist snapshot to a probe-readable path for containerized staging.
    # Disabled by default (PI_CANARY_SNAPSHOT_PATH=""). Only written in staging containers.
    _snap_path = getattr(settings, "pi_canary_snapshot_path", "")
    if _snap_path:
        import json as _json, os as _os
        _os.makedirs(_os.path.dirname(_snap_path), exist_ok=True)
        with open(_snap_path, "w") as _f:
            _json.dump(_shadow_snap, _f, indent=2)
        _log.info("pi_canary_runtime_snapshot written to %s", _snap_path)
    yield
    await close_redis()


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CompanyV2RequestIdMiddleware)


# ── Phase 6N-8A: auth errors carry a stable error_code ────────────────────────
# 401/403 must NEVER be mistaken for a data-source failure by the frontend.
# Response keeps `detail` (backward compat) and adds `error_code` + `message`.
@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request, exc: StarletteHTTPException):
    from app.core.error_codes import AUTH_REQUIRED, FORBIDDEN

    payload = {"detail": exc.detail}
    if exc.status_code == 401:
        payload["error_code"] = AUTH_REQUIRED
        payload["message"] = "Authentication required"
    elif exc.status_code == 403:
        # Missing Authorization header surfaces as 403 via HTTPBearer —
        # semantically it is still "please log in".
        if isinstance(exc.detail, str) and "Not authenticated" in exc.detail:
            payload["error_code"] = AUTH_REQUIRED
            payload["message"] = "Authentication required"
        else:
            payload["error_code"] = FORBIDDEN
            payload["message"] = "Forbidden"
    elif isinstance(exc.detail, dict):
        # Router already provided a structured payload — pass through unchanged
        payload = exc.detail
    return JSONResponse(payload, status_code=exc.status_code, headers=exc.headers)

app.include_router(router, prefix="/api/v1")
# Stock Fundamental Service（Phase 1.5）— 路由前缀已在各 router 内部定义
app.include_router(fundamentals_router)    # /api/v1/stocks/{market}/{symbol}/fundamentals/...
app.include_router(compat_router)          # /api/v1/modules, /api/v1/stock/{code}/...
app.include_router(report_discovery_router)  # /api/v1/stocks/{market}/{code}/reports/discover
app.include_router(report_rag_router)        # /api/v1/stocks/{market}/{code}/reports/{id}/chunk|embed|rag
app.include_router(report_chat_router)       # /api/v1/stock/{code}/report-chat
app.include_router(company_v2_debug_router)  # /api/v2/company/{market}/{symbol}/debug/...
app.include_router(company_v2_financial_fusion_router)  # /api/v2/company/{market}/{symbol}/financial-fusion/...
app.include_router(company_v2_report_rag_router)  # /api/v2/company/{market}/{symbol}/reports/{id}/rag/...
