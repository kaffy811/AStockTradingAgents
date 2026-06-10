"""
Analysis Router — 技术面分析 + 基本面分析 + 综合分析接口。

路由：
  POST /analysis/technical      （推荐，主路由）
  POST /analysis/market         （兼容旧路由，行为完全一致）
  POST /analysis/fundamental    （基本面分析）
  POST /analysis/peer-comparison（同行对比分析）
  POST /analysis/comprehensive  （综合分析，并行调用三个 Agent）
  POST /analysis/runs           （M25-a SSE：创建分析运行）
  GET  /analysis/runs/{id}/events（M25-a SSE：实时进度事件流）
  GET  /analysis/runs/{id}      （M25-a SSE：查询运行状态）
  POST /analysis/runs/{id}/cancel（M25-a SSE：取消运行）

均需要登录（Bearer token）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.dependencies import get_current_user
from app.llm.factory import get_llm_client
from app.models.user import User
from app.agents.technical_analyst import TechnicalAnalystAgent
from app.agents.fundamental_analyst import FundamentalAnalystAgent
from app.agents.peer_comparison_analyst import PeerComparisonAnalystAgent
from app.agents.comprehensive_analysis_coordinator import (
    ComprehensiveAnalysisCoordinator,
    VALID_SCOPES,
    VALID_OUTPUT_LANGUAGES,
)
from app.agents.langgraph_analysis_graph import LangGraphAnalysisRunner
from app.agents.news_analyst import NewsAnalystAgent
from app.agents.realtime_analysis_runner import RealtimeAnalysisRunner
from app.agents.langgraph_realtime_runner import LangGraphRealtimeRunner as LangGraphRealtimeRunnerSSE
from app.core.config import settings
from app.services.run_registry_factory import get_run_registry
from app.services.run_registry_protocol import AnalysisRunRegistry

log = logging.getLogger(__name__)


def _safe_get_registry() -> AnalysisRunRegistry:
    """
    获取 AnalysisRunRegistry 单例，Registry 不可用时返回 HTTP 503。

    Redis 模式下 Redis 客户端不可用时 get_run_registry() 抛出 RuntimeError，
    此处统一转换为 503，避免 500 内部错误暴露给客户端。
    """
    try:
        return get_run_registry()
    except Exception as exc:
        log.error("AnalysisRunRegistry unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analysis run registry is unavailable. Please try again later.",
        )

router = APIRouter(prefix="/analysis", tags=["analysis"])

_VALID_ENGINES = frozenset({"custom_coordinator", "langgraph"})


def _resolve_analysis_engine(engine: str | None) -> str:
    """
    Resolve the effective analysis engine (M42 G2 灰度).

    Priority (highest first):
      1. Explicit engine in request body → always honoured as-is.
      2. settings.default_analysis_engine → set by DEFAULT_ANALYSIS_ENGINE env var.
      3. Hard fallback "custom_coordinator".

    Invalid values (from env or request) silently fall back to custom_coordinator
    so that a misconfigured env never breaks the service.
    """
    if engine in _VALID_ENGINES:
        return engine
    env_default = getattr(settings, "default_analysis_engine", "custom_coordinator")
    if env_default in _VALID_ENGINES:
        return env_default
    return "custom_coordinator"

_SUPPORTED_MARKETS = {"CN", "HK"}


# ── Request / Response schemas ────────────────────────────────────────────────

class TechnicalAnalysisRequest(BaseModel):
    market: str
    symbol: str

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _SUPPORTED_MARKETS:
            raise ValueError(f"market 只支持 CN 或 HK，收到 '{v}'")
        return upper

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("symbol 不能为空")
        return v


class TechnicalAnalysisResponse(BaseModel):
    market: str
    symbol: str
    report: str


# ── 共享处理逻辑 ──────────────────────────────────────────────────────────────

async def _run_technical_analysis(
    body: TechnicalAnalysisRequest,
    user: User,
) -> TechnicalAnalysisResponse:
    """实际执行分析的共享函数，供两个路由复用。"""
    try:
        llm   = get_llm_client()
        agent = TechnicalAnalystAgent(llm)
    except ValueError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    try:
        report = await asyncio.to_thread(agent.analyze, body.market, body.symbol)
    except RuntimeError as exc:
        log.error(
            "TechnicalAnalystAgent failed [%s/%s]: %s",
            body.market, body.symbol, exc,
        )
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return TechnicalAnalysisResponse(
        market=body.market,
        symbol=body.symbol,
        report=report,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/technical",
    response_model=TechnicalAnalysisResponse,
    summary="技术面分析（推荐）",
    description=(
        "生成 Markdown 技术面分析报告。\n\n"
        "- K线获取失败 → HTTP 503\n"
        "- 实时报价失败 → 使用 K线收盘价替代，分析照常进行\n"
        "- LLM 未配置 → HTTP 503\n"
        "- 需要 Bearer token 鉴权"
    ),
)
async def technical_analysis(
    body: TechnicalAnalysisRequest,
    user: User = Depends(get_current_user),
) -> TechnicalAnalysisResponse:
    return await _run_technical_analysis(body, user)


# ── Fundamental analysis ─────────────────────────────────────────────────────

class FundamentalAnalysisRequest(BaseModel):
    market: str
    symbol: str

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _SUPPORTED_MARKETS:
            raise ValueError(f"market 只支持 CN 或 HK，收到 '{v}'")
        return upper

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("symbol 不能为空")
        return v


class FundamentalAnalysisResponse(BaseModel):
    market: str
    symbol: str
    report: str


async def _run_fundamental_analysis(
    body: FundamentalAnalysisRequest,
    user: User,
) -> FundamentalAnalysisResponse:
    """执行基本面分析，供路由复用。"""
    try:
        llm   = get_llm_client()
        agent = FundamentalAnalystAgent(llm)
    except ValueError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    try:
        report = await asyncio.to_thread(agent.analyze, body.market, body.symbol)
    except RuntimeError as exc:
        log.error(
            "FundamentalAnalystAgent failed [%s/%s]: %s",
            body.market, body.symbol, exc,
        )
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return FundamentalAnalysisResponse(
        market=body.market,
        symbol=body.symbol,
        report=report,
    )


@router.post(
    "/fundamental",
    response_model=FundamentalAnalysisResponse,
    summary="基本面分析",
    description=(
        "生成 Markdown 基本面分析报告。\n\n"
        "- 基本面数据获取失败 → 字段标注为缺失，分析继续（不返回 5xx）\n"
        "- LLM 未配置 → HTTP 503\n"
        "- HK 股票 Phase 2 仅有公司名称，财务指标均为 null → 报告注明数据不足\n"
        "- 需要 Bearer token 鉴权"
    ),
)
async def fundamental_analysis(
    body: FundamentalAnalysisRequest,
    user: User = Depends(get_current_user),
) -> FundamentalAnalysisResponse:
    return await _run_fundamental_analysis(body, user)


# ── Peer comparison analysis ─────────────────────────────────────────────────

class PeerComparisonRequest(BaseModel):
    market: str
    symbol: str

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _SUPPORTED_MARKETS:
            raise ValueError(f"market 只支持 CN 或 HK，收到 '{v}'")
        return upper

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("symbol 不能为空")
        return v


class PeerComparisonResponse(BaseModel):
    market: str
    symbol: str
    report: str


async def _run_peer_comparison(
    body: PeerComparisonRequest,
    user: User,
    db:   AsyncSession,
) -> PeerComparisonResponse:
    """
    执行同行基本面对比分析（Phase 1D：动态同行）。

    调用 PeerComparisonAnalystAgent.analyze_async() 使用 DynamicPeerDiscoveryService。
    ComprehensiveAnalysisCoordinator 仍使用旧同步 analyze()，本轮不接入。
    """
    try:
        llm   = get_llm_client()
        agent = PeerComparisonAnalystAgent(llm)
    except ValueError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    try:
        report = await agent.analyze_async(db, body.market, body.symbol)
    except RuntimeError as exc:
        log.error(
            "PeerComparisonAnalystAgent.analyze_async failed [%s/%s]: %s",
            body.market, body.symbol, exc,
        )
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return PeerComparisonResponse(
        market=body.market,
        symbol=body.symbol,
        report=report,
    )


@router.post(
    "/peer-comparison",
    response_model=PeerComparisonResponse,
    summary="同行基本面对比分析",
    description=(
        "生成 Markdown 同行基本面对比报告。\n\n"
        "- 同行来源优先级：PEER_MAP 手动配置 > CN 行业 Hot Score 热门股\n"
        "- peers 未配置且无动态同行 → 报告说明原因，不编造\n"
        "- dynamic_hot peers → 报告明确说明 Hot Score 口径限制\n"
        "- 可比字段为空 → 报告说明缺少可比字段，不强行对比\n"
        "- HK peers → 报告声明「同行口径较粗，仅供参考」\n"
        "- LLM 未配置 → HTTP 503\n"
        "- 需要 Bearer token 鉴权"
    ),
)
async def peer_comparison_analysis(
    body: PeerComparisonRequest,
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> PeerComparisonResponse:
    return await _run_peer_comparison(body, user, db)


# ── Technical analysis (compat) ───────────────────────────────────────────────

@router.post(
    "/market",
    response_model=TechnicalAnalysisResponse,
    summary="技术面分析（兼容旧路由）",
    description=(
        "与 POST /analysis/technical 完全等价，保留此路由仅为向后兼容。\n\n"
        "**推荐使用 POST /analysis/technical。**"
    ),
    deprecated=True,
)
async def market_analysis_compat(
    body: TechnicalAnalysisRequest,
    user: User = Depends(get_current_user),
) -> TechnicalAnalysisResponse:
    return await _run_technical_analysis(body, user)


# ── Comprehensive analysis ────────────────────────────────────────────────────

class ComprehensiveAnalysisRequest(BaseModel):
    market: str
    symbol: str

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _SUPPORTED_MARKETS:
            raise ValueError(f"market 只支持 CN 或 HK，收到 '{v}'")
        return upper

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("symbol 不能为空")
        return v


class AgentStatus(BaseModel):
    status:  str
    message: str | None = None


class ComprehensiveMetadata(BaseModel):
    generated_at: str
    agents:       dict[str, AgentStatus]
    warnings:     list[str]


class ComprehensiveAnalysisResponse(BaseModel):
    market:      str
    symbol:      str
    stock_name:  str = ""    # P6-b: 股票中文名，找不到时为空字符串
    report:      str
    sections:    dict[str, str]
    metadata:    ComprehensiveMetadata


@router.post(
    "/comprehensive",
    response_model=ComprehensiveAnalysisResponse,
    summary="综合分析（技术面 + 基本面 + 同行对比）",
    description=(
        "并行调用 TechnicalAnalystAgent、FundamentalAnalystAgent、"
        "PeerComparisonAnalystAgent（Phase 1E：动态同行）、NewsAnalystAgent，"
        "最终由 LLM 生成综合分析 Markdown 报告。\n\n"
        "- 同行来源优先级：PEER_MAP 手动配置 > CN 行业 Hot Score 热门股\n"
        "- 任一子模块失败 → sections 中写入错误说明，综合报告注明该维度暂缺\n"
        "- 子报告传入综合 LLM 前截断至各 4000 字符，sections 返回完整原文\n"
        "- LLM 未配置 → HTTP 503\n"
        "- 需要 Bearer token 鉴权"
    ),
)
async def comprehensive_analysis(
    body: ComprehensiveAnalysisRequest,
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> ComprehensiveAnalysisResponse:
    try:
        llm = get_llm_client()
    except ValueError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    coordinator = ComprehensiveAnalysisCoordinator(llm)

    try:
        result = await coordinator.analyze_async(db, body.market, body.symbol)
    except Exception as exc:
        log.error(
            "ComprehensiveAnalysis unexpected error [%s/%s]: %s",
            body.market, body.symbol, exc,
        )
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    return ComprehensiveAnalysisResponse(**result)


# ── Comprehensive-v2 (analysis_scope) ────────────────────────────────────────

class ComprehensiveV2Request(BaseModel):
    market:          str
    symbol:          str
    analysis_scope:  str = "comprehensive"
    output_language: str = "zh-CN"
    engine: Optional[Literal["custom_coordinator", "langgraph"]] = None

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _SUPPORTED_MARKETS:
            raise ValueError(f"market 只支持 CN 或 HK，收到 '{v}'")
        return upper

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("symbol 不能为空")
        return v

    @field_validator("analysis_scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        if v not in VALID_SCOPES:
            raise ValueError(
                f"analysis_scope '{v}' 不支持。可选值：{sorted(VALID_SCOPES)}"
            )
        return v

    @field_validator("output_language")
    @classmethod
    def validate_output_language(cls, v: str) -> str:
        if v not in VALID_OUTPUT_LANGUAGES:
            raise ValueError(
                f"output_language '{v}' 不支持。可选值：{sorted(VALID_OUTPUT_LANGUAGES)}"
            )
        return v


class ComprehensiveV2Metadata(BaseModel):
    generated_at:    str
    agents:          dict[str, AgentStatus]
    warnings:        list[str]
    analysis_scope:  str
    workflow_engine: str
    output_language: str = "zh-CN"


class ComprehensiveV2Response(BaseModel):
    market:          str
    symbol:          str
    stock_name:      str = ""
    report:          str
    sections:        dict[str, str]
    metadata:        ComprehensiveV2Metadata
    analysis_scope:  str
    output_language: str = "zh-CN"


@router.post(
    "/comprehensive-v2",
    response_model=ComprehensiveV2Response,
    summary="综合分析 v2（支持 analysis_scope + engine 灰度）",
    description=(
        "支持 analysis_scope 条件执行 Agent，供前端新版分析模式选择使用。\n\n"
        "**analysis_scope 可选值：**\n"
        "- `comprehensive`：技术面 + 基本面 + 同行对比 + 新闻面（默认）\n"
        "- `technical_only`：仅技术面\n"
        "- `fundamental_only`：仅基本面\n"
        "- `peer_only`：仅同行对比\n"
        "- `news_only`：仅新闻面\n"
        "- `technical_fundamental`：技术面 + 基本面\n\n"
        "**engine 可选值：**\n"
        "- `custom_coordinator`：当前默认引擎，行为与旧版一致\n"
        "- `langgraph`：LangGraph 灰度引擎（M4-b.4），仅供实验/验证\n\n"
        "前端默认不传 engine，继续走 custom_coordinator，行为不变。\n"
        "旧接口 POST /analysis/comprehensive 保持不变。\n"
        "需要 Bearer token 鉴权。"
    ),
)
async def comprehensive_analysis_v2(
    body: ComprehensiveV2Request,
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> ComprehensiveV2Response:
    try:
        llm = get_llm_client()
    except ValueError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    engine = _resolve_analysis_engine(body.engine)

    if engine == "langgraph":
        # ── LangGraph 灰度路径 ────────────────────────────────────────────────
        runner = LangGraphAnalysisRunner(llm)
        try:
            result = await runner.analyze(
                db, body.market, body.symbol, body.analysis_scope,
                output_language=body.output_language,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        except Exception as exc:
            log.error(
                "LangGraphAnalysis unexpected error [%s/%s] scope=%s: %s",
                body.market, body.symbol, body.analysis_scope, exc,
            )
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    else:
        # ── custom_coordinator 默认路径（行为与 M4-a 完全一致）────────────────
        coordinator = ComprehensiveAnalysisCoordinator(llm)
        try:
            result = await coordinator.analyze_scoped(
                db, body.market, body.symbol, body.analysis_scope,
                output_language=body.output_language,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        except Exception as exc:
            log.error(
                "ComprehensiveAnalysisV2 unexpected error [%s/%s] scope=%s: %s",
                body.market, body.symbol, body.analysis_scope, exc,
            )
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    return ComprehensiveV2Response(**result)


# ── SSE Analysis Runs (M25-a) ─────────────────────────────────────────────────

class AnalysisRunRequest(BaseModel):
    market:          str
    symbol:          str
    analysis_scope:  str = "comprehensive"
    output_language: str = "zh-CN"
    engine:          Optional[Literal["custom_coordinator", "langgraph"]] = None

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _SUPPORTED_MARKETS:
            raise ValueError(f"market 只支持 CN 或 HK，收到 '{v}'")
        return upper

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("symbol 不能为空")
        return v

    @field_validator("analysis_scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        if v not in VALID_SCOPES:
            raise ValueError(
                f"analysis_scope '{v}' 不支持。可选值：{sorted(VALID_SCOPES)}"
            )
        return v

    @field_validator("output_language")
    @classmethod
    def validate_output_language(cls, v: str) -> str:
        if v not in VALID_OUTPUT_LANGUAGES:
            raise ValueError(
                f"output_language '{v}' 不支持。可选值：{sorted(VALID_OUTPUT_LANGUAGES)}"
            )
        return v


class AnalysisRunResponse(BaseModel):
    run_id:          str
    status:          str
    market:          str
    symbol:          str
    analysis_scope:  str
    workflow_engine: str
    created_at:      str


@router.post(
    "/runs",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建分析运行（SSE 实时进度）",
    description=(
        "创建一个后台分析任务，通过 GET /analysis/runs/{id}/events SSE 流接收进度事件。\n\n"
        "**engine 可选值：**\n"
        "- `custom_coordinator`（默认）：现有稳定 SSE 路径\n"
        "- `langgraph`：LangGraph 灰度 SSE 路径（M25-c），仅供开发者模式使用\n\n"
        "需要 Bearer token 鉴权。"
    ),
)
async def create_analysis_run(
    body: AnalysisRunRequest,
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> AnalysisRunResponse:
    try:
        llm = get_llm_client()
    except ValueError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    engine   = _resolve_analysis_engine(body.engine)
    registry = _safe_get_registry()

    run_ref = await registry.create_run(
        user_id         = str(user.id),
        market          = body.market,
        symbol          = body.symbol,
        analysis_scope  = body.analysis_scope,
        workflow_engine = engine,
        output_language = body.output_language,
    )

    if engine == "langgraph":
        runner: RealtimeAnalysisRunner | LangGraphRealtimeRunnerSSE = LangGraphRealtimeRunnerSSE(llm)
    else:
        runner = RealtimeAnalysisRunner(llm)

    # Start background task; opens its own DB session
    async def _background() -> None:
        async with AsyncSessionLocal() as bg_db:
            await runner.run_analysis(run_ref, registry, bg_db)

    asyncio.create_task(_background(), name=f"analysis_run_{run_ref.run_id}")

    return AnalysisRunResponse(
        run_id          = run_ref.run_id,
        status          = "queued",
        market          = run_ref.market,
        symbol          = run_ref.symbol,
        analysis_scope  = run_ref.analysis_scope,
        workflow_engine = run_ref.workflow_engine,
        created_at      = run_ref.created_at.isoformat(),
    )


@router.get(
    "/runs/{run_id}/events",
    summary="SSE 实时分析进度事件流（M25-b：支持 after_event_id 断线重连）",
    description=(
        "text/event-stream 格式的 SSE 事件流。\n\n"
        "每个事件格式：`event: <type>\\nid: <event_id>\\ndata: <json>\\n\\n`\n"
        "心跳保活：`: heartbeat\\n\\n`（每 15 秒）\n\n"
        "**断线重连**：携带 `?after_event_id=N` 可 replay 错过的事件（N 为最后收到的 event_id）。\n\n"
        "需要 Bearer token 鉴权。"
    ),
)
async def analysis_run_events(
    run_id:        str,
    request:       Request,
    user:          User             = Depends(get_current_user),
    after_event_id: Optional[int]  = Query(default=None,
                                           description="断线重连：replay event_id > N 的历史事件"),
) -> StreamingResponse:
    registry = _safe_get_registry()
    snap     = await registry.get_run_snapshot(run_id)
    # Return 404 for both "not found" and "wrong user" (anti-enumeration)
    if snap is None or snap.user_id != str(user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"run '{run_id}' not found")

    _TERMINAL_EVENTS = frozenset({"report_ready", "analysis_failed", "cancelled"})
    heartbeat_interval = 15

    async def event_generator() -> AsyncGenerator[str, None]:
        sent_event_ids: set = set()

        # ── Phase 1: replay historical events ────────────────────────────────
        past_events = await registry.get_events_after(run_id, after_event_id)
        for past_event in past_events:
            eid = past_event.get("event_id")
            yield _format_sse(past_event)
            if eid is not None:
                sent_event_ids.add(eid)

        # If terminal after replay, close immediately
        snap_now = await registry.get_run_snapshot(run_id)
        if snap_now is not None and snap_now.is_terminal():
            yield ": stream-end\n\n"
            return

        # ── Phases 2+3: drain then live stream ────────────────────────────────
        # Use asyncio.shield() so heartbeat timeouts do NOT cancel the async
        # generator. Without shield, wait_for cancels __anext__(), which triggers
        # the generator's finally-block cleanup (B1 bug: stream ends after first
        # heartbeat when analysis takes > heartbeat_interval seconds).
        sub_gen = registry.subscribe_events(run_id)
        pending_task: Optional[asyncio.Task] = None
        try:
            while True:
                if await request.is_disconnected():
                    log.info("SSE client disconnected for run %s", run_id)
                    break

                if pending_task is None or pending_task.done():
                    pending_task = asyncio.create_task(sub_gen.__anext__())

                try:
                    event = await asyncio.wait_for(
                        asyncio.shield(pending_task), timeout=heartbeat_interval
                    )
                    pending_task = None  # consumed — create new task next iteration
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                except StopAsyncIteration:
                    break

                if event is None:
                    yield ": stream-end\n\n"
                    break

                eid = event.get("event_id")
                if eid in sent_event_ids:
                    continue
                yield _format_sse(event)
                if eid is not None:
                    sent_event_ids.add(eid)

                if event.get("event") in _TERMINAL_EVENTS:
                    yield ": stream-end\n\n"
                    break
        finally:
            if pending_task and not pending_task.done():
                pending_task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


def _format_sse(event: dict) -> str:
    """Format a stamped event dict as SSE wire format using its event_id as the SSE id."""
    event_type = event.get("event", "message")
    event_id   = event.get("event_id", "")
    data_str   = json.dumps(event, ensure_ascii=False)
    return f"event: {event_type}\nid: {event_id}\ndata: {data_str}\n\n"


@router.get(
    "/runs/{run_id}",
    summary="查询分析运行状态（M25-b：含 progress / latest_event）",
    description=(
        "返回运行状态快照。\n\n"
        "新增字段：`progress`（0-100）、`latest_event`（最新事件）。\n\n"
        "需要 Bearer token 鉴权。"
    ),
)
async def get_analysis_run(
    run_id: str,
    user:   User = Depends(get_current_user),
) -> dict:
    registry = _safe_get_registry()
    snap     = await registry.get_run_snapshot(run_id)
    if snap is None or snap.user_id != str(user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"run '{run_id}' not found")

    return {
        "run_id":          snap.run_id,
        "status":          snap.status,
        "market":          snap.market,
        "symbol":          snap.symbol,
        "analysis_scope":  snap.analysis_scope,
        "workflow_engine": snap.workflow_engine,
        "progress":        snap.progress,
        "latest_event":    snap.latest_event,
        "result":          snap.result,
        "error":           snap.error,
        "created_at":      snap.created_at.isoformat(),
        "updated_at":      snap.updated_at.isoformat(),
        "finished_at":     snap.finished_at.isoformat() if snap.finished_at else None,
    }


@router.post(
    "/runs/{run_id}/cancel",
    summary="取消分析运行（M25-b：明确返回 cancelled bool）",
    description=(
        "将运行状态标记为 cancelled，并推送 cancelled 事件（含 event_id）。\n\n"
        "- 已 completed/failed 的 run：返回 `cancelled: false`，不报错。\n"
        "- 运行中/排队中的 run：设为 cancelled，返回 `cancelled: true`。\n\n"
        "注意：asyncio.to_thread 线程不可强制中断；cancel 仅表示'停止等待'。\n\n"
        "需要 Bearer token 鉴权。"
    ),
)
async def cancel_analysis_run(
    run_id: str,
    user:   User = Depends(get_current_user),
) -> dict:
    registry = _safe_get_registry()
    snap     = await registry.get_run_snapshot(run_id)
    if snap is None or snap.user_id != str(user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"run '{run_id}' not found")

    if snap.is_terminal():
        return {
            "cancelled": False,
            "status":    snap.status,
            "message":   "Run already finished",
        }

    # request_cancel: sets status + pushes stamped cancelled event + pushes sentinel
    await registry.request_cancel(run_id)

    return {"cancelled": True, "status": "cancelled", "message": "ok"}


# ── News analysis ─────────────────────────────────────────────────────────────

class NewsAnalysisRequest(BaseModel):
    market:     str
    symbol:     str
    hours_back: int = 72
    limit:      int = 20

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _SUPPORTED_MARKETS:
            raise ValueError(f"market 只支持 CN 或 HK，收到 '{v}'")
        return upper

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("symbol 不能为空")
        return v

    @field_validator("hours_back")
    @classmethod
    def validate_hours_back(cls, v: int) -> int:
        if not (1 <= v <= 720):
            raise ValueError("hours_back 须在 1-720 之间")
        return v

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if not (1 <= v <= 50):
            raise ValueError("limit 须在 1-50 之间")
        return v


class NewsAnalysisResponse(BaseModel):
    market: str
    symbol: str
    report: str


@router.post(
    "/news",
    response_model=NewsAnalysisResponse,
    summary="新闻面分析",
    description=(
        "基于东方财富个股新闻生成 Markdown 新闻面分析报告。\n\n"
        "- 内部调用 NewsDataService 获取新闻快照（含 TTL 缓存）\n"
        "- 最多分析近 10 条新闻，时间窗口由 `hours_back` 控制\n"
        "- 新闻为空时返回'暂无相关新闻数据'报告，不返回 5xx\n"
        "- HK 新闻通过关键词搜索获取，报告中会注明相关性限制\n"
        "- LLM 未配置 → HTTP 503\n"
        "- 需要 Bearer token 鉴权"
    ),
)
async def news_analysis(
    body: NewsAnalysisRequest,
    user: User = Depends(get_current_user),
) -> NewsAnalysisResponse:
    try:
        llm = get_llm_client()
    except ValueError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    agent = NewsAnalystAgent(llm)

    try:
        report = await asyncio.to_thread(
            agent.analyze, body.market, body.symbol, body.hours_back, body.limit
        )
    except Exception as exc:
        log.error(
            "NewsAnalystAgent unexpected error [%s/%s]: %s",
            body.market, body.symbol, exc,
        )
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    return NewsAnalysisResponse(
        market=body.market,
        symbol=body.symbol,
        report=report,
    )
