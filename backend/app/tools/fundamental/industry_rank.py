"""
industry_rank.py — 行业排名工具（Phase 2B）

数据来源：industry_rank_snapshot 表（由 ETL + SQL 窗口函数预计算）

降级策略：
  1. ETL_ENABLED=false → partial=True，reason 说明
  2. DB 表不存在（尚未执行 migration）→ partial=True
  3. DB 中无该股票排名数据 → partial=True + reason（建议执行 ETL）
  4. 从不 fallback 到按票循环调用 Tushare

输出结构：
{
  "symbol": "600519",
  "ts_code": "600519.SH",
  "industry": "白酒",
  "trade_date": "2026-07-05",
  "end_date": "2025-12-31",
  "ranks": [
    {
      "metric": "roe",
      "value": 34.5,
      "rank_in_industry": 3,
      "peer_count": 42,
      "percentile_in_industry": 95.1,
      "direction": "higher_is_better",
      "comment": "ROE 位于行业前 5%，盈利能力领先。"
    },
    ...
  ],
  "source": "industry_rank_snapshot"
}
"""

from __future__ import annotations

import logging
from typing import Any

from app.datasource.tushare_client import _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import fmt_date

log = logging.getLogger(__name__)

# 指标中文描述
_METRIC_LABELS: dict[str, str] = {
    "total_mv":           "总市值",
    "circ_mv":            "流通市值",
    "pe_ttm":             "市盈率（TTM）",
    "pb":                 "市净率",
    "ps_ttm":             "市销率（TTM）",
    "dv_ttm":             "股息率（TTM）",
    "roe":                "ROE（净资产收益率）",
    "grossprofit_margin": "毛利率",
    "netprofit_margin":   "净利率",
    "revenue_yoy":        "营收同比增速",
    "netprofit_yoy":      "净利润同比增速",
    "assets_turn":        "总资产周转率",
    "debt_to_assets":     "资产负债率",
}


def _make_comment(metric: str, value: float | None, percentile: float | None, direction: str, rank: int, peer_count: int) -> str:
    """根据排名生成中文描述。"""
    if value is None or percentile is None:
        return f"{_METRIC_LABELS.get(metric, metric)} 数据缺失。"
    label = _METRIC_LABELS.get(metric, metric)
    pct_int = int(round(percentile * 100))
    top_pct = 100 - pct_int
    if direction == "lower_is_better":
        quality = "偏低（相对同行占优）" if percentile >= 0.7 else ("偏高（相对同行劣势）" if percentile <= 0.3 else "居中")
        return f"{label} {value:.2f}，行业第 {rank}/{peer_count}，相对估值{quality}（行业前 {top_pct+1}% 范围内）。"
    else:
        level = "领先" if percentile >= 0.8 else ("落后" if percentile <= 0.2 else "居中")
        return f"{label} {value:.2f}，行业第 {rank}/{peer_count}，{level}于 {pct_int}% 的同行。"


class IndustryRankTool(BaseFundamentalTool):
    """
    行业排名工具。

    读取预计算的 industry_rank_snapshot 表，不实时调用 Tushare。
    如果 ETL 未配置或数据缺失，返回 partial=True + reason。
    """

    module_key = "industry_rank"
    cache_ttl_seconds = 3600         # 1 小时（排名相对稳定）
    stale_ttl_seconds = 86400        # 1 天（过期数据仍可展示）

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:  # type: ignore[override]
        ts_code = _to_ts_code(market, symbol)

        # ── Step 1: ETL 可用性检查 ─────────────────────────────────────────────
        from app.etl.db import etl_available
        if not etl_available():
            return {
                "symbol": symbol,
                "ts_code": ts_code,
                "industry": None,
                "trade_date": None,
                "end_date": None,
                "ranks": [],
                "source": "unavailable",
                "_partial_errors": [
                    "ETL 未启用（ETL_ENABLED=false）。"
                    "如需行业排名，请设置 ETL_ENABLED=true 并执行 ETL 脚本。"
                ],
            }

        # ── Step 2: 查询 DB ───────────────────────────────────────────────────
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            # 检查表是否存在
            from app.etl.db import table_exists
            if not await table_exists(session, "industry_rank_snapshot"):
                return {
                    "symbol": symbol,
                    "ts_code": ts_code,
                    "industry": None,
                    "trade_date": None,
                    "end_date": None,
                    "ranks": [],
                    "source": "unavailable",
                    "_partial_errors": [
                        "industry_rank_snapshot 表不存在。"
                        "请执行: alembic upgrade head，"
                        "然后运行 ETL 脚本生成排名数据。"
                    ],
                }

            # 查询最新排名数据（trade_date 最新）
            result = await session.execute(
                text("""
                    SELECT
                        ts_code, trade_date, end_date, industry, metric,
                        value, rank_in_industry, peer_count,
                        percentile_in_industry, direction
                    FROM industry_rank_snapshot
                    WHERE ts_code = :ts_code
                    ORDER BY trade_date DESC, end_date DESC
                    LIMIT 100
                """),
                {"ts_code": ts_code},
            )
            rows = result.mappings().all()

        if not rows:
            return {
                "symbol": symbol,
                "ts_code": ts_code,
                "industry": None,
                "trade_date": None,
                "end_date": None,
                "ranks": [],
                "source": "industry_rank_snapshot",
                "_partial_errors": [
                    f"industry_rank_snapshot 中无 {ts_code} 的排名数据。"
                    "请先执行: python scripts/run_fundamental_etl.py industry_rank "
                    "--trade-date YYYYMMDD --end-date YYYYMMDD"
                ],
            }

        # 取最新 trade_date + end_date 组合的数据
        latest_trade = rows[0]["trade_date"]
        latest_end = rows[0]["end_date"]
        industry = rows[0]["industry"]

        latest_rows = [
            r for r in rows
            if r["trade_date"] == latest_trade and r["end_date"] == latest_end
        ]

        ranks = []
        for r in latest_rows:
            value = float(r["value"]) if r["value"] is not None else None
            percentile = float(r["percentile_in_industry"]) if r["percentile_in_industry"] is not None else None
            rank_i = int(r["rank_in_industry"]) if r["rank_in_industry"] is not None else None
            peer = int(r["peer_count"])
            direction = r["direction"]
            metric = r["metric"]

            ranks.append({
                "metric": metric,
                "value": round(value, 4) if value is not None else None,
                "rank_in_industry": rank_i,
                "peer_count": peer,
                "percentile_in_industry": round(percentile * 100, 2) if percentile is not None else None,
                "direction": direction,
                "comment": _make_comment(metric, value, percentile, direction, rank_i or 0, peer),
            })

        return {
            "symbol": symbol,
            "ts_code": ts_code,
            "industry": industry,
            "trade_date": fmt_date(latest_trade) if latest_trade else None,
            "end_date": fmt_date(latest_end) if latest_end else None,
            "ranks": sorted(ranks, key=lambda x: x["metric"]),
            "source": "industry_rank_snapshot",
        }
