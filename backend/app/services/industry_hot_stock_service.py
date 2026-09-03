"""
IndustryHotStockService
========================
行业热门股 Top-N 快照查询服务。

读取 industry_hot_stock_snapshot 表；写入由
scripts/refresh_industry_hot_stocks.py 负责。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.industry import StockIndustryMap
from app.models.industry_hot_stock import IndustryHotStockSnapshot
from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service

log = logging.getLogger(__name__)


class IndustryHotStockService:

    async def get_latest_hot_stocks(
        self,
        db:            AsyncSession,
        market:        str,
        industry_code: str,
        limit:         int = 20,
    ) -> dict:
        cache_key = company_v2_snapshot_cache_service.make_company_key(
            "industry_hot",
            market.upper(),
            industry_code,
            f"limit:{limit}",
            version="v2",
        )
        cached, swr_status, _cache_status = await company_v2_snapshot_cache_service.get_swr(cache_key)
        if swr_status in {"fresh", "stale"} and isinstance(cached, dict):
            out = dict(cached)
            out["cache_status"] = swr_status
            if swr_status == "stale":
                token = await company_v2_snapshot_cache_service.acquire_refresh_lock(cache_key, ttl=15)
                if token:
                    asyncio.create_task(self._refresh_latest_hot_stocks_cache(cache_key, token, market, industry_code, limit))
            return out
        token = await company_v2_snapshot_cache_service.acquire_refresh_lock(cache_key, ttl=15)
        if not token and isinstance(cached, dict):
            out = dict(cached)
            out["cache_status"] = "stale"
            return out
        try:
            result = await self._get_latest_hot_stocks_uncached(db, market, industry_code, limit)
            ttl = 5 * 60 if result.get("items") else 60
            await company_v2_snapshot_cache_service.set_swr(cache_key, result, fresh_ttl=ttl, stale_ttl=5 * 60)
            result["cache_status"] = "miss"
            return result
        except Exception as exc:
            if isinstance(cached, dict):
                out = dict(cached)
                out["cache_status"] = "stale"
                return out
            log.warning("industry hot cache miss query failed [%s/%s]: %s", market, industry_code, exc)
            return {
                "market": market.upper(),
                "industry_code": industry_code,
                "industry_name": None,
                "trade_date": None,
                "score_version": "v1",
                "total": 0,
                "items": [],
                "data_quality": {"message": "Industry hot data temporarily unavailable"},
            }
        finally:
            await company_v2_snapshot_cache_service.release_refresh_lock(cache_key, token)

    async def _refresh_latest_hot_stocks_cache(
        self,
        cache_key: str,
        token: str,
        market: str,
        industry_code: str,
        limit: int,
    ) -> None:
        from app.core.database import get_db

        try:
            async for db in get_db():
                result = await self._get_latest_hot_stocks_uncached(db, market, industry_code, limit)
                ttl = 5 * 60 if result.get("items") else 60
                await company_v2_snapshot_cache_service.set_swr(cache_key, result, fresh_ttl=ttl, stale_ttl=5 * 60)
                break
        except Exception as exc:
            log.debug("industry hot stale refresh failed [%s/%s]: %s", market, industry_code, exc)
        finally:
            await company_v2_snapshot_cache_service.release_refresh_lock(cache_key, token)

    async def _get_latest_hot_stocks_uncached(
        self,
        db:            AsyncSession,
        market:        str,
        industry_code: str,
        limit:         int = 20,
    ) -> dict:
        """
        返回该行业最新 trade_date 的 Top-limit 热门股。

        无快照时返回 items=[]，HTTP 200，data_quality.message 说明原因。
        """
        market = market.upper()

        # ── 找最新 trade_date ─────────────────────────────────────────────────
        date_stmt = (
            select(func.max(IndustryHotStockSnapshot.trade_date))
            .where(
                IndustryHotStockSnapshot.market        == market,
                IndustryHotStockSnapshot.industry_code == industry_code,
            )
        )
        latest_date: date | None = (await db.execute(date_stmt)).scalar_one_or_none()

        if latest_date is None:
            # 仍返回 total（行业成分股数量）即使没有快照
            total_stmt = (
                select(func.count(func.distinct(StockIndustryMap.symbol)))
                .where(
                    StockIndustryMap.market        == market,
                    StockIndustryMap.industry_code == industry_code,
                )
            )
            total: int = (await db.execute(total_stmt)).scalar_one() or 0
            return {
                "market":        market,
                "industry_code": industry_code,
                "industry_name": None,
                "trade_date":    None,
                "score_version": "v1",
                "total":         total,
                "items":         [],
                "data_quality":  {"message": "No hot stock snapshot available"},
            }

        # ── 取 Top-limit 记录 ─────────────────────────────────────────────────
        stmt = (
            select(IndustryHotStockSnapshot)
            .where(
                IndustryHotStockSnapshot.market        == market,
                IndustryHotStockSnapshot.industry_code == industry_code,
                IndustryHotStockSnapshot.trade_date    == latest_date,
                IndustryHotStockSnapshot.rank          <= limit,
            )
            .order_by(IndustryHotStockSnapshot.rank)
        )
        rows = (await db.execute(stmt)).scalars().all()

        if not rows:
            return {
                "market":        market,
                "industry_code": industry_code,
                "industry_name": None,
                "trade_date":    latest_date,
                "score_version": "v1",
                "total":         0,
                "items":         [],
                "data_quality":  {"message": "Snapshot found but no items returned"},
            }

        industry_name  = rows[0].industry_name
        score_version  = rows[0].score_version

        items = [
            {
                "rank":            r.rank,
                "symbol":          r.symbol,
                "stock_name":      r.stock_name,
                "hot_score":       r.hot_score,
                "amount":          r.amount,
                "change_pct":      r.change_pct,
                "amount_norm":     r.amount_norm,
                "change_abs_norm": r.change_abs_norm,
                "data_source":     r.data_source,
                "score_factors":   r.score_factors,
            }
            for r in rows
        ]

        # 查询行业在 stock_industry_map 中的真实成分股总数
        total_stmt = (
            select(func.count(func.distinct(StockIndustryMap.symbol)))
            .where(
                StockIndustryMap.market        == market,
                StockIndustryMap.industry_code == industry_code,
            )
        )
        total: int = (await db.execute(total_stmt)).scalar_one() or 0

        return {
            "market":        market,
            "industry_code": industry_code,
            "industry_name": industry_name,
            "trade_date":    latest_date,
            "score_version": score_version,
            "total":         total,
            "items":         items,
            "data_quality":  {"message": None},
        }


    async def get_industry_hot_summary(
        self,
        db:     AsyncSession,
        market: str,
    ) -> dict[str, dict]:
        """
        基于 industry_hot_stock_snapshot 聚合该市场最新 trade_date 下各行业热度摘要。

        返回 dict keyed by industry_code，每个 value 包含：
            hot_score / stock_count / up_count / down_count /
            avg_change_pct / amount / trade_date / score_version / data_quality

        无任何 snapshot 时返回 {}。
        """
        market = market.upper()

        # ── 找该市场跨所有行业的最新 trade_date ──────────────────────────────
        latest_date_subq = (
            select(func.max(IndustryHotStockSnapshot.trade_date))
            .where(IndustryHotStockSnapshot.market == market)
            .scalar_subquery()
        )

        # ── 按 industry_code 聚合 ─────────────────────────────────────────────
        stmt = (
            select(
                IndustryHotStockSnapshot.industry_code,
                func.avg(IndustryHotStockSnapshot.hot_score).label("hot_score"),
                func.count(
                    func.distinct(IndustryHotStockSnapshot.symbol)
                ).label("stock_count"),
                func.sum(
                    case((IndustryHotStockSnapshot.change_pct > 0, 1), else_=0)
                ).label("up_count"),
                func.sum(
                    case((IndustryHotStockSnapshot.change_pct < 0, 1), else_=0)
                ).label("down_count"),
                func.avg(IndustryHotStockSnapshot.change_pct).label("avg_change_pct"),
                func.sum(IndustryHotStockSnapshot.amount).label("amount"),
                func.max(IndustryHotStockSnapshot.trade_date).label("trade_date"),
                func.max(IndustryHotStockSnapshot.score_version).label("score_version"),
            )
            .where(
                IndustryHotStockSnapshot.market        == market,
                IndustryHotStockSnapshot.trade_date    == latest_date_subq,
            )
            .group_by(IndustryHotStockSnapshot.industry_code)
        )

        rows = (await db.execute(stmt)).all()

        result: dict[str, dict] = {}
        for row in rows:
            result[row.industry_code] = {
                "hot_score":      round(float(row.hot_score), 4) if row.hot_score is not None else None,
                "stock_count":    int(row.stock_count)    if row.stock_count    is not None else 0,
                "up_count":       int(row.up_count)       if row.up_count       is not None else 0,
                "down_count":     int(row.down_count)     if row.down_count     is not None else 0,
                "avg_change_pct": round(float(row.avg_change_pct), 4) if row.avg_change_pct is not None else None,
                "amount":         float(row.amount)       if row.amount         is not None else None,
                "trade_date":     row.trade_date.isoformat() if row.trade_date  is not None else None,
                "score_version":  row.score_version,
                "data_quality": {
                    "status":  "success",
                    "message": "基于最新行业热门股快照聚合",
                },
            }
        return result


# 模块级单例
industry_hot_stock_service = IndustryHotStockService()
