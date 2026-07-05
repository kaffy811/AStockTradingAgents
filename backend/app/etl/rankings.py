"""
app/etl/rankings.py — SQL 窗口函数行业排名计算（Phase 2B）

compute_industry_rank_snapshot(trade_date, end_date)
  读取 etl_stock_basic + etl_daily_basic + etl_fina_indicator，
  通过 SQL 窗口函数（RANK / COUNT OVER PARTITION BY industry）计算行业内排名，
  写入 industry_rank_snapshot 表。

金融口径：
  高分越好（higher_is_better）：roe, grossprofit_margin, netprofit_margin,
    revenue_yoy, netprofit_yoy, assets_turn, total_mv, circ_mv, dv_ttm
  低分越好（lower_is_better）：pe_ttm, pb, ps_ttm, debt_to_assets
    （pe_ttm / ps_ttm <= 0 时排除，避免亏损股干扰估值排名）

percentile_in_industry = 1 - (rank - 1) / max(peer_count - 1, 1)
  → 第 1 名 percentile = 1.0，最后一名 percentile ≈ 0.0
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.etl.db import require_etl, get_etl_session, etl_available

log = logging.getLogger(__name__)


# ── 指标配置 ──────────────────────────────────────────────────────────────────

_METRIC_CONFIG: list[dict[str, Any]] = [
    # 估值/市值类（daily_basic）
    {"metric": "total_mv",   "source": "daily_basic",   "col": "db.total_mv",   "direction": "higher_is_better", "filter": "db.total_mv > 0"},
    {"metric": "circ_mv",    "source": "daily_basic",   "col": "db.circ_mv",    "direction": "higher_is_better", "filter": "db.circ_mv > 0"},
    {"metric": "pe_ttm",     "source": "daily_basic",   "col": "db.pe_ttm",     "direction": "lower_is_better",  "filter": "db.pe_ttm > 0"},
    {"metric": "pb",         "source": "daily_basic",   "col": "db.pb",         "direction": "lower_is_better",  "filter": "db.pb > 0"},
    {"metric": "ps_ttm",     "source": "daily_basic",   "col": "db.ps_ttm",     "direction": "lower_is_better",  "filter": "db.ps_ttm > 0"},
    {"metric": "dv_ttm",     "source": "daily_basic",   "col": "db.dv_ttm",     "direction": "higher_is_better", "filter": "db.dv_ttm IS NOT NULL"},
    # 财务类（fina_indicator）
    {"metric": "roe",                "source": "fina_indicator", "col": "fi.roe",                "direction": "higher_is_better", "filter": "fi.roe IS NOT NULL"},
    {"metric": "grossprofit_margin", "source": "fina_indicator", "col": "fi.grossprofit_margin", "direction": "higher_is_better", "filter": "fi.grossprofit_margin IS NOT NULL"},
    {"metric": "netprofit_margin",   "source": "fina_indicator", "col": "fi.netprofit_margin",   "direction": "higher_is_better", "filter": "fi.netprofit_margin IS NOT NULL"},
    {"metric": "revenue_yoy",        "source": "fina_indicator", "col": "fi.revenue_yoy",        "direction": "higher_is_better", "filter": "fi.revenue_yoy IS NOT NULL"},
    {"metric": "netprofit_yoy",      "source": "fina_indicator", "col": "fi.netprofit_yoy",      "direction": "higher_is_better", "filter": "fi.netprofit_yoy IS NOT NULL"},
    {"metric": "assets_turn",        "source": "fina_indicator", "col": "fi.assets_turn",        "direction": "higher_is_better", "filter": "fi.assets_turn IS NOT NULL"},
    {"metric": "debt_to_assets",     "source": "fina_indicator", "col": "fi.debt_to_assets",     "direction": "lower_is_better",  "filter": "fi.debt_to_assets IS NOT NULL"},
]


def _build_rank_sql(metric_cfg: dict, trade_date: str, end_date: str) -> str:
    """
    为单个指标构建 INSERT ... ON CONFLICT DO UPDATE 的排名 SQL。

    使用 PostgreSQL 窗口函数 RANK() OVER (PARTITION BY industry ORDER BY col):
      - higher_is_better → ORDER BY col DESC NULLS LAST（值越大排名越前）
      - lower_is_better  → ORDER BY col ASC  NULLS LAST（值越小排名越前）

    percentile = 1 - (rank - 1) / GREATEST(peer_count - 1, 1)
    """
    metric = metric_cfg["metric"]
    col = metric_cfg["col"]
    direction = metric_cfg["direction"]
    val_filter = metric_cfg["filter"]
    source = metric_cfg["source"]

    order_dir = "DESC NULLS LAST" if direction == "higher_is_better" else "ASC NULLS LAST"

    return f"""
