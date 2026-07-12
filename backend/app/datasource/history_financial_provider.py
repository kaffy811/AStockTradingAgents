"""
app/datasource/history_financial_provider.py — Full-History Financial Provider（Phase 6T-B）

为每个财务模块生成上市以来全量历史序列，替代原来仅返回最新快照的模式。

输出结构（每个模块）：
{
  "provider": "baostock",
  "module_key": "profitability",
  "period_type": "quarterly",   // annual | quarterly | daily | mixed
  "rows": [...],                // 按期间升序排列
  "latest": {...},              // 最新一期
  "history": [...],             // 与 rows 相同，用于图表
  "source_fields": {...},
  "data_success": true,
  "history_coverage": {
      "start_period": "2016-03-31",
      "end_period": "2026-03-31",
      "periods_count": 40,
      "expected_periods_count": 41,
      "missing_periods": [],
      "history_truncated": false
  },
  "chart_contract": {
      "preferred_chart": "multi_line",
      "x_field": "period",
      "series": [...]
  }
}

安全原则：
- 不暴露内部字段（local_path / token / secret）
- 不提供投资建议
- 不访问 aicaibao
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

log = logging.getLogger(__name__)

# ── Chart contracts 定义 ─────────────────────────────────────────────────────

_CHART_CONTRACTS: dict[str, dict[str, Any]] = {
    "profitability": {
        # Phase 6T-E: BaoStock profit 表无 roa 字段，契约不得引用不存在字段
        "preferred_chart": "multi_line",
        "x_field": "period",
        "series": [
            {"field": "roe", "display_name": "ROE", "display_type": "percent"},
            {"field": "gross_margin", "display_name": "毛利率", "display_type": "percent"},
            {"field": "net_margin", "display_name": "净利率", "display_type": "percent"},
        ],
    },
    "growth": {
        # Phase 6T-E: 字段名与 provider 真实口径对齐。
        # BaoStock growth 表只有净利润/归母净利润同比（YOYNI/YOYPNI），没有营收同比；
        # 绝对值来自 profit 表的主营业务收入（MBRevenue）与净利润，不得标注为"营业收入/归母净利润"。
        "preferred_chart": "bar_line_combo",
        "x_field": "period",
        "series": [
            {"field": "main_business_revenue", "display_name": "主营业务收入", "display_type": "number", "chart_type": "bar"},
            {"field": "net_profit", "display_name": "净利润", "display_type": "number", "chart_type": "bar"},
            {"field": "net_profit_yoy", "display_name": "净利润同比", "display_type": "percent", "chart_type": "line", "axis": "secondary"},
            {"field": "net_profit_parent_yoy", "display_name": "归母净利润同比", "display_type": "percent", "chart_type": "line", "axis": "secondary"},
        ],
        "highlight_negative_yoy": True,
    },
    "cashflow_quality": {
        "preferred_chart": "positive_negative_bar",
        "x_field": "period",
        "series": [
            # Phase 6T-E: BaoStock cash_flow 表只有比率字段（无经营现金净流量绝对值），
            # 契约不得引用不存在字段；比率可为负，保留 0 轴突出。
            {"field": "ocf_to_np", "display_name": "经营现金/净利润", "display_type": "ratio"},
            {"field": "ocf_to_revenue", "display_name": "经营现金/营收", "display_type": "ratio"},
            {"field": "cashflow_revenue_ratio", "display_name": "现金流收入比", "display_type": "ratio"},
        ],
        "highlight_zero_axis": True,
        # Phase 6T-E1: ocf_to_np 与 ocf_to_revenue 真实量级差可 >100x（601686 实测 124x），
        # 声明自动副轴拆分，不共用同一普通 Y 轴
        "auto_secondary_axis": True,
        "scale_threshold": 100,
    },
    "solvency": {
        "preferred_chart": "multi_line",
        "x_field": "period",
        "series": [
            {"field": "current_ratio", "display_name": "流动比率", "display_type": "ratio"},
            {"field": "quick_ratio", "display_name": "速动比率", "display_type": "ratio"},
            {"field": "cash_ratio", "display_name": "现金比率", "display_type": "ratio"},
            {"field": "debt_ratio", "display_name": "资产负债率", "display_type": "percent", "axis": "secondary"},
        ],
    },
    "operation_capability": {
        "preferred_chart": "grouped_bar",
        "x_field": "period",
        "series": [
            {"field": "asset_turnover", "display_name": "总资产周转率", "display_type": "ratio"},
            {"field": "inventory_turnover", "display_name": "存货周转率", "display_type": "ratio"},
            {"field": "receivable_turnover", "display_name": "应收账款周转率", "display_type": "ratio"},
        ],
        "auto_secondary_axis": True,
        "scale_threshold": 100,
    },
    "dupont": {
        "preferred_chart": "dual_axis_line",
        "x_field": "period",
        "series": [
            {"field": "roe", "display_name": "ROE", "display_type": "percent", "axis": "primary"},
            {"field": "net_margin", "display_name": "净利率", "display_type": "percent", "axis": "primary"},
            {"field": "asset_turnover", "display_name": "总资产周转率", "display_type": "ratio", "axis": "secondary"},
            {"field": "equity_multiplier", "display_name": "权益乘数", "display_type": "ratio", "axis": "secondary"},
        ],
        "formula_hint": "ROE ≈ 净利率 × 总资产周转率 × 权益乘数",
    },
    "valuation": {
        "preferred_chart": "metric_cards",
        "x_field": "period",
        "series": [
            {"field": "pe_ttm", "display_name": "PE(TTM)", "display_type": "ratio"},
            {"field": "pb", "display_name": "PB", "display_type": "ratio"},
            {"field": "ps_ttm", "display_name": "PS(TTM)", "display_type": "ratio"},
            {"field": "pcf_ncf_ttm", "display_name": "PCF(TTM)", "display_type": "ratio"},
            {"field": "market_cap", "display_name": "总市值", "display_type": "currency"},
            {"field": "float_market_cap", "display_name": "流通市值", "display_type": "currency"},
        ],
    },
}


# ── 字段映射：BaoStock → 模块字段 ─────────────────────────────────────────────

def _normalize_profit_row(r: dict) -> dict:
    period = r.get("stat_date") or ""
    return {
        "period": period,
        "roe": _safe_float(r.get("roe_avg")),
        "gross_margin": _safe_float(r.get("gross_margin")),
        "net_margin": _safe_float(r.get("net_margin")),
        "net_profit": _safe_float(r.get("net_profit")),
        "net_profit_parent": _safe_float(r.get("net_profit")),
        "eps_ttm": _safe_float(r.get("eps_ttm")),
        "revenue": _safe_float(r.get("mb_revenue")),
        "total_share": _safe_float(r.get("total_share")),
        "float_share": _safe_float(r.get("liqa_share")),
        "source": "baostock_profit",
    }


def _normalize_growth_row(r: dict) -> dict:
    # Phase 6T-E 修复：BaoStock YOYNI=净利润同比、YOYPNI=归母净利润同比。
    # 此前 yoy_ni 被错误标注为 revenue_yoy（营收同比），已移除该误标字段；
    # BaoStock growth 表不提供营收同比，不得伪造。
    period = r.get("stat_date") or ""
    return {
        "period": period,
        "net_profit_yoy": _safe_float(r.get("yoy_ni")),          # YOYNI = 净利润同比
        "net_profit_parent_yoy": _safe_float(r.get("yoy_pni")),  # YOYPNI = 归母净利润同比
        "eps_yoy": _safe_float(r.get("yoy_eps")),
        "equity_yoy": _safe_float(r.get("yoy_equity")),
        "asset_yoy": _safe_float(r.get("yoy_asset")),
        "source": "baostock_growth",
    }


def _normalize_balance_row(r: dict) -> dict:
    period = r.get("stat_date") or ""
    debt_ratio = _safe_float(r.get("liability_to_asset"))
    equity_multiplier = _safe_float(r.get("asset_to_equity"))
    return {
        "period": period,
        "current_ratio": _safe_float(r.get("current_ratio")),
        "quick_ratio": _safe_float(r.get("quick_ratio")),
        "cash_ratio": _safe_float(r.get("cash_ratio")),
        "debt_ratio": debt_ratio,
        "equity_multiplier": equity_multiplier,
        "source": "baostock_balance",
    }


def _normalize_operation_row(r: dict) -> dict:
    period = r.get("stat_date") or ""
    return {
        "period": period,
        "asset_turnover": _safe_float(r.get("asset_turn_ratio")),
        "inventory_turnover": _safe_float(r.get("inv_turn_ratio")),
        "receivable_turnover": _safe_float(r.get("nr_turn_ratio")),
        "ca_turn_ratio": _safe_float(r.get("ca_turn_ratio")),
        "source": "baostock_operation",
    }


def _normalize_cashflow_row(r: dict) -> dict:
    period = r.get("stat_date") or ""
    return {
        "period": period,
        "ocf_to_np": _safe_float(r.get("cfo_to_np")),
        "ocf_to_revenue": _safe_float(r.get("cfo_to_gr")),
        "cashflow_revenue_ratio": _safe_float(r.get("cfo_to_or")),
        "source": "baostock_cashflow",
    }


def _normalize_dupont_row(r: dict) -> dict:
    period = r.get("stat_date") or ""
    return {
        "period": period,
        "roe": _safe_float(r.get("dupont_roe")),
        "net_margin": _safe_float(r.get("dupont_nitogr")),
        "asset_turnover": _safe_float(r.get("dupont_at")),
        "equity_multiplier": _safe_float(r.get("dupont_am")),
        "dupont_npi": _safe_float(r.get("dupont_npi")),
        "dupont_tax": _safe_float(r.get("dupont_tax")),
        "dupont_int": _safe_float(r.get("dupont_int")),
        "source": "baostock_dupont",
    }


_MODULE_NORMALIZERS = {
    "profitability": _normalize_profit_row,
    "growth": _normalize_growth_row,
    "solvency": _normalize_balance_row,
    "operation_capability": _normalize_operation_row,
    "cashflow_quality": _normalize_cashflow_row,
    "dupont": _normalize_dupont_row,
}

_MODULE_BAOSTOCK_TABLE = {
    "profitability": "profit",
    "growth": "growth",
    "solvency": "balance",
    "operation_capability": "operation",
    "cashflow_quality": "cash_flow",
    "dupont": "dupont",
}


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _detect_period_type(rows: list[dict]) -> str:
    """根据 period 字段识别数据周期类型（委托后端权威分类器）。"""
    from app.services.company_v2_period_classifier import classify_rows_period_type
    return classify_rows_period_type(rows)


def _expected_period_list(period_type: str, start_year: int, end_year: int) -> list[str]:
    """生成截至今天应已披露的报告期列表（不含未来期）。"""
    today_str = date.today().isoformat()
    quarter_ends = ("03-31", "06-30", "09-30", "12-31")
    out: list[str] = []
    for year in range(start_year, end_year + 1):
        if period_type == "annual":
            candidates = [f"{year}-12-31"]
        else:
            candidates = [f"{year}-{q}" for q in quarter_ends]
        out.extend(p for p in candidates if p < today_str)
    return out


def _compute_history_coverage(
    rows: list[dict],
    *,
    period_type: str,
    start_year: int,
    end_year: int,
) -> dict[str, Any]:
    """计算历史覆盖情况（Phase 6T-E：missing_periods 真实计算，不含未来报告期）。"""
    periods = sorted(set(r.get("period") or "" for r in rows if r.get("period")))
    start_period = periods[0] if periods else ""
    end_period = periods[-1] if periods else ""

    if period_type in ("annual", "quarterly"):
        expected = _expected_period_list(period_type, start_year, end_year)
    else:
        expected = []
    expected_count = len(expected) if expected else len(periods)
    period_set = set(periods)
    missing = [p for p in expected if p not in period_set]

    return {
        "start_period": start_period,
        "end_period": end_period,
        "periods_count": len(periods),
        "expected_periods_count": expected_count,
        "missing_periods": missing[:40],
        "history_truncated": len(period_set) < expected_count,
    }


def _all_quarters_from_year(start_year: int) -> list[tuple[int, int]]:
    """生成从 start_year 至今所有季度的 (year, quarter) 列表，降序。"""
    today = date.today()
    cur_year, cur_month = today.year, today.month
    cur_quarter = (cur_month - 1) // 3 + 1
    result: list[tuple[int, int]] = []
    year, quarter = cur_year, cur_quarter
    while year >= start_year:
        result.append((year, quarter))
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1
    return result


# ── 主服务函数 ───────────────────────────────────────────────────────────────

async def fetch_module_history(
    ts_code: str,
    module_key: str,
    *,
    start_year: int,
    end_year: int | None = None,
    period: str = "quarterly",   # "annual" | "quarterly" | "all"
) -> dict[str, Any]:
    """
    获取单个模块的全历史数据行。

    Parameters:
        ts_code:    Tushare 格式股票代码 e.g. "601686.SH"
        module_key: 财务模块名称
        start_year: 起始年份（从上市年份开始）
        end_year:   截止年份（默认当前年）
        period:     "annual" 仅年报 | "quarterly" 所有季度 | "all"

    Returns:
        {
          "provider": str,
          "module_key": str,
          "period_type": str,
          "rows": list,
          "latest": dict,
          "history": list,
          "data_success": bool,
          "history_coverage": dict,
          "chart_contract": dict,
        }
    """
    if end_year is None:
        end_year = date.today().year

    table_key = _MODULE_BAOSTOCK_TABLE.get(module_key)
    if not table_key:
        return _empty_module_result(module_key, start_year, end_year)

    normalizer = _MODULE_NORMALIZERS.get(module_key)
    if not normalizer:
        return _empty_module_result(module_key, start_year, end_year)

    # 获取数据（Phase 6T-E1: 批量接口，消除逐季 N+1）
    raw_rows: list[dict] = []
    aux_profit_rows: list[dict] = []
    data_success = False
    try:
        from app.datasource.baostock_client import baostock_client
        all_data = await baostock_client.get_financial_history_bulk(
            ts_code,
            start_year=start_year,
            end_year=end_year,
            mode="annual" if period == "annual" else "quarterly",
        )
        table_rows = all_data.get(table_key, [])
        raw_rows = table_rows
        if module_key == "growth":
            aux_profit_rows = all_data.get("profit") or []
        data_success = bool(raw_rows)
    except Exception as e:
        log.warning("history_financial_provider [%s/%s] BaoStock failed: %s", ts_code, module_key, e)

    return _build_module_history_from_rows(
        module_key,
        raw_rows,
        ts_code=ts_code,
        start_year=start_year,
        end_year=end_year,
        period=period,
        data_success=data_success,
        aux_profit_rows=aux_profit_rows,
    )


def _build_module_history_from_rows(
    module_key: str,
    raw_rows: list[dict],
    *,
    ts_code: str,
    start_year: int,
    end_year: int,
    period: str,
    data_success: bool,
    aux_profit_rows: list[dict] | None = None,
) -> dict[str, Any]:
    """Normalize one BaoStock table into the CompanyV2 history contract."""
    from app.services.company_v2_period_classifier import enrich_row, is_valid_period

    table_key = _MODULE_BAOSTOCK_TABLE.get(module_key)
    normalizer = _MODULE_NORMALIZERS.get(module_key)
    if not table_key or not normalizer:
        return _empty_module_result(module_key, start_year, end_year)

    normalized: list[dict] = []
    for r in raw_rows:
        try:
            norm = normalizer(r)
            if norm.get("period") and is_valid_period(str(norm["period"])):
                normalized.append(norm)
        except Exception as ex:
            log.debug("normalize error [%s]: %s", module_key, ex)

    # 去重（同一 period 只保留一条）
    seen_periods: set[str] = set()
    deduped: list[dict] = []
    for row in normalized:
        p = row.get("period") or ""
        if p not in seen_periods:
            seen_periods.add(p)
            deduped.append(row)

    # 过滤到 start_year
    filtered: list[dict] = [
        r for r in deduped
        if r.get("period") and str(r["period"])[:4].isdigit() and int(str(r["period"])[:4]) >= start_year
    ]

    # 按 period 过滤：只取年末（annual）或全部季度
    if period == "annual":
        filtered = [r for r in filtered if (r.get("period") or "").endswith("12-31")]

    # 升序排列（图表用）
    filtered.sort(key=lambda r: r.get("period") or "")

    # Phase 6T-E: growth 模块补充绝对值（来自 profit 表，字段口径为主营业务收入/净利润）
    if module_key == "growth" and aux_profit_rows:
        by_period: dict[str, dict] = {}
        for pr in aux_profit_rows:
            p = str(pr.get("stat_date") or "")
            if p:
                by_period[p] = pr
        for row in filtered:
            src = by_period.get(str(row.get("period") or ""))
            if src:
                row["main_business_revenue"] = _safe_float(src.get("mb_revenue"))
                row["net_profit"] = _safe_float(src.get("net_profit"))

    # Phase 6T-E: 行级口径注入（report_year/quarter/report_period_type/value_basis/source_provider）
    for row in filtered:
        enrich_row(
            row,
            module_key=module_key,
            source_table=table_key,
            source_provider="baostock",
            requested_period=period,
        )

    period_type = _detect_period_type(filtered)
    if period == "annual" and filtered:
        period_type = "annual"

    history_coverage = _compute_history_coverage(
        filtered, period_type=period_type, start_year=start_year, end_year=end_year
    )

    # 同时确定 point_in_time（只有1行）
    if len(filtered) == 1:
        final_period_type = "point_in_time"
    else:
        final_period_type = period_type

    latest = filtered[-1] if filtered else {}

    return {
        "provider": "baostock",
        "module_key": module_key,
        "period_type": final_period_type,
        "rows": filtered,
        "latest": latest,
        "history": filtered,
        "source_fields": {
            "baostock_table": table_key,
            "ts_code": ts_code,
        },
        "data_success": data_success and bool(filtered),
        "history_coverage": history_coverage,
        "chart_contract": _CHART_CONTRACTS.get(module_key, {}),
    }


async def fetch_all_modules_history(
    ts_code: str,
    *,
    start_year: int,
    end_year: int | None = None,
    period: str = "quarterly",
    valid_quarters: list[tuple[int, int]] | None = None,
    stats_out: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    一次性获取所有财务模块的全历史数据（并行）。

    Returns:
        {
          "profitability": {...},
          "growth": {...},
          "cashflow_quality": {...},
          "solvency": {...},
          "operation_capability": {...},
          "dupont": {...},
        }
    """
    if end_year is None:
        end_year = date.today().year

    modules = list(_MODULE_BAOSTOCK_TABLE.keys())
    quarter_sig = ",".join(f"{y}Q{q}" for y, q in (valid_quarters or [])) or "full"

    if period == "quarterly":
        try:
            from app.services.company_v2_snapshot_cache_service import (
                company_v2_snapshot_cache_service as cache,
            )
            cached_modules: dict[str, dict[str, Any]] = {}
            for module_key in modules:
                key = cache.make_key(
                    "quarterly_normalized", ts_code, module_key,
                    str(start_year), str(end_year), quarter_sig, "v2",
                )
                cached, hit, _stale, _st = await cache.get(key)
                if not hit or not isinstance(cached, dict) or not cached.get("history"):
                    cached_modules = {}
                    break
                cached_modules[module_key] = cached
            if len(cached_modules) == len(modules):
                if stats_out is not None:
                    stats_out.update({
                        "mode": "quarterly",
                        "requested_start_year": start_year,
                        "effective_start_year": start_year,
                        "end_year": end_year,
                        "provider_calls": 0,
                        "actual_calls": 0,
                        "provider_calls_planned": len(valid_quarters or []) * len(_MODULE_BAOSTOCK_TABLE),
                        "planned_calls": len(valid_quarters or []) * len(_MODULE_BAOSTOCK_TABLE),
                        "calls_by_endpoint": {k: 0 for k in _MODULE_BAOSTOCK_TABLE.values()},
                        "duplicate_calls_avoided": 0,
                        "login_batches": 0,
                        "years_from_cache": len({y for y, _q in (valid_quarters or [])}),
                        "years_fetched": 0,
                        "cache_hit": True,
                        "normalized_cache_hit": True,
                    })
                return cached_modules
        except Exception as exc:
            log.debug("quarterly normalized cache read failed: %s", exc)

    # Phase 6T-E1: 批量接口（分年缓存 + singleflight + 并发≤3），消除逐季 N+1
    try:
        from app.datasource.baostock_client import baostock_client
        aggregate = await baostock_client.get_financial_history_bulk(
            ts_code,
            start_year=start_year,
            end_year=end_year,
            mode="annual" if period == "annual" else "quarterly",
            valid_quarters=valid_quarters,
        )
        if stats_out is not None and isinstance(aggregate.get("_bulk_stats"), dict):
            stats_out.update(aggregate["_bulk_stats"])
    except Exception as exc:
        log.warning("fetch_all_modules_history [%s] BaoStock aggregate failed: %s", ts_code, exc)
        return {mk: _empty_module_result(mk, start_year, end_year) for mk in modules}

    profit_rows = aggregate.get("profit") or []
    output: dict[str, dict[str, Any]] = {}
    for module_key in modules:
        table_key = _MODULE_BAOSTOCK_TABLE[module_key]
        rows = aggregate.get(table_key) or []
        output[module_key] = _build_module_history_from_rows(
            module_key,
            rows if isinstance(rows, list) else [],
            ts_code=ts_code,
            start_year=start_year,
            end_year=end_year,
            period=period,
            data_success=bool(rows),
            aux_profit_rows=profit_rows if module_key == "growth" and isinstance(profit_rows, list) else None,
        )
        if period == "quarterly" and output[module_key].get("history"):
            try:
                from app.services.company_v2_snapshot_cache_service import (
                    company_v2_snapshot_cache_service as cache,
                )
                key = cache.make_key(
                    "quarterly_normalized", ts_code, module_key,
                    str(start_year), str(end_year), quarter_sig, "v2",
                )
                await cache.set(
                    key,
                    {
                        **output[module_key],
                        "schema_version": "phase6te2-quarterly-normalized-v2",
                        "provider": "baostock",
                        "period": period,
                    },
                    ttl=3 * 24 * 3600,
                )
            except Exception as exc:
                log.debug("quarterly normalized cache set failed: %s", exc)
    return output


def _empty_module_result(module_key: str, start_year: int, end_year: int) -> dict[str, Any]:
    return {
        "provider": "baostock",
        "module_key": module_key,
        "period_type": "unknown",
        "rows": [],
        "latest": {},
        "history": [],
        "source_fields": {},
        "data_success": False,
        "history_coverage": {
            "start_period": "",
            "end_period": "",
            "periods_count": 0,
            "expected_periods_count": 0,
            "missing_periods": [],
            "history_truncated": True,
        },
        "chart_contract": _CHART_CONTRACTS.get(module_key, {}),
    }
