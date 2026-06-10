"""
IndustryHotStockService
========================
行业热门股 Top-N 快照查询服务。

读取 industry_hot_stock_snapshot 表；写入由
scripts/refresh_industry_hot_stocks.py 负责。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.industry_hot_stock import IndustryHotStockSnapshot


class IndustryHotStockService:

    async def get_latest_hot_stocks(
        self,
        db:            AsyncSession,
        market:        str,
        industry_code: str,
        limit:         int = 5,
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
            return {
                "market":        market,
                "industry_code": industry_code,
                "industry_name": None,
                "trade_date":    None,
                "score_version": "v1",
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

        return {
            "market":        market,
            "industry_code": industry_code,
            "industry_name": industry_name,
            "trade_date":    latest_date,
            "score_version": score_version,
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
