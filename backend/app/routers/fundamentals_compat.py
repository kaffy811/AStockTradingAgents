"""
app/routers/fundamentals_compat.py — 兼容路由（Phase 1.5）

提供更短更易用的路径别名，内部委托给主路由逻辑。

新增端点（3 个）：
  GET /api/v1/modules
      → 全局模块目录（不依赖 market/symbol）

  GET /api/v1/stock/{code}/overview
      → 首屏快照（兼容 600519、600519.SH、000001.SZ 格式）

  GET /api/v1/stock/{code}/modules/{module_id}
      → 单模块数据（兼容旧版 module_id 别名）

代码格式解析规则：
  600519        → CN, 600519
  600519.SH     → CN, 600519
  000001.SZ     → CN, 000001
  688981.SH     → CN, 688981
  838030.BJ     → CN, 838030
  00700.HK      → HK, 00700
  700.HK        → HK, 00700
  AAPL          → US, AAPL

module_id 别名映射：
  cashflow      → cashflow_quality
  quote         → snapshot
  其他保持不变
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.aggregator.envelope import build_api_response
from app.aggregator.fundamentals_aggregator import get_aggregator
from app.core.database import get_db
from app.datasource.tushare_client import _to_ts_code
from app.tools.fundamental import MODULE_CATALOG, MODULE_NAME_MAP, TOOL_REGISTRY

log = logging.getLogger(__name__)


# ── Phase 6N-8B helpers for diagnostics endpoint ─────────────────────────────

def _get_cache_status() -> str:
    """Return current Redis circuit-breaker status: 'ok' or 'unavailable'."""
    try:
        from app.services.cache_service import cache_status
        return cache_status()
    except Exception:
        return "unknown"


def _get_provider_status(module_results: list[dict]) -> str:
    """Infer overall provider status from module probe results."""
    ok_count = sum(1 for m in module_results if m.get("status") == "ok")
    fail_count = sum(1 for m in module_results if m.get("status") == "failed")
    if ok_count == 0 and fail_count > 0:
        return "unavailable"
    if fail_count > 0:
        return "partial"
    return "ok"


# Per-module fallback chains (what sources are tried in order)
_MODULE_FALLBACK_CHAINS: dict[str, list[str]] = {
    "quote_snapshot": ["cache", "eastmoney", "sina", "akshare_spot", "baostock_kline"],
    "growth":         ["free_fundamental_cache", "baostock_financial", "akshare_income_statement", "pdf_metrics"],
    "profitability":  ["free_fundamental_cache", "baostock_financial", "akshare_indicators", "pdf_metrics"],
    "cashflow_quality": ["free_fundamental_cache", "baostock_financial", "akshare_cashflow", "pdf_metrics"],
    "solvency":       ["free_fundamental_cache", "baostock_financial", "akshare_indicators", "akshare_balance_sheet"],
    "operation_capability": ["free_fundamental_cache", "baostock_financial", "akshare_indicators"],
    "dupont":         ["free_fundamental_cache", "baostock_financial", "akshare_indicators"],
    "valuation":      ["baostock_kline", "akshare_quote"],
    "asset_structure": ["free_fundamental_cache", "baostock_financial", "akshare_balance_sheet"],
    "major_holders":  ["free_fundamental_cache", "akshare_holders"],
    "equity_structure": ["free_fundamental_cache", "akshare_equity"],
    "main_business":  ["akshare_main_business"],
    "industry_rank":  ["db_etl_snapshot"],
    "dividend_history": ["akshare_dividend"],
    "financial_summary": ["baostock_financial", "akshare_indicators"],
}

_MODULE_CORE_FIELDS: dict[str, list[str]] = {
    "growth":           ["revenue_yoy", "net_profit_yoy", "revenue_abs", "net_profit_parent"],
    "profitability":    ["roe", "gross_margin", "net_margin"],
    "cashflow_quality": ["ocf_to_np", "operating_cashflow"],
    "solvency":         ["current_ratio", "quick_ratio", "debt_ratio"],
    "operation_capability": ["asset_turnover", "inventory_turnover"],
    "dupont":           ["roe", "net_margin", "asset_turnover"],
    "valuation":        ["pe_ttm", "pb", "ps_ttm"],
}


def _build_fill_chains(module_results: list[dict], market: str) -> list[dict]:
    """
    Build per-module fill chain diagnostic entries (Phase 6N-8B).
    """
    out = []
    for m in module_results:
        key = m.get("module_key", "")
        status = m.get("status", "failed")
        chain = _MODULE_FALLBACK_CHAINS.get(key, [])
        core = _MODULE_CORE_FIELDS.get(key, [])
        non_null = m.get("non_null_fields", [])
        filled = [f for f in core if f in non_null]
        missing = [f for f in core if f not in non_null]
        renderable_before = status in ("ok",) and m.get("rows_count", 0) > 0
        renderable_after = renderable_before or bool(filled)
        out.append({
            "module_key":           key,
            "renderable_before_fill": renderable_before,
            "fallback_chain":       chain,
            "filled_fields":        filled,
            "still_missing_fields": missing,
            "renderable_after_fill": renderable_after,
            "hidden_reason":        None if renderable_after else "ALL_NULL_ROWS",
            "provider_success":     m.get("provider_success"),
            "inferred":             m.get("inferred", False),
        })
    return out

compat_router = APIRouter(
    prefix="/api/v1",
    tags=["fundamentals-compat"],
)

_DISCLAIMER_HEADER = "For informational purposes only. Not investment advice. Invest at your own risk."

# 模块元数据快速查找（module_key → MODULE_CATALOG 条目）
_MODULE_META: dict[str, dict] = {
    m["key"]: m for m in MODULE_CATALOG if m.get("display") and m.get("status") != "hidden"
}

# module_id 别名（旧 key → 新 key）
_MODULE_ALIAS: dict[str, str] = {
    "cashflow":           "cashflow_quality",
    "quote":              "snapshot",
    "quote_snapshot":     "snapshot",
    "cashflow_health":    "cashflow_quality",
    "growth_metrics":     "growth",
    "profit_quality":     "profitability",
    "operating_efficiency": "operation_capability",
    "industry_ranking":   "industry_rank",
    "peer_rank":          "industry_rank",
    "industry_position":  "industry_rank",
    # Phase 2C aliases
    "dividend":           "dividend_history",
    "holders":            "major_holders",
    "shareholders":       "major_holders",
    "events":             "announcements",
    "forecast_rating":    "analyst_ratings",
    "rating":             "analyst_ratings",
}


def _disclaimer_response(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        content=data,
        status_code=status_code,
        headers={"X-Data-Disclaimer": _DISCLAIMER_HEADER},
    )


def _parse_code(code: str) -> tuple[str, str]:
    """
    解析股票代码字符串，返回 (market, symbol)。

    支持：
      "600519"      → ("CN", "600519")
      "600519.SH"   → ("CN", "600519")
      "000001.SZ"   → ("CN", "000001")
      "838030.BJ"   → ("CN", "838030")
      "00700.HK"    → ("HK", "00700")
      "700.HK"      → ("HK", "00700")
      "AAPL"        → ("US", "AAPL")
    """
    code = code.strip()

    if "." in code:
        parts = code.rsplit(".", 1)
        symbol_part = parts[0]
        suffix = parts[1].upper()

        if suffix in ("SH", "SZ", "BJ"):
            return "CN", symbol_part
        elif suffix == "HK":
            # 港股：确保 5 位数字补零
            digits = symbol_part.lstrip("0") or "0"
            return "HK", digits.zfill(5)
        else:
            return "US", symbol_part
    else:
        # 无后缀 — 按长度和内容猜测
        if code.isdigit():
            if len(code) == 6:
                return "CN", code
            elif len(code) <= 5:
                # 港股（短数字代码）
                return "HK", code.zfill(5)
        # 字母 ticker → 美股
        return "US", code


def _resolve_module_id(module_id: str) -> str:
    """将 module_id（可能是旧别名）映射为规范的 module_key。"""
    return _MODULE_ALIAS.get(module_id, module_id)


def _module_name(module_key: str) -> str:
    return MODULE_NAME_MAP.get(module_key, module_key)


# ── 端点 A：全局模块目录 ──────────────────────────────────────────────────────

@compat_router.get(
    "/modules",
    summary="全局模块目录（32+1，无需 market/symbol）",
    response_description="所有基本面模块元数据列表，含 render_type / field_labels / unit_hints 等渲染契约字段",
)
async def get_global_module_catalog() -> JSONResponse:
    """
    返回全部 32+1 个基本面模块的声明（与 /stocks/{market}/{symbol}/fundamentals/modules 等价）。

    无需提供 market/symbol，适合前端初始化模块导航栏。

    status 取值：available / legacy / planned
    每个条目包含 Phase 2D 新增渲染契约字段：render_type, chart_type, field_labels,
    unit_hints, description, data_freshness, disclaimer_type 等。
    """
    aggregator = get_aggregator()
    modules = aggregator.list_modules()
    return _disclaimer_response(modules)


# ── 端点 B：首屏快照（code 格式）─────────────────────────────────────────────

@compat_router.get(
    "/stock/{code}/overview",
    summary="首屏快照（兼容 600519 / 600519.SH / 000001.SZ）",
    response_description="snapshot + financial_summary 两模块的 DataEnvelope，含 group/group_seq/meta 渲染字段",
)
async def get_stock_overview(
    code: str = Path(..., description="股票代码，支持 600519 / 600519.SH / 000001.SZ / 00700.HK / AAPL"),
) -> JSONResponse:
    """
    首屏快照的短路径版本，内部等同于：
      GET /api/v1/stocks/{market}/{symbol}/fundamentals/snapshot

    支持代码格式：
    - `600519` （A 股，自动判断交易所）
    - `600519.SH` / `000001.SZ`（带后缀）
    - `00700.HK` / `700.HK`（港股，自动补零）
    - `AAPL` （美股 ticker）

    返回的每个模块 envelope 包含 Phase 2D 新增字段：
    group, group_seq, meta（含 render_type / field_labels / unit_hints）
    """
    market, symbol = _parse_code(code)
    ts_code = _to_ts_code(market, symbol)
    aggregator = get_aggregator()
    snapshot = await aggregator.fetch_snapshot(market=market, symbol=symbol)

    response: dict[str, Any] = {}
    for key, envelope in snapshot.items():
        module_meta = _MODULE_META.get(key)
        response[key] = build_api_response(
            envelope, market=market, symbol=symbol, ts_code=ts_code,
            module_key=key, module_name=_module_name(key),
            module_meta=module_meta,
        )

    return _disclaimer_response(response)


# ── 端点 D：Free Mode 模块诊断 ──────────────────────────────────────────────

# 诊断探针的 module key 列表（不含 report_documents，由 DB 单独处理）
_DIAG_MODULE_KEYS: list[str] = [
    "quote_snapshot",
    "valuation",
    "financial_summary",
    "growth",
    "profitability",
    "expense_analysis",
    "cashflow_quality",
    "asset_structure",
    "solvency",
    "capital_occupation",
    "operation_capability",
    "dupont",
    "main_business",
    "dividend_history",
    "industry_rank",
    "major_holders",
    "equity_structure",
]

# BaoStock-backed modules: these require 5–75s per call due to the global asyncio Lock.
# In free mode, we infer availability from config rather than live-probing each one.
_BAOSTOCK_MODULE_KEYS: frozenset[str] = frozenset([
    "growth",
    "profitability",
    "cashflow_quality",
    "solvency",
    "operation_capability",
    "dupont",
])

# 所有 section IDs（按页面顺序，用于 unavailable_sections 排序）
_ALL_SECTION_IDS: list[str] = [
    "overview",
    "highlight-risk",
    "ai-analysis",
    "report-documents",
    "valuation",
    "dividend",
    "main-business",
    "industry",
    "growth",
    "profitability",
    "earnings-quality",
    "asset-structure",
    "solvency",
    "capital",
    "operations",
    "dupont",
    "shareholders",
]


def _count_rows(data: dict) -> int:
    """从 module data dict 中推断行数。支持 rows/series/periods/records/rankings 等字段。"""
    if not isinstance(data, dict):
        return 0
    for field in ("rows", "series", "periods", "records", "rankings",
                  "top10_float_holders", "holder_num_series"):
        val = data.get(field)
        if isinstance(val, list) and val:
            return len(val)
    # 计算顶层非 None 的数值字段
    count = 0
    for v in data.values():
        if v is not None and isinstance(v, (int, float)):
            count += 1
    return count


@compat_router.get(
    "/stock/{code}/fundamentals/diagnostics",
    summary="Free Mode 模块数据诊断（不调用付费 Tushare）",
)
async def get_module_diagnostics(
    code: str = Path(..., description="股票代码"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    诊断当前 Free Mode 下每个模块的数据可用性。
    - 不调用 Tushare（DATA_MODE=free 已自动跳过）
    - 每个模块 5 秒 timeout
    - 并发执行所有模块
    - 不抛 500，所有错误以 failed 状态返回
    - 不泄露 secret/local_path
    """
    from app.services.free_mode_visibility_service import (
        compute_section_visibility,
        get_unavailable_sections,
    )

    market, symbol = _parse_code(code)
    ts_code = _to_ts_code(market, symbol)
    aggregator = get_aggregator()

    async def _probe_module(module_key: str) -> dict:
        t0 = time.time()
        try:
            envelope = await asyncio.wait_for(
                aggregator.fetch_module(market, symbol, module_key),
                timeout=5.0,
            )
            latency_ms = round((time.time() - t0) * 1000)
            ok = getattr(envelope, "ok", envelope.get("ok", False)) if hasattr(envelope, "get") else False
            partial = getattr(envelope, "partial", envelope.get("partial", False)) if hasattr(envelope, "get") else False
            data = getattr(envelope, "data", envelope.get("data", {})) if hasattr(envelope, "get") else {}
            if data is None:
                data = {}
            rows_count = _count_rows(data) if isinstance(data, dict) else 0

            non_null_fields = [k for k, v in data.items() if v is not None][:10] if isinstance(data, dict) else []

            if not ok:
                status = "failed"
            elif partial:
                status = "partial"
            elif rows_count > 0:
                status = "ok"
            else:
                status = "empty"

            provider_success = data.get("source") if isinstance(data, dict) else None

            return {
                "module_key":       module_key,
                "status":           status,
                "rows_count":       rows_count,
                "non_null_fields":  non_null_fields,
                "latency_ms":       latency_ms,
                "provider_success": provider_success,
            }
        except asyncio.TimeoutError:
            return {
                "module_key":       module_key,
                "status":           "failed",
                "rows_count":       0,
                "non_null_fields":  [],
                "latency_ms":       5000,
                "provider_success": None,
                "error":            "timeout",
            }
        except Exception as exc:
            return {
                "module_key":       module_key,
                "status":           "failed",
                "rows_count":       0,
                "non_null_fields":  [],
                "latency_ms":       round((time.time() - t0) * 1000),
                "provider_success": None,
                "error":            type(exc).__name__,
            }

    # Free mode + CN: BaoStock 模块用配置推断，跳过 5–75s 的实时探针
    # （BaoStock 全局 asyncio.Lock 导致并发探针全部超时）
    from app.core.config import settings as _settings
    _data_mode = getattr(_settings, "data_mode", "free")
    _enable_baostock = getattr(_settings, "enable_baostock", True)
    _use_bs_inference = (_data_mode == "free" and market == "CN" and _enable_baostock)

    def _inferred_baostock(module_key: str) -> dict:
        """Config-based inference: BaoStock available → module has data."""
        return {
            "module_key":       module_key,
            "status":           "ok",
            "rows_count":       1,  # inferred; actual count loaded on demand
            "non_null_fields":  [],
            "latency_ms":       0,
            "provider_success": "baostock",
            "inferred":         True,
        }

    # 并发探针非 BaoStock 模块；BaoStock 模块在 free+CN 下直接推断
    probe_keys = [mk for mk in _DIAG_MODULE_KEYS if not (_use_bs_inference and mk in _BAOSTOCK_MODULE_KEYS)]
    tasks = [_probe_module(mk) for mk in probe_keys]
    probed_results: list[dict] = list(await asyncio.gather(*tasks))

    module_results: list[dict] = []
    probed_iter = iter(probed_results)
    for mk in _DIAG_MODULE_KEYS:
        if _use_bs_inference and mk in _BAOSTOCK_MODULE_KEYS:
            module_results.append(_inferred_baostock(mk))
        else:
            module_results.append(next(probed_iter))

    # 单独探针 report_documents + RAG 状态（DB 查询）
    rd_count    = 0
    rc_count    = 0   # report_chunks
    emb_count   = 0   # chunks with non-null embedding
    rd_status   = "failed"
    rag_status  = "unknown"
    t0 = time.time()
    try:
        from sqlalchemy import text

        rd_count = (await db.execute(
            text("SELECT COUNT(*) FROM report_documents WHERE ts_code = :ts_code"),
            {"ts_code": ts_code},
        )).scalar() or 0

        rc_count = (await db.execute(
            text("SELECT COUNT(*) FROM report_chunks WHERE ts_code = :ts_code"),
            {"ts_code": ts_code},
        )).scalar() or 0

        emb_count = (await db.execute(
            text("SELECT COUNT(*) FROM report_chunks WHERE ts_code = :ts_code AND embedding IS NOT NULL"),
            {"ts_code": ts_code},
        )).scalar() or 0

        rd_status  = "ok" if rd_count > 0 else "empty"
        # RAG ready = has chunks with embeddings
        if rc_count > 0 and emb_count > 0:
            rag_status = "ready"
        elif rd_count > 0:
            rag_status = "not_indexed"   # docs exist but no chunks/embeddings yet
        else:
            rag_status = "empty"
    except Exception as _exc:
        rd_status  = "failed"
        rag_status = "unknown"
        rd_count = rc_count = emb_count = 0

    module_results.append({
        "module_key":       "report_documents",
        "status":           rd_status,
        "rows_count":       rd_count,
        "non_null_fields":  [],
        "latency_ms":       round((time.time() - t0) * 1000),
        "provider_success": "db" if rd_status != "failed" else None,
        "rag": {
            "status":          rag_status,
            "documents_count": rd_count,
            "chunks_count":    rc_count,
            "embedding_count": emb_count,
        },
    })

    # 计算可见性
    visibility = compute_section_visibility(module_results)
    unavailable = get_unavailable_sections(visibility, _ALL_SECTION_IDS)

    # 汇总统计
    summary = {"ok": 0, "partial": 0, "empty": 0, "failed": 0}
    for m in module_results:
        s = m.get("status", "failed")
        if s in summary:
            summary[s] += 1

    return _disclaimer_response({
        "market":               market,
        "symbol":               symbol,
        "ts_code":              ts_code,
        "data_mode":            _data_mode,
        "modules":              module_results,
        "visibility":           visibility,
        "unavailable_sections": unavailable,
        "summary":              summary,
        "rag_status":           rag_status,   # top-level convenience field
        # Phase 6N-8B: cache + fill chain diagnostics
        "cache_status":         _get_cache_status(),
        "auth_status":          "ok",  # if this endpoint is reachable, auth passed
        "provider_status":      _get_provider_status(module_results),
        "pdf_status":           rd_status,
        "module_fill_chains":   _build_fill_chains(module_results, market),
    })


