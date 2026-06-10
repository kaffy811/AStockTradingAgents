"""
AkShareFundamentalProvider — 同花顺财报数据封装层。

封装的 AkShare 接口（同花顺，不依赖东方财富 _em 接口）：
  stock_financial_abstract_ths(symbol)
    → 综合财务摘要：ROE / 毛利率 / 净利率 / 收入增速 / 利润增速 / 资产负债率
    → 25 列，~102 期（季报+年报），日期列 "报告期" 为 "YYYY-MM-DD" 字符串

  stock_financial_cash_ths(symbol)
    → 现金流量表：经营活动现金流净额
    → 72 列，~98 期，日期列 "报告期" 为 "YYYY-MM-DD" 字符串

不可用接口（已损坏，不使用）：
  stock_balance_sheet_by_report_em   → TypeError
  stock_cash_flow_sheet_by_report_em → TypeError
  stock_profit_sheet_by_report_em    → TypeError

数据格式规则（所有 _ths 接口共用）：
  - 所有列 dtype = object（字符串）
  - 缺失值 = 字符串 "False"（不是 Python bool）
  - 百分比：  "54.27%"  → float 54.27（保持百分比单位，不除以 100）
  - 亿元金额： "615.22亿" → float 61522000000.0（单位：元）
  - 万元金额： "1.23万"   → float 12300.0（单位：元）
  - 纯数字：  "12.34"    → float 12.34
  - 解析失败  → None（不抛异常）

代理处理：
  复用 akshare_provider._direct_connect() 进行直连（同花顺域名不受 Clash 东方财富规则影响）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.data.providers.akshare_provider import _direct_connect

log = logging.getLogger(__name__)


# ── 字符串值解析 ──────────────────────────────────────────────────────────────

_THS_NULL_STRINGS = frozenset({"False", "false", "", "—", "-", "--", "N/A", "n/a"})


def _parse_ths_value(raw: Any) -> float | None:
    """
    将同花顺财报字符串值解析为 float。

    规则：
      "54.27%"  → 54.27       （百分比，不除以 100）
      "615.22亿" → 6.1522e10  （亿元 → 元）
      "1.23万"  → 12300.0     （万元 → 元）
      "False"   → None
      解析失败  → None
    """
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    if s in _THS_NULL_STRINGS:
        return None
    try:
        if s.endswith("%"):
            return round(float(s[:-1]), 6)
        if "亿" in s:
            return round(float(s.replace("亿", "")) * 1e8, 2)
        if "万" in s:
            return round(float(s.replace("万", "")) * 1e4, 2)
        return float(s)
    except (ValueError, TypeError):
        return None


# ── Provider ──────────────────────────────────────────────────────────────────

class AkShareFundamentalProvider:
    """
    同花顺财报数据 Provider。

    get_financial_abstract(symbol)  → dict | None
    get_cash_flow(symbol)           → dict | None

    两个方法独立失败，不互相影响。
    失败时 log error 并返回 None，由 FundamentalDataService 做降级处理。
    """

    # ── 综合财务摘要 ──────────────────────────────────────────────────────────

    def get_financial_abstract(self, symbol: str) -> dict | None:
        """
        调用 stock_financial_abstract_ths(symbol)，返回最新一期的字段 dict。

        返回结构示例：
        {
          "report_date":          "2025-12-31",
          "roe":                  54.27,          # %
          "gross_margin":         91.44,          # %
          "net_margin":           49.55,          # %
          "revenue_growth_yoy":   18.21,          # %
          "net_profit_growth_yoy":19.38,          # %
          "debt_ratio":           16.42,          # %
        }

        任意字段解析失败时该字段为 None，不影响其他字段。
        接口整体失败时返回 None。
        """
        import akshare as ak
        try:
            with _direct_connect():
                df = ak.stock_financial_abstract_ths(symbol=symbol)
        except Exception as exc:
            raise RuntimeError(
                f"stock_financial_abstract_ths 获取失败 [{symbol}]: {exc}"
            ) from exc

        if df is None or df.empty:
            raise RuntimeError(
                f"stock_financial_abstract_ths 返回空数据 [{symbol}]"
            )

        # 确认日期列存在
        if "报告期" not in df.columns:
            raise RuntimeError(
                f"stock_financial_abstract_ths 缺少 '报告期' 列 [{symbol}]，"
                f"实际列名: {df.columns.tolist()}"
            )

        # 按报告期降序，取最新一期
        df = df.sort_values("报告期", ascending=False)
        row = df.iloc[0]
        report_date: str = str(row["报告期"])

        # 列名 → 字段名映射
        _COL_MAP = {
            "净资产收益率":         "roe",
            "销售毛利率":           "gross_margin",
            "销售净利率":           "net_margin",
            "营业总收入同比增长率":  "revenue_growth_yoy",
            "净利润同比增长率":      "net_profit_growth_yoy",
            "资产负债率":           "debt_ratio",
        }

        result: dict = {"report_date": report_date}
        for col, field in _COL_MAP.items():
            raw = row.get(col)
            result[field] = _parse_ths_value(raw)
            if raw is not None:
                log.debug(
                    "abstract_ths [%s] %s=%r → %s",
                    symbol, col, raw, result[field],
                )

        log.info(
            "abstract_ths OK [%s] 报告期=%s roe=%s gross=%s net=%s",
            symbol, report_date,
            result.get("roe"), result.get("gross_margin"), result.get("net_margin"),
        )
        return result

    # ── 现金流量表 ────────────────────────────────────────────────────────────

    def get_cash_flow(self, symbol: str) -> dict | None:
        """
        调用 stock_financial_cash_ths(symbol)，返回最新一期的字段 dict。

        返回结构示例：
        {
          "report_date":        "2025-12-31",
          "operating_cashflow": 61522000000.0,   # 元 CNY
        }

        接口整体失败时返回 None。
        """
        import akshare as ak

        # 同花顺现金流接口的经营活动列名（带 * 前缀）
        _OCF_COL = "*经营活动产生的现金流量净额"

        try:
            with _direct_connect():
                df = ak.stock_financial_cash_ths(symbol=symbol)
        except Exception as exc:
            raise RuntimeError(
                f"stock_financial_cash_ths 获取失败 [{symbol}]: {exc}"
            ) from exc

        if df is None or df.empty:
            raise RuntimeError(
                f"stock_financial_cash_ths 返回空数据 [{symbol}]"
            )

        if "报告期" not in df.columns:
            raise RuntimeError(
                f"stock_financial_cash_ths 缺少 '报告期' 列 [{symbol}]，"
                f"实际列名: {df.columns.tolist()}"
            )

        df = df.sort_values("报告期", ascending=False)
        row = df.iloc[0]
        report_date: str = str(row["报告期"])

        ocf = _parse_ths_value(row.get(_OCF_COL))
        log.info(
            "cash_ths OK [%s] 报告期=%s operating_cashflow=%s",
            symbol, report_date, ocf,
        )
        return {
            "report_date":        report_date,
            "operating_cashflow": ocf,
        }


# ── 模块级单例 ────────────────────────────────────────────────────────────────

fundamental_provider = AkShareFundamentalProvider()
