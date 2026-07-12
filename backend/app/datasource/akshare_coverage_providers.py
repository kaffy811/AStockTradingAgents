"""
app/datasource/akshare_coverage_providers.py — AKShare Coverage Providers（Phase 6N-7B）

三个 Provider，为 CoverageAuditService 补充免费数据：

  1. AkshareQuoteProvider              — stock_zh_a_spot_em（行情/市值）
  2. AkshareFinancialStatementProvider — EM 三大报表（主）→ Sina（备）
  3. AkshareFinancialIndicatorProvider — EM 指标（主）→ Sina 指标（备）

设计约定：
  - 所有方法 async（内部 asyncio.to_thread 包裹同步 AkShare 调用）；
  - 返回 (data, meta)：
      data: {core_schema_field: value}   — 单位统一（市值=元，比率=小数）
      meta: {status, source, interface, elapsed_ms, latest_period,
             reason_code, source_fields: {norm: src_col}, errors: [...]}
  - 网络失败 → NETWORK_UNAVAILABLE / PROVIDER_TIMEOUT；
  - 列名变化 → COLUMN_RENAMED（记录在 meta.errors，字段不静默 null）；
  - 字段存在但为空 → PROVIDER_EMPTY。

Probe 验证（2026-07-08，600519.SH / 000725.SZ / 601686.SH）：
  - EM 报表接口（emweb 域名）：全部 15 字段可用，latest_period=2026-03-31；
  - EM spot（push2 域名）：dev 环境被 Clash 阻断 → NETWORK_UNAVAILABLE（prod 可用）；
  - EM 指标接口：返回 None（接口异常）→ Sina 指标 10/11 可用；
  - Sina 指标 "经营现金净流量与净利润的比率(%)"：列名带 % 但值为原始比率，不除 100。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

log = logging.getLogger(__name__)

# ── 列名 Mapping ──────────────────────────────────────────────────────────────

SPOT_EM_COLUMN_MAP: dict[str, str] = {
    "最新价":       "latest_price",
    "涨跌幅":       "change_pct",       # percent → /100
    "成交量":       "volume",           # 手
    "成交额":       "amount",           # 元
    "总市值":       "market_cap",       # 元
    "流通市值":     "circ_mv",          # 元
    "换手率":       "turnover_rate",    # percent（保持与 ETL 一致，不除100）
    "市盈率-动态":  "pe",
    "市净率":       "pb",
}

EM_PROFIT_MAP: dict[str, str] = {
    "TOTAL_OPERATE_INCOME": "revenue",
    "OPERATE_INCOME":       "operating_income",
    "OPERATE_COST":         "operating_cost",
    "OPERATE_PROFIT":       "operating_profit",
    "NETPROFIT":            "net_profit",
    "PARENT_NETPROFIT":     "net_profit_parent",
}
EM_BALANCE_MAP: dict[str, str] = {
    "TOTAL_ASSETS":         "total_assets",
    "TOTAL_LIABILITIES":    "total_liabilities",
    "TOTAL_EQUITY":         "total_equity",
    "TOTAL_PARENT_EQUITY":  "parent_equity",
    "TOTAL_CURRENT_ASSETS": "current_assets",
    "TOTAL_CURRENT_LIAB":   "current_liabilities",
}
EM_CASHFLOW_MAP: dict[str, str] = {
    "NETCASH_OPERATE": "operating_cashflow",
    "NETCASH_INVEST":  "investing_cashflow",
    "NETCASH_FINANCE": "financing_cashflow",
}

SINA_PROFIT_MAP: dict[str, str] = {
    "营业总收入":                 "revenue",
    "营业收入":                   "operating_income",
    "营业成本":                   "operating_cost",
    "营业利润":                   "operating_profit",
    "净利润":                     "net_profit",
    "归属于母公司所有者的净利润":  "net_profit_parent",
}
SINA_BALANCE_MAP: dict[str, str] = {
    "资产总计":                   "total_assets",
    "负债合计":                   "total_liabilities",
    "所有者权益(或股东权益)合计":  "total_equity",
    "归属于母公司股东权益合计":    "parent_equity",
    "流动资产合计":               "current_assets",
    "流动负债合计":               "current_liabilities",
}
SINA_CASHFLOW_MAP: dict[str, str] = {
    "经营活动产生的现金流量净额": "operating_cashflow",
    "投资活动产生的现金流量净额": "investing_cashflow",
    "筹资活动产生的现金流量净额": "financing_cashflow",
}

# Sina 指标：(core_field, unit)  unit: percent → /100, ratio → as-is
SINA_INDICATOR_MAP: dict[str, tuple[str, str]] = {
    "净资产收益率(%)":                 ("roe",                "percent"),
    "总资产净利润率(%)":               ("roa",                "percent"),
    "销售毛利率(%)":                   ("gross_margin",       "percent"),
    "销售净利率(%)":                   ("net_margin",         "percent"),
    "资产负债率(%)":                   ("debt_ratio",         "percent"),
    "流动比率":                        ("current_ratio",      "ratio"),
    "主营业务收入增长率(%)":           ("revenue_growth",     "percent"),
    "净利润增长率(%)":                 ("net_profit_growth",  "percent"),
    "总资产周转率(次)":                ("asset_turnover",     "ratio"),
    "存货周转率(次)":                  ("inventory_turnover", "ratio"),
    # 注意：该列虽带 (%) 后缀，实际值已是比率（probe 验证 OCF/NP=0.9558=raw）
    "经营现金净流量与净利润的比率(%)": ("ocf_to_np",          "ratio"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in ("None", "null", "nan", "--", "-", ""):
        return None
    try:
        f = float(s)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _exc_reason_code(exc: Exception) -> str:
    msg = repr(exc).lower()
    if "timeout" in msg:
        return "PROVIDER_TIMEOUT"
    if any(k in msg for k in ("connection", "proxy", "remote", "unreachable", "refused")):
        return "NETWORK_UNAVAILABLE"
    return "PROVIDER_EMPTY"


def _to_em_code(ts_code: str) -> str:
    code, ex = ts_code.split(".", 1)
    return f"{ex.upper()}{code}"


def _to_sina_code(ts_code: str) -> str:
    code, ex = ts_code.split(".", 1)
    return f"{ex.lower()}{code}"


def _map_row(row: Any, colmap: dict[str, str], available_cols: set) -> tuple[dict, dict, list]:
    """
    Map one DataFrame row through a column map.
    Returns (data, source_fields, errors).
    Missing column → COLUMN_RENAMED error; present-but-empty → PROVIDER_EMPTY error.
    """
    data: dict[str, Any] = {}
    source_fields: dict[str, str] = {}
    errors: list[dict] = []
    for src, norm in colmap.items():
        if src not in available_cols:
            errors.append({"field": norm, "source_field": src, "reason_code": "COLUMN_RENAMED"})
            continue
        val = _safe_float(row.get(src))
        if val is None:
            errors.append({"field": norm, "source_field": src, "reason_code": "PROVIDER_EMPTY"})
            continue
        data[norm] = val
        source_fields[norm] = src
    return data, source_fields, errors


# ── 1. Quote Provider ─────────────────────────────────────────────────────────

class AkshareQuoteProvider:
    """stock_zh_a_spot_em 行情/市值补充。dev 环境 push2 被代理阻断时返回 NETWORK_UNAVAILABLE。"""

    interface = "stock_zh_a_spot_em"
    source = "akshare_spot_em"

    async def fetch(self, ts_code: str, timeout_s: float = 20.0) -> tuple[dict, dict]:
        plain = ts_code.split(".")[0]
        t0 = time.monotonic()

        def _sync() -> Any:
            import akshare as ak
            from app.data.providers.akshare_provider import _direct_connect
            with _direct_connect():
                return ak.stock_zh_a_spot_em()

        try:
            df = await asyncio.wait_for(asyncio.to_thread(_sync), timeout=timeout_s)
        except asyncio.TimeoutError:
            return {}, self._meta("failed", t0, reason_code="PROVIDER_TIMEOUT")
        except Exception as exc:
            return {}, self._meta("failed", t0, reason_code=_exc_reason_code(exc),
                                  errors=[{"error": str(exc)[:200]}])

        if df is None or len(df) == 0:
            return {}, self._meta("empty", t0, reason_code="PROVIDER_EMPTY")

        sub = df[df["代码"] == plain]
        if sub.empty:
            return {}, self._meta("empty", t0, reason_code="PROVIDER_EMPTY",
                                  errors=[{"error": f"{plain} not in spot_em"}])

        row = sub.iloc[0]
        data, source_fields, errors = _map_row(row, SPOT_EM_COLUMN_MAP, set(df.columns))
        # normalize: change_pct percent → decimal
        if data.get("change_pct") is not None:
            data["change_pct"] = data["change_pct"] / 100
        meta = self._meta("ok", t0, source_fields=source_fields, errors=errors)
        meta["rows_count"] = len(df)
        meta["columns_count"] = len(df.columns)
        return data, meta

    def _meta(self, status: str, t0: float, *, reason_code: str | None = None,
              source_fields: dict | None = None, errors: list | None = None) -> dict:
        return {
            "provider": "akshare", "interface": self.interface, "source": self.source,
            "status": status, "elapsed_ms": int((time.monotonic() - t0) * 1000),
            "reason_code": reason_code, "source_fields": source_fields or {},
            "errors": errors or [],
        }


# ── 2. Financial Statement Provider ───────────────────────────────────────────

class AkshareFinancialStatementProvider:
    """三大报表：EM 主源（emweb 域名，dev 可用）→ Sina 备源。"""

    source_em = "akshare_em_report"
    source_sina = "akshare_sina_report"

    async def fetch(self, ts_code: str, timeout_s: float = 30.0) -> tuple[dict, dict]:
        t0 = time.monotonic()
        try:
            data, meta = await asyncio.wait_for(
                asyncio.to_thread(self._sync_fetch, ts_code), timeout=timeout_s,
            )
            meta["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
            return data, meta
        except asyncio.TimeoutError:
            return {}, {"provider": "akshare", "interface": "em+sina_statements",
                        "status": "failed", "reason_code": "PROVIDER_TIMEOUT",
                        "elapsed_ms": int((time.monotonic() - t0) * 1000),
                        "source_fields": {}, "errors": []}

    def _sync_fetch(self, ts_code: str) -> tuple[dict, dict]:
        import akshare as ak
        from app.data.providers.akshare_provider import _direct_connect

        em_code = _to_em_code(ts_code)
        sina_code = _to_sina_code(ts_code)

        data: dict[str, Any] = {}
        source_fields: dict[str, str] = {}
        errors: list[dict] = []
        sources_used: list[str] = []
        latest_period = ""

        sheets = [
            ("profit",
             lambda: ak.stock_profit_sheet_by_report_em(symbol=em_code), EM_PROFIT_MAP,
             lambda: ak.stock_financial_report_sina(stock=sina_code, symbol="利润表"), SINA_PROFIT_MAP),
            ("balance",
             lambda: ak.stock_balance_sheet_by_report_em(symbol=em_code), EM_BALANCE_MAP,
             lambda: ak.stock_financial_report_sina(stock=sina_code, symbol="资产负债表"), SINA_BALANCE_MAP),
            ("cashflow",
             lambda: ak.stock_cash_flow_sheet_by_report_em(symbol=em_code), EM_CASHFLOW_MAP,
             lambda: ak.stock_financial_report_sina(stock=sina_code, symbol="现金流量表"), SINA_CASHFLOW_MAP),
        ]

        for name, em_fn, em_map, sina_fn, sina_map in sheets:
            sheet_data: dict[str, Any] = {}
            # ── EM primary ──
            try:
                with _direct_connect():
                    df = em_fn()
                if df is not None and len(df):
                    row = df.iloc[0]
                    sheet_data, sf, errs = _map_row(row, em_map, set(df.columns))
                    if sheet_data:
                        sources_used.append(f"{name}:em")
                        source_fields.update(sf)
                        errors.extend(errs)
                        rd = row.get("REPORT_DATE")
                        if rd is not None:
                            latest_period = str(rd)[:10]
            except Exception as exc:
                errors.append({"sheet": name, "source": "em",
                               "reason_code": _exc_reason_code(exc), "error": str(exc)[:150]})

            # ── Sina fallback ──
            if not sheet_data:
                try:
                    with _direct_connect():
                        df = sina_fn()
                    if df is not None and len(df):
                        row = df.iloc[0]  # sina sorted desc by 报告日
                        sheet_data, sf, errs = _map_row(row, sina_map, set(df.columns))
                        if sheet_data:
                            sources_used.append(f"{name}:sina")
                            source_fields.update(sf)
                            errors.extend(errs)
                            rd = row.get("报告日")
                            if rd is not None and not latest_period:
                                s = str(rd)
                                latest_period = f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s
                except Exception as exc:
                    errors.append({"sheet": name, "source": "sina",
                                   "reason_code": _exc_reason_code(exc), "error": str(exc)[:150]})

            data.update(sheet_data)

        # computed: gross_profit = operating_income − operating_cost
        if data.get("gross_profit") is None:
            oi, oc = data.get("operating_income"), data.get("operating_cost")
            if oi is not None and oc is not None:
                data["gross_profit"] = oi - oc
                source_fields["gross_profit"] = "computed:operating_income-operating_cost"

        status = "ok" if data else "failed"
        meta = {
            "provider": "akshare",
            "interface": "+".join(sources_used) or "em+sina_statements",
            "source": self.source_em if any(":em" in s for s in sources_used) else self.source_sina,
            "status": status, "elapsed_ms": 0,
            "latest_period": latest_period,
            "reason_code": None if data else "PROVIDER_EMPTY",
            "source_fields": source_fields, "errors": errors,
        }
        return data, meta


# ── 3. Financial Indicator Provider ───────────────────────────────────────────

class AkshareFinancialIndicatorProvider:
    """财务指标：EM stock_financial_analysis_indicator_em（主）→ Sina（备）。"""

    source = "akshare_sina_indicator"

    async def fetch(self, ts_code: str, timeout_s: float = 20.0) -> tuple[dict, dict]:
        t0 = time.monotonic()
        try:
            data, meta = await asyncio.wait_for(
                asyncio.to_thread(self._sync_fetch, ts_code), timeout=timeout_s,
            )
            meta["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
            return data, meta
        except asyncio.TimeoutError:
            return {}, {"provider": "akshare", "interface": "financial_indicator",
                        "status": "failed", "reason_code": "PROVIDER_TIMEOUT",
                        "elapsed_ms": int((time.monotonic() - t0) * 1000),
                        "source_fields": {}, "errors": []}

    def _sync_fetch(self, ts_code: str) -> tuple[dict, dict]:
        import datetime as _dt

        import akshare as ak
        from app.data.providers.akshare_provider import _direct_connect

        plain = ts_code.split(".")[0]
        errors: list[dict] = []

        # ── EM primary（probe 显示当前接口返回 None → 直接尝试并记录）──
        try:
            with _direct_connect():
                df_em = ak.stock_financial_analysis_indicator_em(
                    symbol=_to_em_code(ts_code), indicator="按报告期",
                )
            if df_em is not None and len(df_em):
                # EM 接口可用时优先（列名映射未在 dev 验证，暂记录并 fallback）
                errors.append({"source": "em", "reason_code": "NOT_IMPLEMENTED",
                               "error": "EM indicator column mapping not verified; using sina"})
        except Exception as exc:
            errors.append({"source": "em", "reason_code": _exc_reason_code(exc),
                           "error": str(exc)[:120]})

        # ── Sina（当前 dev/prod 均可用）──
        start_year = str(_dt.date.today().year - 1)
        try:
            with _direct_connect():
                df = ak.stock_financial_analysis_indicator(symbol=plain, start_year=start_year)
        except Exception as exc:
            return {}, {"provider": "akshare", "interface": "stock_financial_analysis_indicator",
                        "source": self.source, "status": "failed",
                        "reason_code": _exc_reason_code(exc), "elapsed_ms": 0,
                        "source_fields": {}, "errors": errors + [{"error": str(exc)[:150]}]}

        if df is None or len(df) == 0:
            return {}, {"provider": "akshare", "interface": "stock_financial_analysis_indicator",
                        "source": self.source, "status": "empty",
                        "reason_code": "PROVIDER_EMPTY", "elapsed_ms": 0,
                        "source_fields": {}, "errors": errors}

        cols = set(df.columns)
        latest = df.iloc[-1]  # sina 按日期升序
        data: dict[str, Any] = {}
        source_fields: dict[str, str] = {}
        for src, (norm, unit) in SINA_INDICATOR_MAP.items():
            if src not in cols:
                errors.append({"field": norm, "source_field": src, "reason_code": "COLUMN_RENAMED"})
                continue
            raw = _safe_float(latest.get(src))
            if raw is None:
                errors.append({"field": norm, "source_field": src, "reason_code": "PROVIDER_EMPTY"})
                continue
            data[norm] = raw / 100 if unit == "percent" else raw
            source_fields[norm] = src

        return data, {
            "provider": "akshare", "interface": "stock_financial_analysis_indicator",
            "source": self.source, "status": "ok" if data else "empty",
            "reason_code": None if data else "PROVIDER_EMPTY",
            "elapsed_ms": 0,
            "latest_period": str(latest.get("日期", "")),
            "source_fields": source_fields, "errors": errors,
        }


# ── 模块级单例 ────────────────────────────────────────────────────────────────

akshare_quote_provider     = AkshareQuoteProvider()
akshare_statement_provider = AkshareFinancialStatementProvider()
akshare_indicator_provider = AkshareFinancialIndicatorProvider()