# ── 端点 C：单模块（code 格式）───────────────────────────────────────────────

@compat_router.get(
    "/stock/{code}/modules/{module_id}",
    summary="单模块数据（短路径，支持旧版 module_id）",
    response_description="单模块 DataEnvelope，含 group/group_seq/meta 渲染契约字段",
)
async def get_stock_module_compat(
    code: str = Path(..., description="股票代码，支持多种格式"),
    module_id: str = Path(..., description="模块 key 或别名（cashflow → cashflow_quality）"),
    mode: str = Query("summary", description="AI 分析模式：summary / full（仅 ai_analysis 模块使用）"),
    force_refresh: bool = Query(False, description="强制刷新，绕过 AI 分析缓存（仅 ai_analysis 模块使用）"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    单模块按需加载的短路径版本。

    module_id 别名映射：
    - `cashflow` → `cashflow_quality`
    - `quote` → `snapshot`
    - 其他保持不变

    返回标准 DataEnvelope（同主路由），Phase 2D 新增：
    group, group_seq, meta（含 render_type / field_labels / unit_hints）
    """
    market, symbol = _parse_code(code)
    module_key = _resolve_module_id(module_id)
    ts_code = _to_ts_code(market, symbol)

    # Special case: ai_analysis uses the AI Orchestrator
    if module_key == "ai_analysis":
        from app.agent.fundamental_ai_orchestrator import get_ai_orchestrator
        orchestrator = get_ai_orchestrator()
        # Orchestrator returns a fully-formed API response dict (not a DataEnvelope)
        response = await orchestrator.run(market, symbol, mode=mode, force_refresh=force_refresh, db=db)
        return _disclaimer_response(response)

    # Special case: report_documents has a dedicated handler in fundamentals.py
    if module_key == "report_documents":
        from app.routers.fundamentals import get_report_documents
        return await get_report_documents(market=market, symbol=symbol, db=db)

    aggregator = get_aggregator()
    envelope = await aggregator.fetch_module(
        market=market,
        symbol=symbol,
        module_key=module_key,
    )

    module_meta = _MODULE_META.get(module_key)
    response = build_api_response(
        envelope, market=market, symbol=symbol, ts_code=ts_code,
        module_key=module_key, module_name=_module_name(module_key),
        module_meta=module_meta,
    )
    # Always return HTTP 200; errors are communicated via partial=true / errors[]
    # so the frontend can render a graceful empty state for each module independently.
    return _disclaimer_response(response, status_code=200)
