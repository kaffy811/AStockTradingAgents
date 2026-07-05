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

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import JSONResponse

from app.aggregator.envelope import build_api_response
from app.aggregator.fundamentals_aggregator import get_aggregator
from app.datasource.tushare_client import _to_ts_code
from app.tools.fundamental import MODULE_CATALOG, MODULE_NAME_MAP, TOOL_REGISTRY

log = logging.getLogger(__name__)

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


# ── 端点 C：单模块（code 格式）───────────────────────────────────────────────

@compat_router.get(
    "/stock/{code}/modules/{module_id}",
    summary="单模块数据（短路径，支持旧版 module_id）",
    response_description="单模块 DataEnvelope，含 group/group_seq/meta 渲染契约字段",
)
async def get_stock_module_compat(
    code: str = Path(..., description="股票代码，支持多种格式"),
    module_id: str = Path(..., description="模块 key 或别名（cashflow → cashflow_quality）"),
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
    status = 200 if envelope["ok"] else 503
    return _disclaimer_response(response, status_code=status)
