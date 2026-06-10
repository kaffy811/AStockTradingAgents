"""
IndustryClassificationService
==============================
申万一级行业分类查询服务。

依赖 industry_master 和 stock_industry_map 两张静态表，由
scripts/import_industry_map.py 从 CSV 导入。

股票搜索（search_stocks）优先使用 stock_master 表；若该表为空（迁移期间）
则自动 fallback 到 stock_industry_map。

所有方法接收 AsyncSession 作为第一参数，与 FastAPI Depends(get_db) 配合使用。
"""

from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.industry import IndustryMaster, StockIndustryMap
from app.models.stock_master import StockMaster


class IndustryClassificationService:

    async def get_stock_industry(
        self,
        db: AsyncSession,
        market: str,
        symbol: str,
    ) -> dict | None:
        """
        查询单只股票的主行业分类。

        参数：
            market  大写市场代码，如 "CN"
            symbol  带前导零的股票代码，如 "000001"

        返回：
            dict(market, symbol, stock_name, industry_code, industry_name,
                 industry_level, source, is_primary)
            找不到返回 None，不抛异常。
        """
        market = market.upper()
        symbol = symbol.strip().zfill(len(symbol.strip()))  # 保留已有前导零；不补位

        stmt = (
            select(StockIndustryMap)
            .where(
                StockIndustryMap.market  == market,
                StockIndustryMap.symbol  == symbol,
                StockIndustryMap.is_primary.is_(True),
            )
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return {
            "market":         row.market,
            "symbol":         row.symbol,
            "stock_name":     row.stock_name,
            "industry_code":  row.industry_code,
            "industry_name":  row.industry_name,
            "industry_level": row.industry_level,
            "source":         row.source,
            "is_primary":     row.is_primary,
        }

    async def get_industry_constituents(
        self,
        db: AsyncSession,
        market: str,
        industry_code: str,
        limit: int = 1000,
    ) -> list[dict]:
        """
        查询某行业的所有成分股。

        返回：
            list of dict(market, symbol, stock_name, industry_code, industry_name)
            找不到返回 []，不抛异常。
        """
        market = market.upper()

        stmt = (
            select(StockIndustryMap)
            .where(
                StockIndustryMap.market        == market,
                StockIndustryMap.industry_code == industry_code,
            )
            .order_by(StockIndustryMap.symbol)
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "market":        r.market,
                "symbol":        r.symbol,
                "stock_name":    r.stock_name,
                "industry_code": r.industry_code,
                "industry_name": r.industry_name,
            }
            for r in rows
        ]

    async def search_stocks(
        self,
        db: AsyncSession,
        market: str,
        q: str,
        limit: int = 10,
    ) -> list[dict]:
        """
        按股票代码前缀或名称关键词搜索。

        优先查 stock_master（已导入时）；stock_master 为空时 fallback 到
        stock_industry_map（迁移期间保证零停机）。

        返回：
            list of dict(market, symbol, name, industry_code, industry_name, source)
            按 symbol 升序。
        """
        q = q.strip()
        if not q:
            return []
        market = market.upper()

        # Decide which path to take based on whether stock_master has data.
        master_count: int = await db.scalar(
            select(func.count()).select_from(StockMaster).where(
                StockMaster.market == market
            )
        ) or 0

        if master_count > 0:
            return await self._search_stocks_from_master(db, market, q, limit)
        return await self._search_stocks_from_industry_map(db, market, q, limit)

    # ── private: HK symbol filter ─────────────────────────────────────────────

    @staticmethod
    def _build_symbol_filter(market: str, q: str):
        """
        Build the WHERE clause filter for stock_master symbol/name search.

        CN: symbol ILIKE 'q%' OR name ILIKE '%q%'
        HK: also try zero-padded variant so '700' matches '00700',
            and pure-name queries ('腾讯') skip the numeric padding.
        """
        if market == "HK" and q.isdigit():
            # Numeric query: try both raw and 5-digit zero-padded forms
            padded = q.lstrip("0").zfill(5)   # 700 → 00700
            return or_(
                StockMaster.symbol.ilike(f"{q}%"),
                StockMaster.symbol.ilike(f"{padded}%"),
                StockMaster.name.ilike(f"%{q}%"),
            )
        # Default (CN + HK name/symbol queries)
        return or_(
            StockMaster.symbol.ilike(f"{q}%"),
            StockMaster.name.ilike(f"%{q}%"),
        )

    # ── private: search via stock_master (primary path) ──────────────────────

    async def _search_stocks_from_master(
        self,
        db: AsyncSession,
        market: str,
        q: str,
        limit: int,
    ) -> list[dict]:
        """
        Query stock_master for matching stocks, then LEFT JOIN stock_industry_map
        to populate industry_code / industry_name.
        HK numeric queries (700, 00700) are matched via zero-padded expansion.
        HK industry_code/industry_name will be None (no HK data in stock_industry_map).
        """
        # Step 1: find matching master rows
        master_stmt = (
            select(StockMaster)
            .where(
                StockMaster.market == market,
                StockMaster.status == "active",
                self._build_symbol_filter(market, q),
            )
            .order_by(StockMaster.symbol)
            .limit(limit)
        )
        master_rows = (await db.execute(master_stmt)).scalars().all()

        if not master_rows:
            return []

        symbols = [r.symbol for r in master_rows]

        # Step 2: fetch industry info for matched symbols in one query
        industry_stmt = (
            select(StockIndustryMap)
            .where(
                StockIndustryMap.market == market,
                StockIndustryMap.symbol.in_(symbols),
                StockIndustryMap.is_primary.is_(True),
            )
            .order_by(StockIndustryMap.symbol, StockIndustryMap.industry_code)
        )
        industry_rows = (await db.execute(industry_stmt)).scalars().all()

        # Build symbol → (industry_code, industry_name) map; keep first per symbol
        industry_map: dict[str, tuple[str | None, str | None]] = {}
        for ir in industry_rows:
            if ir.symbol not in industry_map:
                industry_map[ir.symbol] = (ir.industry_code, ir.industry_name)

        # Step 3: assemble results; dedup by symbol (master guarantees unique,
        # but guard against any future edge cases)
        seen: set[str] = set()
        result: list[dict] = []
        for mr in master_rows:
            if mr.symbol in seen:
                continue
            seen.add(mr.symbol)
            ind_code, ind_name = industry_map.get(mr.symbol, (None, None))
            result.append({
                "market":        mr.market,
                "symbol":        mr.symbol,
                "name":          mr.name,
                "industry_code": ind_code,
                "industry_name": ind_name,
                "source":        "stock_master",
            })
        return result

    # ── private: fallback path (stock_industry_map) ───────────────────────────

    async def _search_stocks_from_industry_map(
        self,
        db: AsyncSession,
        market: str,
        q: str,
        limit: int,
    ) -> list[dict]:
        """
        Original search logic via stock_industry_map.
        Used when stock_master is empty (e.g. during initial migration).
        """
        fetch_limit = limit * 4
        stmt = (
            select(StockIndustryMap)
            .where(
                StockIndustryMap.market == market,
                StockIndustryMap.is_primary.is_(True),
                or_(
                    StockIndustryMap.symbol.ilike(f"{q}%"),
                    and_(
                        StockIndustryMap.stock_name.is_not(None),
                        StockIndustryMap.stock_name.ilike(f"%{q}%"),
                    ),
                ),
            )
            .order_by(StockIndustryMap.symbol, StockIndustryMap.industry_code)
            .limit(fetch_limit)
        )
        rows = (await db.execute(stmt)).scalars().all()

        seen: set[str] = set()
        result: list[dict] = []
        for r in rows:
            if r.symbol in seen:
                continue
            seen.add(r.symbol)
            result.append({
                "market":        r.market,
                "symbol":        r.symbol,
                "name":          r.stock_name,
                "industry_code": r.industry_code,
                "industry_name": r.industry_name,
                "source":        "stock_industry_map",
            })
            if len(result) == limit:
                break
        return result

    async def list_industries(
        self,
        db: AsyncSession,
        market: str = "CN",
    ) -> list[dict]:
        """
        查询某市场下所有已录入的行业。

        返回：
            list of dict(market, industry_code, industry_name, industry_level, source)
            按 industry_code 升序。
        """
        market = market.upper()

        stmt = (
            select(IndustryMaster)
            .where(IndustryMaster.market == market)
            .order_by(IndustryMaster.industry_code)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "market":         r.market,
                "industry_code":  r.industry_code,
                "industry_name":  r.industry_name,
                "industry_level": r.industry_level,
                "source":         r.source,
            }
            for r in rows
        ]


# 模块级单例
industry_classification_service = IndustryClassificationService()
