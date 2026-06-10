"""
Watchlist Router — 自选股 CRUD。

路由：
  POST   /watchlist/          添加自选股（重复返回 409）
  GET    /watchlist/          查询当前用户自选股列表
  PATCH  /watchlist/{id}      修改 name / note / sort_order
  DELETE /watchlist/{id}      删除自选股

所有接口均需要 Bearer token 鉴权。
user_id 严格从 JWT 读取，不接受请求体传入。
不属于当前用户的 item_id 一律返回 404。
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.analysis_report import AnalysisReport
from app.models.industry import StockIndustryMap
from app.models.user import User
from app.models.watchlist_item import (
    WatchlistItem,
    WatchlistAddRequest,
    WatchlistLatestReport,
    WatchlistPatchRequest,
    WatchlistItemResponse,
    WatchlistListResponse,
    WatchlistEnrichedItemResponse,
    WatchlistEnrichedListResponse,
)
from app.services.stock_data_service import StockDataService

_stock_data_svc = StockDataService()

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("/enriched", response_model=WatchlistEnrichedListResponse)
async def get_watchlist_enriched(
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> WatchlistEnrichedListResponse:
    """
    查询当前用户自选股列表，并补充行情 / 行业 / 最近报告。

    - industry:  批量 DB 查询（单次，无 N+1）
    - quote:     asyncio.gather + asyncio.to_thread 并发获取
    - 任何 quote 失败：quote_status="failed"，latest_price/change_pct=null
    """
    # ── Step 1: Load watchlist items ──────────────────────────────────────────
    count_stmt = (
        select(func.count())
        .select_from(WatchlistItem)
        .where(WatchlistItem.user_id == user.id)
    )
    total: int = (await db.execute(count_stmt)).scalar_one()

    if total == 0:
        return WatchlistEnrichedListResponse(total=0, items=[])

    list_stmt = (
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user.id)
        .order_by(WatchlistItem.sort_order.asc(), WatchlistItem.created_at.desc())
    )
    wl_rows = (await db.execute(list_stmt)).scalars().all()

    # ── Step 2: Latest reports (lightweight, same as list endpoint) ───────────
    rn_subq = (
        select(
            AnalysisReport.id,
            AnalysisReport.market,
            AnalysisReport.symbol,
            AnalysisReport.report_type,
            AnalysisReport.warnings,
            AnalysisReport.agents,
            AnalysisReport.created_at,
            func.row_number().over(
                partition_by=[AnalysisReport.market, AnalysisReport.symbol],
                order_by=AnalysisReport.created_at.desc(),
            ).label("rn"),
        )
        .where(AnalysisReport.user_id == user.id)
        .subquery()
    )
    latest_rows = (await db.execute(select(rn_subq).where(rn_subq.c.rn == 1))).mappings().all()
    latest_map: dict[tuple[str, str], WatchlistLatestReport] = {
        (row["market"], row["symbol"]): WatchlistLatestReport(
            id          = row["id"],
            created_at  = row["created_at"],
            report_type = row["report_type"],
            warnings    = row["warnings"] or [],
            agents      = row["agents"]   or {},
        )
        for row in latest_rows
    }

    # ── Step 3: Batch industry lookup — one DB query, no N+1 ─────────────────
    cn_symbols = [row.symbol for row in wl_rows if row.market == "CN"]
    industry_map: dict[str, dict] = {}
    if cn_symbols:
        ind_stmt = (
            select(
                StockIndustryMap.symbol,
                StockIndustryMap.industry_code,
                StockIndustryMap.industry_name,
            )
            .where(
                StockIndustryMap.market == "CN",
                StockIndustryMap.symbol.in_(cn_symbols),
                StockIndustryMap.is_primary.is_(True),
            )
        )
        ind_rows = (await db.execute(ind_stmt)).mappings().all()
        industry_map = {row["symbol"]: dict(row) for row in ind_rows}

    # ── Step 4: Parallel quote fetches ────────────────────────────────────────
    async def _fetch_quote(mkt: str, sym: str) -> dict:
        try:
            result = await asyncio.to_thread(_stock_data_svc.get_quote, mkt, sym)
            if result.http_status == 200 and result.data:
                d = result.data
                return {
                    "latest_price": d.get("price"),
                    "change_pct":   d.get("change_pct"),
                    "quote_status": "ok",
                    "quote_message": None,
                }
        except Exception:
            pass
        return {
            "latest_price": None,
            "change_pct":   None,
            "quote_status": "failed",
            "quote_message": None,
        }

    quote_results = await asyncio.gather(
        *[_fetch_quote(row.market, row.symbol) for row in wl_rows]
    )

    # ── Step 5: Combine ───────────────────────────────────────────────────────
    items: list[WatchlistEnrichedItemResponse] = []
    for row, qdata in zip(wl_rows, quote_results):
        ind = industry_map.get(row.symbol, {}) if row.market == "CN" else {}
        items.append(WatchlistEnrichedItemResponse(
            id            = row.id,
            market        = row.market,
            symbol        = row.symbol,
            name          = row.name,
            note          = row.note,
            sort_order    = row.sort_order,
            created_at    = row.created_at,
            updated_at    = row.updated_at,
            latest_price  = qdata["latest_price"],
            change_pct    = qdata["change_pct"],
            industry_code = ind.get("industry_code"),
            industry_name = ind.get("industry_name"),
            quote_status  = qdata["quote_status"],
            quote_message = qdata["quote_message"],
            latest_report = latest_map.get((row.market, row.symbol)),
        ))

    return WatchlistEnrichedListResponse(total=total, items=items)


@router.post("/", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_watchlist_item(
    body: WatchlistAddRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistItemResponse:
    """添加自选股。user_id 从 JWT 读取；同用户 market+symbol 重复时返回 409。"""
    # 检查是否已存在
    stmt = select(WatchlistItem).where(
        WatchlistItem.user_id == user.id,
        WatchlistItem.market  == body.market,
        WatchlistItem.symbol  == body.symbol,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Watchlist item already exists",
        )

    item = WatchlistItem(
        user_id    = user.id,
        market     = body.market,
        symbol     = body.symbol,
        name       = body.name,
        note       = body.note,
        sort_order = body.sort_order,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return WatchlistItemResponse.model_validate(item)


@router.get("/", response_model=WatchlistListResponse)
async def list_watchlist_items(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistListResponse:
    """查询当前用户自选股列表，按 sort_order ASC, created_at DESC 排序。
    每条记录附带该股票最近一次保存报告的轻量摘要（latest_report），
    不含 report_md / sections / report_metadata 大字段。
    使用两次查询 + Python join 避免 N+1。
    """
    # ── Query 1: count ────────────────────────────────────────────────────────
    count_stmt = (
        select(func.count())
        .select_from(WatchlistItem)
        .where(WatchlistItem.user_id == user.id)
    )
    total: int = (await db.execute(count_stmt)).scalar_one()

    if total == 0:
        return WatchlistListResponse(total=0, items=[])

    # ── Query 1 (cont): watchlist items ───────────────────────────────────────
    list_stmt = (
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user.id)
        .order_by(WatchlistItem.sort_order.asc(), WatchlistItem.created_at.desc())
    )
    wl_rows = (await db.execute(list_stmt)).scalars().all()

    # ── Query 2: latest report per (market, symbol) — ROW_NUMBER window ───────
    # Only select lightweight columns; never select(AnalysisReport) to avoid
    # pulling report_md (TEXT) and sections (JSONB) large fields.
    rn_subq = (
        select(
            AnalysisReport.id,
            AnalysisReport.market,
            AnalysisReport.symbol,
            AnalysisReport.report_type,
            AnalysisReport.warnings,
            AnalysisReport.agents,
            AnalysisReport.created_at,
            func.row_number().over(
                partition_by=[AnalysisReport.market, AnalysisReport.symbol],
                order_by=AnalysisReport.created_at.desc(),
            ).label("rn"),
        )
        .where(AnalysisReport.user_id == user.id)  # strict: never cross users
        .subquery()
    )
    latest_stmt = select(rn_subq).where(rn_subq.c.rn == 1)
    latest_rows = (await db.execute(latest_stmt)).mappings().all()

    # Build (market, symbol) → WatchlistLatestReport lookup dict
    latest_map: dict[tuple[str, str], WatchlistLatestReport] = {
        (row["market"], row["symbol"]): WatchlistLatestReport(
            id          = row["id"],
            created_at  = row["created_at"],
            report_type = row["report_type"],
            warnings    = row["warnings"] or [],
            agents      = row["agents"]   or {},
        )
        for row in latest_rows
    }

    # ── Python join: attach latest_report to each watchlist item ─────────────
    items = [
        WatchlistItemResponse(
            id            = row.id,
            market        = row.market,
            symbol        = row.symbol,
            name          = row.name,
            note          = row.note,
            sort_order    = row.sort_order,
            created_at    = row.created_at,
            latest_report = latest_map.get((row.market, row.symbol)),
        )
        for row in wl_rows
    ]

    return WatchlistListResponse(total=total, items=items)


@router.patch("/{item_id}", response_model=WatchlistItemResponse)
async def patch_watchlist_item(
    item_id: uuid.UUID,
    body: WatchlistPatchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistItemResponse:
    """修改自选股的 name / note / sort_order。不属于当前用户返回 404。"""
    stmt = select(WatchlistItem).where(
        WatchlistItem.id      == item_id,
        WatchlistItem.user_id == user.id,
    )
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")

    if body.name is not None:
        item.name = body.name
    if body.note is not None:
        item.note = body.note or None   # "" → null (clear note)
    if body.sort_order is not None:
        item.sort_order = body.sort_order

    await db.commit()
    await db.refresh(item)
    return WatchlistItemResponse.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist_item(
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """删除自选股。不属于当前用户返回 404。成功返回 204 No Content。"""
    stmt = select(WatchlistItem).where(
        WatchlistItem.id      == item_id,
        WatchlistItem.user_id == user.id,
    )
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")

    await db.delete(item)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
