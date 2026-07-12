"""
app/routers/fundamentals.py — Stock Fundamental Service API 路由（Phase 1.5）

原有路由（保留，全部兼容）：
  GET /api/v1/stocks/{market}/{symbol}/fundamentals/snapshot
  GET /api/v1/stocks/{market}/{symbol}/fundamentals/modules/{module_key}
  GET /api/v1/stocks/{market}/{symbol}/fundamentals/modules

响应格式：build_api_response() 统一 JSON 结构（见 aggregator/envelope.py）
响应头：X-Data-Disclaimer: 本页面数据仅供参考，不构成投资建议。
市场代码：CN / HK / US
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.aggregator.envelope import build_api_response, ok_envelope, err_envelope
from app.aggregator.fundamentals_aggregator import get_aggregator
from app.core.database import get_db
from app.datasource.tushare_client import _to_ts_code
from app.tools.fundamental import MODULE_NAME_MAP

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/stocks",
    tags=["fundamentals"],
)

_DISCLAIMER_HEADER = "For informational purposes only. Not investment advice. Invest at your own risk."
_VALID_MARKETS = {"CN", "HK", "US"}


def _disclaimer_response(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        content=data,
        status_code=status_code,
        headers={"X-Data-Disclaimer": _DISCLAIMER_HEADER},
    )


def _validate_market(market: str) -> str:
    m = market.upper()
    if m not in _VALID_MARKETS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的市场代码 '{market}'，合法值: CN / HK / US",
        )
    return m


def _module_name(module_key: str) -> str:
    return MODULE_NAME_MAP.get(module_key, module_key)


# ── 端点 1：首屏快照 ──────────────────────────────────────────────────────────

@router.get(
    "/{market}/{symbol}/fundamentals/snapshot",
    summary="首屏基本面快照（行情 + 财务摘要，并发）",
)
async def get_fundamentals_snapshot(
    market: str = Path(..., description="市场代码：CN / HK / US"),
    symbol: str = Path(..., description="股票代码，如 600519"),
) -> JSONResponse:
    """
    并发拉取 snapshot（行情）+ financial_summary（财务摘要）。

    返回 {module_key: APIEnvelope} 字典。
    """
    market = _validate_market(market)
    ts_code = _to_ts_code(market, symbol)
    aggregator = get_aggregator()
    snapshot = await aggregator.fetch_snapshot(market=market, symbol=symbol)

    response: dict[str, Any] = {}
    for key, envelope in snapshot.items():
        response[key] = build_api_response(
            envelope, market=market, symbol=symbol, ts_code=ts_code,
            module_key=key, module_name=_module_name(key),
        )

    return _disclaimer_response(response)


# ── 端点 2：单模块数据 ────────────────────────────────────────────────────────

@router.get(
    "/{market}/{symbol}/fundamentals/modules/{module_key}",
    summary="单模块基本面数据（带缓存）",
)
async def get_fundamentals_module(
    market: str = Path(..., description="市场代码：CN / HK / US"),
    symbol: str = Path(..., description="股票代码"),
    module_key: str = Path(..., description="模块 key，如 valuation / dupont / cashflow_quality"),
) -> JSONResponse:
    """
    按需拉取单个模块数据，返回标准 APIEnvelope。

    ```json
    {
      "market": "CN", "symbol": "600519", "ts_code": "600519.SH",
      "module_key": "valuation", "module_name": "估值分位",
      "data": { ... },
      "errors": [],
      "partial": false,
      "stale": false,
      "generated_at": "2026-07-05T10:23:45+08:00",
      "source": { "primary": "tushare", "fallback": null, "akshare_enabled": false, "actual": "tushare" }
    }
    ```
    """
    market = _validate_market(market)
    ts_code = _to_ts_code(market, symbol)
    aggregator = get_aggregator()
    envelope = await aggregator.fetch_module(market=market, symbol=symbol, module_key=module_key)

    response = build_api_response(
        envelope, market=market, symbol=symbol, ts_code=ts_code,
        module_key=module_key, module_name=_module_name(module_key),
    )
    # Always HTTP 200 — errors surface via partial=True + errors[] in the envelope.
    # Returning 503 on every missing token floods the browser console and breaks
    # the frontend graceful-degradation path (DataSourceBanner).
    return _disclaimer_response(response, status_code=200)


# ── 端点 3：模块声明列表 ──────────────────────────────────────────────────────

@router.get(
    "/{market}/{symbol}/fundamentals/modules",
    summary="全模块声明列表（23+1，含 status/seq/name_en）",
)
async def list_fundamentals_modules(
    market: str = Path(..., description="市场代码：CN / HK / US"),
    symbol: str = Path(..., description="股票代码"),
) -> JSONResponse:
    """
    返回 23+1 模块的 metadata。

    status 取值：available / legacy / planned
    - available: Phase 1.5 主力模块（推荐使用）
    - legacy:    Phase 1 原始模块（可调用，已有 Phase 1.5 替代版本）
    - planned:   尚未实现，将在后续 Phase 支持
    """
    _validate_market(market)
    aggregator = get_aggregator()
    modules = aggregator.list_modules()
    return _disclaimer_response(modules)


# ── 端点 4：年报文件索引（Phase 6A）─────────────────────────────────────────

@router.get(
    "/{market}/{symbol}/fundamentals/modules/report_documents",
    summary="上市公司年报/半年报文件索引（Phase 6A）",
)
async def get_report_documents(
    market: str = Path(..., description="市场代码：CN / HK / US"),
    symbol: str = Path(..., description="股票代码"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    查询 report_documents 表中该股票的历史年报/半年报索引。

    - 需要 ENABLE_REPORT_PDF=true 且已运行 PDF 采集任务后才有数据。
    - 未开启时返回 partial=True + 提示信息，不报错。
    """
    from app.core.config import settings

    market = _validate_market(market)
    ts_code = _to_ts_code(market, symbol)

    if not settings.enable_report_pdf:
        envelope = err_envelope(
            "ENABLE_REPORT_PDF 未开启，年报文件功能未激活。"
            "请设置环境变量 ENABLE_REPORT_PDF=true 并运行 PDF 采集任务。"
        )
        response = build_api_response(
            envelope, market=market, symbol=symbol, ts_code=ts_code,
            module_key="report_documents", module_name="年报文件",
        )
        return _disclaimer_response(response)

    try:
        from app.models.report_document import ReportDocument
        stmt = (
            select(ReportDocument)
            .where(ReportDocument.ts_code == ts_code)
            .order_by(ReportDocument.period_end.desc())
        )
        result = await db.execute(stmt)
        docs = result.scalars().all()
        rows = [
            {
                "id":               d.id,
                "ts_code":          d.ts_code,
                "report_type":      d.report_type,
                "period_end":       d.period_end,
                "title":            d.title,
                "source_url":       d.source_url,
                "file_sha256":      d.file_sha256,
                "text_excerpt":     d.text_excerpt,
                "disclosure_date":  d.disclosure_date,
                "parsed":           d.parsed,
                "created_at":       d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
        envelope = ok_envelope({"ts_code": ts_code, "rows": rows, "source": "db"})
    except Exception as e:
        log.warning("report_documents 查询失败 [%s]: %s", ts_code, e)
        envelope = err_envelope(f"年报文件查询失败: {e}")

    response = build_api_response(
        envelope, market=market, symbol=symbol, ts_code=ts_code,
        module_key="report_documents", module_name="年报文件",
    )
    return _disclaimer_response(response)