WITH base AS (
    SELECT
        sb.ts_code,
        sb.industry,
        {col} AS value
    FROM etl_stock_basic sb
    JOIN etl_daily_basic db
        ON sb.ts_code = db.ts_code AND db.trade_date = '{trade_date}'
    JOIN etl_fina_indicator fi
        ON sb.ts_code = fi.ts_code AND fi.end_date = '{end_date}'
    WHERE sb.industry IS NOT NULL
      AND {val_filter}
),
ranked AS (
    SELECT
        ts_code,
        industry,
        value,
        RANK() OVER (PARTITION BY industry ORDER BY value {order_dir}) AS rank_in_industry,
        COUNT(*) OVER (PARTITION BY industry) AS peer_count
    FROM base
)
INSERT INTO industry_rank_snapshot
    (ts_code, trade_date, end_date, industry, metric, value,
     rank_in_industry, peer_count, percentile_in_industry,
     direction, source_table, generated_at)
SELECT
    ts_code,
    '{trade_date}',
    '{end_date}',
    industry,
    '{metric}',
    value,
    rank_in_industry::INTEGER,
    peer_count::INTEGER,
    CAST(1.0 - (rank_in_industry - 1.0) / GREATEST(peer_count - 1, 1) AS NUMERIC(8,4)),
    '{direction}',
    'etl_{source}',
    now()
FROM ranked
ON CONFLICT (ts_code, trade_date, end_date, metric)
DO UPDATE SET
    industry             = EXCLUDED.industry,
    value                = EXCLUDED.value,
    rank_in_industry     = EXCLUDED.rank_in_industry,
    peer_count           = EXCLUDED.peer_count,
    percentile_in_industry = EXCLUDED.percentile_in_industry,
    direction            = EXCLUDED.direction,
    source_table         = EXCLUDED.source_table,
    generated_at         = EXCLUDED.generated_at
"""


class RankResult(dict):
    """compute_industry_rank_snapshot 的返回值。"""


async def compute_industry_rank_snapshot(
    trade_date: str,
    end_date: str,
) -> RankResult:
    """
    计算指定 trade_date + end_date 组合下全市场 industry_rank_snapshot。

    前置条件：
      - etl_stock_basic 已导入（至少含 ts_code / industry）
      - etl_daily_basic 含 trade_date 行
      - etl_fina_indicator 含 end_date 行

    输出：
        {
          "trade_date": "20260705",
          "end_date": "20251231",
          "metrics_computed": [...],
          "total_rows_inserted": n,
          "errors": [...],
        }
    """
    require_etl()

    result: RankResult = {
        "trade_date": trade_date,
        "end_date": end_date,
        "metrics_computed": [],
        "total_rows_inserted": 0,
        "errors": [],
    }

    async with await get_etl_session() as session:
        for cfg in _METRIC_CONFIG:
            metric = cfg["metric"]
            try:
                sql = _build_rank_sql(cfg, trade_date, end_date)
                res = await session.execute(text(sql))
                rowcount = res.rowcount if res.rowcount and res.rowcount >= 0 else 0
                await session.commit()
                result["metrics_computed"].append(metric)
                result["total_rows_inserted"] += rowcount
                log.info(
                    "industry_rank: metric=%s trade=%s end=%s rows=%d",
                    metric, trade_date, end_date, rowcount,
                )
            except Exception as exc:
                await session.rollback()
                result["errors"].append(f"{metric}: {exc}")
                log.error("compute_industry_rank metric=%s 失败: %s", metric, exc)

    return result


# ── Pure-Python 计算（用于测试，不依赖 DB） ───────────────────────────────────

def compute_ranks_in_memory(
    rows: list[dict[str, Any]],
    value_key: str,
    direction: str = "higher_is_better",
) -> list[dict[str, Any]]:
    """
    对 rows 按 value_key 计算行业内排名（纯 Python，用于测试和验证）。

    返回每行增加以下字段：
      rank_in_industry, peer_count, percentile_in_industry

    行必须有 "industry" 和 value_key 字段。
    缺失值（None）不参与排名，其 rank_in_industry / percentile 为 None。
    """
    # 按 industry 分组
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["industry"]].append(row)

    results = []
    for industry, members in groups.items():
        valid = [r for r in members if r.get(value_key) is not None]
        invalid = [r for r in members if r.get(value_key) is None]

        # 排序
        reverse = direction == "higher_is_better"
        valid_sorted = sorted(valid, key=lambda r: r[value_key], reverse=reverse)

        peer_count = len(valid_sorted)
        for rank_0, row in enumerate(valid_sorted):
            rank_1 = rank_0 + 1  # 1-indexed
            percentile = 1.0 - (rank_1 - 1) / max(peer_count - 1, 1)
            results.append({
                **row,
                "rank_in_industry": rank_1,
                "peer_count": peer_count,
                "percentile_in_industry": round(percentile, 4),
            })

        for row in invalid:
            results.append({
                **row,
                "rank_in_industry": None,
                "peer_count": peer_count,
                "percentile_in_industry": None,
            })

    return results
