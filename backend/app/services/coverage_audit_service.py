"""
app/services/coverage_audit_service.py — 数据完整性 Coverage Audit（Phase 6N-6/7）

职责：
  - 对给定股票池，从现有 ETL 表、BaoStock 补充数据、RAG 状态中汇总字段完整率；
  - 生成 CoverageReport：各分类完整率 + 缺失字段列表 + reason_code 汇总；
  - 将结果写入 data_coverage_snapshot 表（可用于历史趋势对比）；
  - 对缺失字段生成 missing_field_queue 条目（供后台 backfill 消费）。

数据源优先级：
  1. etl_daily_basic / etl_fina_indicator（Tushare ETL，需付费权限）
  2. BaoStock 免费 API（query_profit_data / query_balance_data / kline）
  3. 报告缺失字段时附带 reason_code（PERMISSION_DENIED / PROVIDER_EMPTY 等）

设计约定：
  - DB 不可用时安全降级：coverage = 0%，reason_code = CACHE_UNAVAILABLE；
  - Tushare 权限不足时 reason_code = PERMISSION_DENIED；
  - 所有 DB / BaoStock 操作均为 async。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core_schema import CORE_FIELDS, FIELD_CATEGORIES, FieldSpec
from app.models.data_field import DataField, DataFieldStatus, ReasonCode

log = logging.getLogger(__name__)

# ── Coverage Report 数据结构 ─────────────────────────────────────────────────

class CategoryCoverage:
    """单分类的字段完整率摘要。"""
    def __init__(
        self, category: str, total: int, ok: int, fields: list[dict],
        extra: dict | None = None,
    ) -> None:
        self.category    = category
        self.total       = total
        self.ok          = ok
        self.completeness = round(ok / total, 4) if total > 0 else 0.0
        self.fields      = fields  # [{field_name, status, reason_code}]
        self.extra       = extra or {}  # e.g. p0/p1 split, rag status detail

    def to_dict(self) -> dict:
        d = {
            "category":      self.category,
            "total_fields":  self.total,
            "ok_fields":     self.ok,
            "completeness":  self.completeness,
            "fields":        self.fields,
        }
        d.update(self.extra)
        return d


class CoverageReport:
    """单只股票的完整 coverage report。"""

    def __init__(
        self,
        ts_code:          str,
        trade_date:       str,
        categories:       dict[str, CategoryCoverage],
        rag_status:       str = "unknown",
        generated_at:     str = "",
    ) -> None:
        self.ts_code      = ts_code
        self.trade_date   = trade_date
        self.categories   = categories
        self.rag_status   = rag_status
        self.generated_at = generated_at or datetime.utcnow().isoformat()

        # Overall completeness (all categories)
        total = sum(c.total for c in categories.values())
        ok    = sum(c.ok    for c in categories.values())
        self.overall_completeness = round(ok / total, 4) if total > 0 else 0.0

        # Overall completeness excluding RAG category
        # (RAG "empty" counts fields as 0/4 but skews the financial picture)
        non_rag_cats = {k: v for k, v in categories.items() if k != "rag"}
        total_nr = sum(c.total for c in non_rag_cats.values())
        ok_nr    = sum(c.ok    for c in non_rag_cats.values())
        self.overall_without_rag = round(ok_nr / total_nr, 4) if total_nr > 0 else 0.0

        # Missing fields across all categories
        self.missing_fields: list[dict] = [
            f for cat in categories.values() for f in cat.fields
            if f.get("status") not in ("ok", "computed", "estimated")
        ]

    def to_dict(self) -> dict:
        cats = {k: v.to_dict() for k, v in self.categories.items()}
        return {
            "ts_code":              self.ts_code,
            "trade_date":           self.trade_date,
            "generated_at":         self.generated_at,
            "overall_completeness": self.overall_completeness,
            "overall_without_rag":  self.overall_without_rag,
            "rag_status":           self.rag_status,
            "quote_completeness":      cats.get("quote",      {}).get("completeness", 0.0),
            "valuation_completeness":  cats.get("valuation",  {}).get("completeness", 0.0),
            "valuation_p0_completeness": cats.get("valuation", {}).get("p0_completeness", 0.0),
            "valuation_p1_completeness": cats.get("valuation", {}).get("p1_completeness", 0.0),
            "financial_statement_completeness": round(
                (
                    cats.get("income",   {}).get("completeness", 0.0) +
                    cats.get("balance",  {}).get("completeness", 0.0) +
                    cats.get("cashflow", {}).get("completeness", 0.0)
                ) / 3, 4
            ),
            "financial_indicator_completeness": cats.get("indicators", {}).get("completeness", 0.0),
            "financial_completeness":  round(
                (
                    cats.get("income",     {}).get("completeness", 0.0) +
                    cats.get("balance",    {}).get("completeness", 0.0) +
                    cats.get("cashflow",   {}).get("completeness", 0.0) +
                    cats.get("indicators", {}).get("completeness", 0.0)
                ) / 4, 4
            ),
            "rag_completeness":        cats.get("rag",        {}).get("completeness", 0.0),
            "categories":           cats,
            "missing_fields":       self.missing_fields,
        }


# ── 数据源合并（Phase 6N-7B）───────────────────────────────────────────────────

def merge_coverage_rows(
    daily_row: dict,
    fina_row: dict,
    bs_quote: dict,
    bs_fina: dict,
    ak_quote: dict,
    ak_stmt: dict,
    ak_ind: dict,
) -> tuple[dict, dict]:
    """
    按数据源优先级合并所有字段，并生成 __src__ 来源标注。

    daily（行情/估值）优先级: etl_daily_basic → baostock_kline → akshare_spot_em
    fina （财务）优先级:     etl_fina_indicator → akshare(报表/指标) → baostock

    返回 (merged_daily, merged_fina)，均带 "__src__" 与 "__computed__"。
    """
    # AKShare quote 字段名映射到内部 daily 键名
    ak_quote_norm = dict(ak_quote)
    if "latest_price" in ak_quote_norm:
        ak_quote_norm["close"] = ak_quote_norm.pop("latest_price")
    if "volume" in ak_quote_norm:
        ak_quote_norm["vol"] = ak_quote_norm.pop("volume")
    if "market_cap" in ak_quote_norm:
        ak_quote_norm["total_mv"] = ak_quote_norm.pop("market_cap")

    merged_daily: dict[str, Any] = {}
    daily_src: dict[str, str] = {}
    computed_daily: dict[str, Any] = dict(bs_quote.get("__computed__", {}))

    for src_name, d in (
        ("akshare_spot_em",  ak_quote_norm),
        ("baostock_kline",   bs_quote),
        ("etl_daily_basic",  daily_row),
    ):
        for k, v in d.items():
            if k.startswith("__") or v is None:
                continue
            merged_daily[k] = v
            daily_src[k] = src_name
    # computed market_cap/circ_mv 的来源标注
    for k in computed_daily:
        target = "total_mv" if k == "market_cap" else k
        if daily_src.get(target) == "baostock_kline":
            daily_src[target] = "computed"

    merged_fina: dict[str, Any] = {}
    fina_src: dict[str, str] = {}
    for src_name, d in (
        ("baostock",               bs_fina),
        ("akshare_sina_indicator", ak_ind),
        ("akshare_em_report",      ak_stmt),
        ("etl_fina_indicator",     fina_row),
    ):
        for k, v in d.items():
            if k.startswith("__") or v is None:
                continue
            merged_fina[k] = v
            fina_src[k] = src_name

    computed_fina: dict[str, Any] = {}
    # ocf_to_np: 直接值缺失时 computed = operating_cashflow / net_profit
    if merged_fina.get("ocf_to_np") is None:
        ocf, np_ = merged_fina.get("operating_cashflow"), merged_fina.get("net_profit")
        if ocf is not None and np_ not in (None, 0):
            merged_fina["ocf_to_np"] = round(ocf / np_, 6)
            fina_src["ocf_to_np"] = "computed"
            computed_fina["ocf_to_np"] = {
                "formula": "operating_cashflow / net_profit",
                "dependencies": ["operating_cashflow", "net_profit"],
            }
    # gross_profit: computed = operating_income − operating_cost（provider 已算则跳过）
    if merged_fina.get("gross_profit") is None:
        oi, oc = merged_fina.get("operating_income"), merged_fina.get("operating_cost")
        if oi is not None and oc is not None:
            merged_fina["gross_profit"] = oi - oc
            fina_src["gross_profit"] = "computed"
            computed_fina["gross_profit"] = {
                "formula": "operating_income - operating_cost",
                "dependencies": ["operating_income", "operating_cost"],
            }

    # total_share / float_share promote 到 daily（供 valuation audit 使用）
    for share_key in ("total_share", "float_share"):
        if merged_daily.get(share_key) is None and merged_fina.get(share_key) is not None:
            merged_daily[share_key] = merged_fina[share_key]
            daily_src[share_key] = fina_src.get(share_key, "baostock")

    merged_daily["__src__"] = daily_src
    merged_daily["__computed__"] = computed_daily
    merged_fina["__src__"] = fina_src
    merged_fina["__computed__"] = computed_fina
    return merged_daily, merged_fina


# ── CoverageAuditService ──────────────────────────────────────────────────────

class CoverageAuditService:
    """
    数据完整性审计服务。

    参数：
        db:         AsyncSession（SQLAlchemy）
        trade_date: 基准交易日（YYYY-MM-DD）
    """

    def __init__(self, db: AsyncSession, trade_date: str) -> None:
        self._db    = db
        self._trade_date = trade_date

    # ── Public API ────────────────────────────────────────────────────────────

    async def audit_stock(self, ts_code: str) -> CoverageReport:
        """对单只股票生成 CoverageReport。

        数据来源优先级：
          1. Tushare ETL 表（etl_daily_basic / etl_fina_indicator）
          2. BaoStock 免费 API（当 ETL 为空时自动补充）
        """
        categories: dict[str, CategoryCoverage] = {}

        # ── 1. ETL 表（Tushare 批量入库结果）─────────────────────────────────
        daily_row = await self._fetch_daily_basic(ts_code)
        fina_row  = await self._fetch_fina_indicator(ts_code)

        # ── 2. BaoStock 补充（ETL 为空时自动触发）──────────────────────────
        bs_quote:  dict[str, Any] = {}
        bs_fina:   dict[str, Any] = {}
        tushare_ok = bool(daily_row or fina_row)
        if not tushare_ok:
            # ETL tables empty → Tushare likely not available (PERMISSION_DENIED)
            bs_quote, bs_fina = await self._fetch_baostock_supplemental(ts_code)

        # ── 2b. AKShare 补充（Phase 6N-7B：报表 + 指标 + 行情/市值）────────
        ak_quote, ak_stmt, ak_ind, _ak_meta = await self._fetch_akshare_supplement(ts_code)

        # ── 3. 合并：ETL 优先 → BaoStock → AKShare ────────────────────────
        merged_daily, merged_fina = merge_coverage_rows(
            daily_row, fina_row, bs_quote, bs_fina, ak_quote, ak_stmt, ak_ind,
        )

        # Determine reason_code for Tushare-only fields when ETL empty
        tushare_miss_rc = (
            ReasonCode.PROVIDER_EMPTY.value
            if tushare_ok
            else ReasonCode.PERMISSION_DENIED.value
        )

        categories["quote"]      = self._audit_quote(merged_daily, tushare_miss_rc)
        categories["valuation"]  = self._audit_valuation(merged_daily, tushare_miss_rc)
        categories["income"]     = self._audit_income(merged_fina, tushare_miss_rc)
        categories["balance"]    = self._audit_balance(merged_fina, tushare_miss_rc)
        categories["cashflow"]   = self._audit_cashflow(merged_fina, tushare_miss_rc)
        categories["indicators"] = self._audit_indicators(merged_fina, tushare_miss_rc)

        # ── 4. RAG ──────────────────────────────────────────────────────────
        rag_info   = await self._fetch_rag_status(ts_code)
        rag_status = rag_info.get("rag_status", "unknown")
        categories["rag"] = self._audit_rag(rag_info)

        report = CoverageReport(
            ts_code=ts_code,
            trade_date=self._trade_date,
            categories=categories,
            rag_status=rag_status,
        )

        # Persist (non-fatal)
        await self._save_snapshot(report)
        await self._enqueue_missing(ts_code, report.missing_fields)

        return report

    async def audit_pool(self, ts_codes: list[str]) -> list[CoverageReport]:
        """对股票池批量审计。顺序执行，避免 DB 连接耗尽。"""
        reports = []
        for ts_code in ts_codes:
            try:
                rpt = await self.audit_stock(ts_code)
                reports.append(rpt)
            except Exception as exc:
                log.warning("coverage audit failed [%s]: %r", ts_code, exc)
                reports.append(self._empty_report(ts_code, str(exc)))
        return reports

    # ── Private: DB queries ───────────────────────────────────────────────────

    async def _fetch_daily_basic(self, ts_code: str) -> dict[str, Any]:
        """从 etl_daily_basic 读取最近一行 quote+valuation 数据。

        注：etl_daily_basic 仅存储 Tushare daily_basic 字段。
        pre_close / vol / amount 不在此表中（来自 daily 接口，非 daily_basic）。
        total_mv / circ_mv 单位为万元（Tushare 原始单位），取出后乘以 10000 转为元。
        """
        try:
            from sqlalchemy import text
            result = await self._db.execute(
                text("""
                    SELECT close, trade_date,
                           pe, pe_ttm, pb, turnover_rate,
                           total_share, float_share, total_mv, circ_mv
                    FROM etl_daily_basic
                    WHERE ts_code = :ts_code
                    ORDER BY trade_date DESC
                    LIMIT 1
                """),
                {"ts_code": ts_code},
            )
            row = result.mappings().first()
            if not row:
                return {}
            d = dict(row)
            # 万元 → 元
            for mv_key in ("total_mv", "circ_mv"):
                if d.get(mv_key) is not None:
                    d[mv_key] = float(d[mv_key]) * 10_000
            return d
        except Exception as exc:
            log.warning("fetch_daily_basic error [%s]: %r", ts_code, exc)
            return {}

    async def _fetch_fina_indicator(self, ts_code: str) -> dict[str, Any]:
        """从 etl_fina_indicator 读取最近一个财报期数据。

        注：etl_fina_indicator 列名：
          revenue_yoy   (不是 yoy_sales / or_yoy)
          netprofit_yoy (不是 yoy_profit / tr_yoy)
        ocf_to_netprofit 不在此表，需从现金流量表单独拉取（暂标为 None）。
        """
        try:
            from sqlalchemy import text
            result = await self._db.execute(
                text("""
                    SELECT end_date, roe, roa, grossprofit_margin, netprofit_margin,
                           revenue_yoy, netprofit_yoy, assets_turn, debt_to_assets,
                           current_ratio
                    FROM etl_fina_indicator
                    WHERE ts_code = :ts_code
                    ORDER BY end_date DESC
                    LIMIT 1
                """),
                {"ts_code": ts_code},
            )
            row = result.mappings().first()
            return dict(row) if row else {}
        except Exception as exc:
            log.warning("fetch_fina_indicator error [%s]: %r", ts_code, exc)
            return {}

    async def _fetch_rag_status(self, ts_code: str) -> dict[str, Any]:
        """查询 report_documents + report_chunks 的 RAG 状态。"""
        result: dict[str, Any] = {
            "documents_count": 0,
            "chunks_count":    0,
            "embedding_count": 0,
            "rag_status":      "unknown",
        }
        try:
            from sqlalchemy import text
            rd = (await self._db.execute(
                text("SELECT COUNT(*) FROM report_documents WHERE ts_code = :ts_code"),
                {"ts_code": ts_code},
            )).scalar() or 0
            rc = (await self._db.execute(
                text("SELECT COUNT(*) FROM report_chunks WHERE ts_code = :ts_code"),
                {"ts_code": ts_code},
            )).scalar() or 0
            emb = (await self._db.execute(
                text("SELECT COUNT(*) FROM report_chunks WHERE ts_code = :ts_code AND embedding IS NOT NULL"),
                {"ts_code": ts_code},
            )).scalar() or 0
            result.update({
                "documents_count": int(rd),
                "chunks_count":    int(rc),
                "embedding_count": int(emb),
                "rag_status": (
                    "ready"       if rc > 0 and emb > 0
                    else "not_indexed" if rd > 0
                    else "empty"
                ),
            })
        except Exception as exc:
            log.warning("fetch_rag_status error [%s]: %r", ts_code, exc)
        return result

    # ── Private: BaoStock supplemental ───────────────────────────────────────

    async def _fetch_baostock_supplemental(
        self, ts_code: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        当 Tushare ETL 为空时，从 BaoStock 拉取可用字段作为补充。

        使用单一 BaoStock 会话（login/logout 仅各一次）完成所有查询：
          - kline: close, pctChg, volume, turn (换手率)
          - profit_data: roeAvg, gpMargin, npMargin, netProfit, totalShare
          - balance_data: currentRatio, liabilityToAsset
          - growth_data:  YOYNI

        返回 (quote_dict, fina_dict)，键名与 _audit_* 方法期望的一致。
        """
        quote_dict: dict[str, Any] = {}
        fina_dict:  dict[str, Any] = {}

        try:
            import datetime
            import baostock as bs_lib
            from app.datasource.baostock_client import (
                _to_bs_code, _parse_rows, _suppress_bs_output,
                _safe_float, _get_bs_lock,
            )

            bs_code = _to_bs_code(ts_code)
            today   = datetime.date.today()
            start   = today - datetime.timedelta(days=30)

            # Build ordered list of (year, quarter) candidates to try,
            # starting from the most recently published quarter working backwards.
            # Financial data is published ~1–2 months after quarter end, so
            # for 2026-07, Q2 2026 data may not be published yet; use Q1 2026 and Q4 2025.
            def _recent_quarters(n: int = 4) -> list[tuple[int, int]]:
                yr, qtr = today.year, (today.month - 1) // 3 + 1
                # Back up one quarter to avoid querying unpublished data
                qtr -= 1
                if qtr < 1:
                    qtr = 4
                    yr -= 1
                candidates = []
                for _ in range(n):
                    candidates.append((yr, qtr))
                    qtr -= 1
                    if qtr < 1:
                        qtr = 4
                        yr -= 1
                return candidates

            quarter_candidates = _recent_quarters(4)

            def _sync_fetch_all():
                """Single BaoStock session for all queries."""
                with _suppress_bs_output():
                    bs_lib.login()
                result_kline:   list[dict] = []
                result_profit:  list[dict] = []
                result_balance: list[dict] = []
                result_growth:  list[dict] = []
                try:
                    # 1. Kline
                    rs = bs_lib.query_history_k_data_plus(
                        bs_code,
                        "date,close,pctChg,volume,amount,turn,peTTM,pbMRQ,psTTM,pcfNcfTTM",
                        start_date=start.strftime("%Y-%m-%d"),
                        end_date=today.strftime("%Y-%m-%d"),
                        frequency="d",
                        adjustflag="3",
                    )
                    result_kline = _parse_rows(rs)

                    # 2–4. Financial data: try quarters until we get data
                    for yr, qtr in quarter_candidates:
                        if not result_profit:
                            rs2 = bs_lib.query_profit_data(code=bs_code, year=yr, quarter=qtr)
                            result_profit.extend(_parse_rows(rs2))
                        if not result_balance:
                            rs3 = bs_lib.query_balance_data(code=bs_code, year=yr, quarter=qtr)
                            result_balance.extend(_parse_rows(rs3))
                        if not result_growth:
                            rs4 = bs_lib.query_growth_data(code=bs_code, year=yr, quarter=qtr)
                            result_growth.extend(_parse_rows(rs4))
                        if result_profit and result_balance and result_growth:
                            break
                finally:
                    with _suppress_bs_output():
                        bs_lib.logout()
                return result_kline, result_profit, result_balance, result_growth

            async with _get_bs_lock():
                klines, profits, balances, growths = await asyncio.to_thread(_sync_fetch_all)

            # ── Parse kline ────────────────────────────────────────────────
            if klines:
                lat = klines[-1]
                close   = _safe_float(lat.get("close"))
                pct_chg = _safe_float(lat.get("pctChg"))
                vol     = _safe_float(lat.get("volume"))
                turn    = _safe_float(lat.get("turn"))
                quote_dict = {
                    "close":         close,
                    "change_pct":    pct_chg / 100 if pct_chg is not None else None,
                    "vol":           vol,
                    "amount":        _safe_float(lat.get("amount")),
                    "trade_date":    lat.get("date", ""),
                    "turnover_rate": turn,
                    # valuation multiples from BaoStock kline
                    "pe_ttm":        _safe_float(lat.get("peTTM")),
                    "pb":            _safe_float(lat.get("pbMRQ")),
                    "ps_ttm":        _safe_float(lat.get("psTTM")),
                    "pcf_ttm":       _safe_float(lat.get("pcfNcfTTM")),
                }

            # ── Parse profit ───────────────────────────────────────────────
            if profits:
                lat = profits[0]
                fina_dict.update({
                    "roe":         _safe_float(lat.get("roeAvg")),
                    "gross_margin":_safe_float(lat.get("gpMargin")),
                    "net_margin":  _safe_float(lat.get("npMargin")),
                    "net_profit":  _safe_float(lat.get("netProfit")),
                    "total_share": _safe_float(lat.get("totalShare")),
                    "float_share": _safe_float(lat.get("liqaShare")),
                })

            # ── Computed: market_cap / circ_mv = close × share count ───────
            close_v = quote_dict.get("close")
            if close_v is not None:
                tot_sh = fina_dict.get("total_share")
                flt_sh = fina_dict.get("float_share")
                if tot_sh is not None and quote_dict.get("total_mv") is None:
                    quote_dict["total_mv"] = close_v * tot_sh   # 元
                    quote_dict.setdefault("__computed__", {})["market_cap"] = {
                        "formula": "close × total_share",
                        "dependencies": ["close", "total_share"],
                    }
                if flt_sh is not None and quote_dict.get("circ_mv") is None:
                    quote_dict["circ_mv"] = close_v * flt_sh    # 元
                    quote_dict.setdefault("__computed__", {})["circ_mv"] = {
                        "formula": "close × float_share",
                        "dependencies": ["close", "float_share"],
                    }

            # ── Parse balance ──────────────────────────────────────────────
            if balances:
                lat = balances[0]
                fina_dict.update({
                    "current_ratio":  _safe_float(lat.get("currentRatio")),
                    "debt_to_assets": _safe_float(lat.get("liabilityToAsset")),
                })

            # ── Parse growth ───────────────────────────────────────────────
            if growths:
                lat = growths[0]
                yoy_ni = _safe_float(lat.get("YOYNI"))
                if yoy_ni is not None:
                    # BaoStock YOYNI is already a percentage (e.g., 25.3 = 25.3%)
                    fina_dict["netprofit_yoy"] = yoy_ni

        except Exception as exc:
            log.warning("baostock supplemental failed [%s]: %r", ts_code, exc)

        return quote_dict, fina_dict

    # ── Private: AKShare supplemental（Phase 6N-7B）──────────────────────────

    async def _fetch_akshare_supplement(
        self, ts_code: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        """
        AKShare 补充：行情/市值 + 三大报表 + 财务指标。

        返回 (ak_quote, ak_statements, ak_indicators, meta)。
        每个 provider 失败均不影响其他 provider（独立 try）。
        """
        from app.datasource.akshare_coverage_providers import (
            akshare_quote_provider,
            akshare_statement_provider,
            akshare_indicator_provider,
        )

        ak_quote: dict[str, Any] = {}
        ak_stmt:  dict[str, Any] = {}
        ak_ind:   dict[str, Any] = {}
        meta:     dict[str, Any] = {}

        try:
            ak_quote, meta["quote"] = await akshare_quote_provider.fetch(ts_code)
        except Exception as exc:
            log.warning("akshare quote failed [%s]: %r", ts_code, exc)
            meta["quote"] = {"status": "failed", "reason_code": "PROVIDER_EMPTY",
                             "errors": [{"error": str(exc)[:150]}]}

        try:
            ak_stmt, meta["statements"] = await akshare_statement_provider.fetch(ts_code)
        except Exception as exc:
            log.warning("akshare statements failed [%s]: %r", ts_code, exc)
            meta["statements"] = {"status": "failed", "reason_code": "PROVIDER_EMPTY",
                                  "errors": [{"error": str(exc)[:150]}]}

        try:
            ak_ind, meta["indicators"] = await akshare_indicator_provider.fetch(ts_code)
        except Exception as exc:
            log.warning("akshare indicators failed [%s]: %r", ts_code, exc)
            meta["indicators"] = {"status": "failed", "reason_code": "PROVIDER_EMPTY",
                                  "errors": [{"error": str(exc)[:150]}]}

        return ak_quote, ak_stmt, ak_ind, meta

    # ── Private: per-category audit ───────────────────────────────────────────

    def _field_entry(
        self,
        name: str,
        value: Any,
        source: str,
        *,
        missing_rc: str | None = None,
    ) -> dict:
        """
        Build a field entry dict.

        Args:
            missing_rc: Override reason_code when value is None.
                        Defaults to PROVIDER_EMPTY.
        """
        has = value is not None
        return {
            "field_name":  name,
            "value":       value,
            "status":      "ok" if has else "missing",
            "source":      source if has else "",
            "reason_code": None if has else (
                missing_rc or ReasonCode.PROVIDER_EMPTY.value
            ),
        }

    @staticmethod
    def _row_src(row: dict, key: str, default: str) -> str:
        """Look up per-field source from the merged row's __src__ map."""
        return row.get("__src__", {}).get(key, default)

    def _audit_quote(
        self, row: dict, tushare_miss_rc: str = ReasonCode.PROVIDER_EMPTY.value
    ) -> CategoryCoverage:
        # Priority merge already done upstream:
        #   etl_daily_basic → baostock_kline → akshare_spot_em
        def _e(name: str, key: str) -> dict:
            v = row.get(key)
            return self._field_entry(
                name, v, self._row_src(row, key, "baostock_kline") if v is not None else "",
                missing_rc=tushare_miss_rc,
            )

        fields = [
            _e("latest_price", "close"),
            _e("change_pct",   "change_pct"),
            _e("volume",       "vol"),
            _e("amount",       "amount"),
            _e("trade_date",   "trade_date"),
        ]
        ok = sum(1 for f in fields if f["status"] == "ok")
        return CategoryCoverage("quote", len(fields), ok, fields)

    # 估值字段 P0/P1 分级（Phase 6N-7B）
    VALUATION_P0 = ("pe_ttm", "pb", "market_cap")
    VALUATION_P1 = ("circ_mv", "total_share", "float_share", "turnover_rate",
                    "dividend_yield", "ps_ttm", "pcf_ttm")

    def _audit_valuation(
        self, row: dict, tushare_miss_rc: str = ReasonCode.PROVIDER_EMPTY.value
    ) -> CategoryCoverage:
        computed_meta = row.get("__computed__", {})

        def _e(name: str, key: str, priority: str) -> dict:
            v = row.get(key)
            if v is not None:
                if name in computed_meta or key in computed_meta:
                    src = "computed"
                else:
                    src = self._row_src(row, key, "baostock_kline")
            else:
                src = ""
            entry = self._field_entry(name, v, src, missing_rc=tushare_miss_rc)
            entry["priority"] = priority
            cm = computed_meta.get(name) or computed_meta.get(key)
            if v is not None and cm:
                entry["status"] = "ok"          # computed counts as covered
                entry["formula"] = cm.get("formula")
                entry["dependencies"] = cm.get("dependencies")
            return entry

        fields = [
            # P0
            _e("pe_ttm",     "pe_ttm",   "P0"),
            _e("pb",         "pb",       "P0"),
            _e("market_cap", "total_mv", "P0"),
            # P1
            _e("circ_mv",       "circ_mv",       "P1"),
            _e("total_share",   "total_share",   "P1"),
            _e("float_share",   "float_share",   "P1"),
            _e("turnover_rate", "turnover_rate", "P1"),
            _e("dividend_yield","dividend_yield","P1"),
            _e("ps_ttm",        "ps_ttm",        "P1"),
            _e("pcf_ttm",       "pcf_ttm",       "P1"),
        ]
        ok = sum(1 for f in fields if f["status"] == "ok")

        p0 = [f for f in fields if f["priority"] == "P0"]
        p1 = [f for f in fields if f["priority"] == "P1"]
        p0_ok = sum(1 for f in p0 if f["status"] == "ok")
        p1_ok = sum(1 for f in p1 if f["status"] == "ok")
        extra = {
            "p0_completeness": round(p0_ok / len(p0), 4) if p0 else 0.0,
            "p1_completeness": round(p1_ok / len(p1), 4) if p1 else 0.0,
            "p0_total": len(p0), "p0_ok": p0_ok,
            "p1_total": len(p1), "p1_ok": p1_ok,
        }
        return CategoryCoverage("valuation", len(fields), ok, fields, extra=extra)

    def _audit_income(
        self, row: dict, tushare_miss_rc: str = ReasonCode.PROVIDER_EMPTY.value
    ) -> CategoryCoverage:
        # Phase 6N-7B: AKShare EM 报表接口（Sina 备源）提供全部利润表核心字段。
        def _e(name: str, key: str) -> dict:
            v = row.get(key)
            src = self._row_src(row, key, "akshare_em_report") if v is not None else ""
            return self._field_entry(name, v, src, missing_rc=tushare_miss_rc)

        fields = [
            _e("revenue",           "revenue"),
            _e("gross_profit",      "gross_profit"),
            _e("operating_profit",  "operating_profit"),
            _e("net_profit",        "net_profit"),
            _e("net_profit_parent", "net_profit_parent"),
        ]
        ok = sum(1 for f in fields if f["status"] == "ok")
        return CategoryCoverage("income", len(fields), ok, fields)

    def _audit_balance(
        self, row: dict, tushare_miss_rc: str = ReasonCode.PROVIDER_EMPTY.value
    ) -> CategoryCoverage:
        def _e(name: str) -> dict:
            v = row.get(name)
            src = self._row_src(row, name, "akshare_em_report") if v is not None else ""
            return self._field_entry(name, v, src, missing_rc=tushare_miss_rc)

        fields = [
            _e("total_assets"),
            _e("total_liabilities"),
            _e("total_equity"),
            _e("current_assets"),
            _e("current_liabilities"),
        ]
        ok = sum(1 for f in fields if f["status"] == "ok")
        return CategoryCoverage("balance", len(fields), ok, fields)

    def _audit_cashflow(
        self, row: dict, tushare_miss_rc: str = ReasonCode.PROVIDER_EMPTY.value
    ) -> CategoryCoverage:
        def _e(name: str) -> dict:
            v = row.get(name)
            src = self._row_src(row, name, "akshare_em_report") if v is not None else ""
            return self._field_entry(name, v, src, missing_rc=tushare_miss_rc)

        fields = [
            _e("operating_cashflow"),
            _e("investing_cashflow"),
            _e("financing_cashflow"),
        ]
        ok = sum(1 for f in fields if f["status"] == "ok")
        return CategoryCoverage("cashflow", len(fields), ok, fields)

    def _audit_indicators(
        self, row: dict, tushare_miss_rc: str = ReasonCode.PROVIDER_EMPTY.value
    ) -> CategoryCoverage:
        # Phase 6N-7B priority merge (upstream):
        #   etl_fina_indicator → akshare_sina_indicator → baostock_profit/balance/growth
        # ocf_to_np: 直接值（Sina）或 computed = operating_cashflow / net_profit
        computed_meta = row.get("__computed__", {})

        def _e(name: str, *keys: str) -> dict:
            for key in keys:
                v = row.get(key)
                if v is not None:
                    src = "computed" if name in computed_meta else \
                          self._row_src(row, key, "akshare_sina_indicator")
                    entry = self._field_entry(name, v, src, missing_rc=tushare_miss_rc)
                    cm = computed_meta.get(name)
                    if cm:
                        entry["formula"] = cm.get("formula")
                        entry["dependencies"] = cm.get("dependencies")
                    return entry
            return self._field_entry(name, None, "", missing_rc=tushare_miss_rc)

        fields = [
            _e("roe",               "roe"),
            _e("roa",               "roa"),
            _e("gross_margin",      "grossprofit_margin", "gross_margin"),
            _e("net_margin",        "netprofit_margin", "net_margin"),
            _e("revenue_growth",    "revenue_yoy", "revenue_growth"),
            _e("net_profit_growth", "netprofit_yoy", "net_profit_growth"),
            _e("debt_ratio",        "debt_to_assets", "debt_ratio"),
            _e("current_ratio",     "current_ratio"),
            _e("asset_turnover",    "assets_turn", "asset_turnover"),
            _e("inventory_turnover","inventory_turnover"),
            _e("ocf_to_np",         "ocf_to_np"),
        ]
        ok = sum(1 for f in fields if f["status"] == "ok")
        return CategoryCoverage("indicators", len(fields), ok, fields)

    # RAG data_status → completeness 映射（Phase 6N-7B：empty 不再算 100%）
    RAG_COMPLETENESS_MAP = {
        "ready":       1.0,
        "not_indexed": 0.3,
        "empty":       0.0,
        "failed":      0.0,
        "unknown":     0.0,
    }
    RAG_REASON_MAP = {
        "ready":       None,
        "not_indexed": ReasonCode.RAG_NOT_INDEXED.value,
        "empty":       ReasonCode.REPORT_NOT_INGESTED.value,
        "failed":      ReasonCode.CACHE_UNAVAILABLE.value,
        "unknown":     ReasonCode.CACHE_UNAVAILABLE.value,
    }

    def _audit_rag(self, rag_info: dict) -> CategoryCoverage:
        """
        RAG coverage 口径（Phase 6N-7B）：
          - diagnostic_status: ok（诊断查询成功）/ unknown（DB 查询失败）
          - data_status: ready / not_indexed / empty / failed
          - completeness: ready=100%, not_indexed=30%, empty=0%, failed/unknown=0%
        """
        data_status = rag_info.get("rag_status", "unknown")
        diagnostic_status = "ok" if data_status != "unknown" else "unknown"
        completeness = self.RAG_COMPLETENESS_MAP.get(data_status, 0.0)
        reason_code = self.RAG_REASON_MAP.get(data_status, ReasonCode.CACHE_UNAVAILABLE.value)

        fields = [
            self._field_entry("documents_count", rag_info.get("documents_count"), "report_documents"),
            self._field_entry("chunks_count",    rag_info.get("chunks_count"),    "report_chunks"),
            self._field_entry("embedding_count", rag_info.get("embedding_count"), "report_chunks"),
            self._field_entry("rag_status",      data_status,                     "report_chunks"),
        ]
        total = len(fields)
        # ok count derived from mapped completeness so overall stays consistent
        ok = round(completeness * total)
        cov = CategoryCoverage("rag", total, ok, fields, extra={
            "diagnostic_status": diagnostic_status,
            "data_status":       data_status,
            "documents_count":   rag_info.get("documents_count", 0),
            "chunks_count":      rag_info.get("chunks_count", 0),
            "embedding_count":   rag_info.get("embedding_count", 0),
            "reason_code":       reason_code,
        })
        cov.completeness = completeness
        return cov

    # ── Private: persistence ──────────────────────────────────────────────────

    async def _save_snapshot(self, report: CoverageReport) -> None:
        """写入 data_coverage_snapshot（non-fatal）。"""
        try:
            from sqlalchemy import text
            await self._db.execute(
                text("""
                    INSERT INTO data_coverage_snapshot
                        (ts_code, trade_date, overall_completeness,
                         quote_completeness, valuation_completeness,
                         financial_completeness, rag_status,
                         missing_field_count, generated_at)
                    VALUES
                        (:ts_code, :trade_date, :overall,
                         :quote, :valuation,
                         :financial, :rag_status,
                         :missing_count, NOW())
                    ON CONFLICT (ts_code, trade_date) DO UPDATE
                    SET overall_completeness = EXCLUDED.overall_completeness,
                        quote_completeness   = EXCLUDED.quote_completeness,
                        valuation_completeness = EXCLUDED.valuation_completeness,
                        financial_completeness = EXCLUDED.financial_completeness,
                        rag_status           = EXCLUDED.rag_status,
                        missing_field_count  = EXCLUDED.missing_field_count,
                        generated_at         = NOW()
                """),
                {
                    "ts_code":    report.ts_code,
                    "trade_date": report.trade_date,
                    "overall":    report.overall_completeness,
                    "quote":      report.categories.get("quote",      CategoryCoverage("quote",0,0,[])).completeness,
                    "valuation":  report.categories.get("valuation",  CategoryCoverage("valuation",0,0,[])).completeness,
                    "financial":  round(
                        (
                            report.categories.get("income",     CategoryCoverage("income",0,0,[])).completeness +
                            report.categories.get("balance",    CategoryCoverage("balance",0,0,[])).completeness +
                            report.categories.get("cashflow",   CategoryCoverage("cashflow",0,0,[])).completeness +
                            report.categories.get("indicators", CategoryCoverage("indicators",0,0,[])).completeness
                        ) / 4, 4
                    ),
                    "rag_status":    report.rag_status,
                    "missing_count": len(report.missing_fields),
                },
            )
            await self._db.commit()
        except Exception as exc:
            log.warning("save_snapshot failed [%s]: %r", report.ts_code, exc)
            try:
                await self._db.rollback()
            except Exception:
                pass

    async def _enqueue_missing(self, ts_code: str, missing: list[dict]) -> None:
        """将缺失字段写入 missing_field_queue（non-fatal）。"""
        if not missing:
            return
        try:
            from sqlalchemy import text
            for mf in missing:
                await self._db.execute(
                    text("""
                        INSERT INTO missing_field_queue
                            (ts_code, field_name, reason_code, trade_date, retry_count, status)
                        VALUES
                            (:ts_code, :field_name, :reason_code, :trade_date, 0, 'pending')
                        ON CONFLICT (ts_code, field_name, trade_date) DO NOTHING
                    """),
                    {
                        "ts_code":     ts_code,
                        "field_name":  mf["field_name"],
                        "reason_code": mf.get("reason_code", ReasonCode.FIELD_MISSING.value),
                        "trade_date":  self._trade_date,
                    },
                )
            await self._db.commit()
        except Exception as exc:
            log.warning("enqueue_missing failed [%s]: %r", ts_code, exc)
            try:
                await self._db.rollback()
            except Exception:
                pass

    # ── Private: helpers ──────────────────────────────────────────────────────

    def _empty_report(self, ts_code: str, error: str) -> CoverageReport:
        empty_cat = {
            cat: CategoryCoverage(cat, len(fields), 0, [
                {"field_name": f, "status": "missing",
                 "reason_code": ReasonCode.CACHE_UNAVAILABLE.value, "value": None}
                for f in fields
            ])
            for cat, fields in FIELD_CATEGORIES.items()
        }
        return CoverageReport(
            ts_code=ts_code,
            trade_date=self._trade_date,
            categories=empty_cat,
            rag_status="unknown",
        )
