"""
app/services/company_v2_history_service.py — Full-History Financial Dashboard Service（Phase 6T-B）

职责：
1. 聚合从上市年份至今的全历史财务数据
2. 为每个模块提供 latest（最新快照）和 history（历史序列）
3. 支持 period=annual|quarterly|all 参数
4. 支持 start_year / end_year 参数
5. 支持缓存（annual TTL 7d，quarterly TTL 3d）
6. 支持 force_refresh
7. 不破坏现有 latest snapshot API

安全原则：
- 不泄露 local_path / token / secret
- 不提供投资建议（不生成买入/卖出/目标价等）
- 不访问 aicaibao
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date
from typing import Any

from app.datasource.history_financial_provider import fetch_all_modules_history
from app.services.company_v2_period_classifier import resolve_quarterly_window
from app.services.company_v2_stock_basic_service import (
    get_default_start_year,
    get_stock_basic,
)

log = logging.getLogger(__name__)

_CACHE_TTL_ANNUAL = 7 * 24 * 3600    # 7 天
_CACHE_TTL_QUARTERLY = 3 * 24 * 3600  # 3 天


def _ts_code(symbol: str) -> str:
    """将6位股票代码（CN市场）转为 Tushare 格式。"""
    if "." in symbol:
        return symbol
    if symbol.startswith(("6", "5", "9")):
        return f"{symbol}.SH"
    elif symbol.startswith(("0", "3", "2")):
        return f"{symbol}.SZ"
    elif symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    return f"{symbol}.SH"


async def build_company_history_dashboard(
    market: str,
    symbol: str,
    *,
    period: str = "quarterly",   # "annual" | "quarterly" | "all"
    start_year: int | None = None,
    end_year: int | None = None,
    force_refresh: bool = False,
    include_stock_basic: bool = True,
) -> dict[str, Any]:
    """
    构建全历史财务仪表盘数据。

    Parameters:
        market:       市场（目前仅支持 CN）
        symbol:       股票代码（6位或含交易所后缀）
        period:       数据周期："annual" | "quarterly" | "all"
        start_year:   起始年份（默认从上市年份）
        end_year:     截止年份（默认当前年）
        force_refresh:是否强制刷新（跳过缓存）

    Returns:
        {
          "market": "CN",
          "symbol": "601686",
          "ts_code": "601686.SH",
          "period": "quarterly",
          "start_year": 2016,
          "end_year": 2026,
          "start_year_status": "from_list_date",
          "stock_basic": {...},
          "modules": {
            "profitability": {
              "history": [...],
              "latest": {...},
              "period_type": "quarterly",
              "chart_contract": {...},
              "history_coverage": {...},
              "data_success": bool,
            },
            ...
          },
          "data_success_count": N,
          "generated_at": "2026-07-10",
          "disclaimer": "数据来源：公开数据源聚合...",
        }
    """
    t_total = time.perf_counter()
    ts = _ts_code(symbol)
    today_year = date.today().year
    if end_year is None:
        end_year = today_year

    # Step 1: 获取股票基本信息（确定上市年份）
    t0 = time.perf_counter()
    stock_basic: dict[str, Any] = {}
    if include_stock_basic or start_year is None:
        try:
            stock_basic = await get_stock_basic(symbol, force_refresh=force_refresh)
        except Exception as e:
            log.warning("get_stock_basic [%s] failed: %s", symbol, e)
    stock_basic_latency_ms = int((time.perf_counter() - t0) * 1000)

    if start_year is None:
        computed_start, start_status = get_default_start_year(stock_basic)
        start_year = computed_start
        if period != "annual":
            window = resolve_quarterly_window(date.today(), years=5)
            start_year = window["start_year"]
            end_year = window["end_year"]
            valid_quarters = window["valid_quarters"]
            start_status = "recent_5_complete_years_default"
        else:
            valid_quarters = None
    else:
        start_status = "explicit"
        if period != "annual":
            valid_quarters = [
                (year, quarter)
                for year in range(start_year, end_year + 1)
                for quarter in (1, 2, 3, 4)
                if f"{year}-{('03-31','06-30','09-30','12-31')[quarter - 1]}" < date.today().isoformat()
            ]
        else:
            valid_quarters = None

    # Phase 6T-E2: cache key must use the resolved quarterly window, not the
    # pre-resolution None/default values.
    from app.services.company_v2_snapshot_cache_service import (
        company_v2_snapshot_cache_service,
    )
    quarter_sig = ",".join(f"{y}Q{q}" for y, q in (valid_quarters or [])) or "annual"
    cache_key = company_v2_snapshot_cache_service.make_key(
        "history", ts, "v6te2", period, str(start_year), str(end_year), quarter_sig
    )
    cached, hit, _stale, _status = await company_v2_snapshot_cache_service.get(
        cache_key, force_refresh=force_refresh
    )
    if hit and isinstance(cached, dict) and cached.get("modules"):
        cached_perf = dict(cached.get("performance_summary") or {})
        cached_perf["cache_hit"] = True
        cached_perf["provider_calls"] = 0
        cached_perf["actual_calls"] = 0
        cached_perf["login_batches"] = 0
        cached_perf["total_latency_ms"] = int((time.perf_counter() - t_total) * 1000)
        cached["performance_summary"] = cached_perf
        return cached

    # Step 2: 获取全历史财务数据（所有模块，批量接口 + 分年缓存）
    t0 = time.perf_counter()
    modules_data: dict[str, dict] = {}
    provider_stats: dict[str, Any] = {}
    try:
        modules_data = await fetch_all_modules_history(
            ts,
            start_year=start_year,
            end_year=end_year,
            period=period if period != "all" else "quarterly",
            valid_quarters=valid_quarters,
            stats_out=provider_stats,
        )
    except Exception as e:
        log.warning("fetch_all_modules_history [%s] failed: %s", ts, e)
    provider_latency_ms = int((time.perf_counter() - t0) * 1000)

    # Step 3: 统计成功模块数
    data_success_count = sum(
        1 for v in modules_data.values() if v.get("data_success")
    )

    # Step 4: 构建 modules 结构 + Phase 6T-E 审计/图表契约/行业适用性
    t0 = time.perf_counter()
    from app.services.company_v2_chart_contract_validator import validate_chart_contract
    from app.services.company_v2_history_completeness_audit import (
        audit_module_history,
        build_history_quality,
    )
    from app.services.company_v2_industry_metric_applicability import (
        build_module_applicability,
        infer_accounting_type,
    )

    accounting_type = infer_accounting_type(stock_basic.get("industry"), symbol)
    list_date = stock_basic.get("list_date") or ""

    clean_modules: dict[str, Any] = {}
    history_rows_total = 0
    for mk, mdata in modules_data.items():
        history_rows = mdata.get("history", [])
        history_rows_total += len(history_rows)
        contract = mdata.get("chart_contract", {})
        contract_fields = [
            s.get("field") or ""
            for s in (contract.get("series") or [])
            if isinstance(s, dict)
        ]
        applicability = build_module_applicability(mk, contract_fields, accounting_type)
        module_audit = audit_module_history(
            mk, mdata,
            list_date=list_date,
            requested_period=period if period != "all" else "quarterly",
            start_year=start_year,
            end_year=end_year,
        )
        chart_validation = validate_chart_contract(
            mk, contract,
            rows=history_rows,
            period_type=mdata.get("period_type", "unknown"),
            not_applicable_fields=applicability["not_applicable_fields"],
        )
        clean_modules[mk] = {
            "history": history_rows,
            "latest": mdata.get("latest", {}),
            "period_type": mdata.get("period_type", "unknown"),
            "chart_contract": contract,
            "history_coverage": mdata.get("history_coverage", {}),
            "history_quality": build_history_quality(module_audit),
            "chart_contract_validation": {
                "valid": chart_validation["valid"],
                "effective_chart": chart_validation["effective_chart"],
                "issues": chart_validation["issues"],
                "warnings": chart_validation["warnings"],
            },
            "metric_applicability": {
                "accounting_type": accounting_type,
                "not_applicable_fields": applicability["not_applicable_fields"],
            },
            "data_success": mdata.get("data_success", False),
            "provider": mdata.get("provider", "baostock"),
            "provider_status": mdata.get("provider_status"),
            "reason_code": mdata.get("reason_code"),
            "errors": mdata.get("errors", []),
        }
    validation_latency_ms = int((time.perf_counter() - t0) * 1000)

    # Step 5: 历史范围语义（不得夸大为"上市以来"）
    history_range = _build_history_range(
        clean_modules,
        list_date=list_date,
        list_date_status=stock_basic.get("list_date_status") or "unknown",
        period=period,
    )

    payload = {
        "market": market.upper(),
        "symbol": symbol,
        "ts_code": ts,
        "period": period,
        "start_year": start_year,
        "end_year": end_year,
        "start_year_status": start_status,
        "quarterly_window": {
            "valid_quarters": valid_quarters or [],
            "expected_periods": [
                f"{y}-{('03-31','06-30','09-30','12-31')[q - 1]}"
                for y, q in (valid_quarters or [])
            ],
            "excluded_future_periods": [],
        } if period != "annual" else None,
        "accounting_type": accounting_type,
        "stock_basic": stock_basic,
        "modules": clean_modules,
        "data_success_count": data_success_count,
        **history_range,
        "generated_at": date.today().isoformat(),
        "disclaimer": (
            "数据来源：公开数据源聚合、CNINFO 公告文件及系统计算。"
            "行情可能存在延迟，财务数据最终以交易所及巨潮资讯披露文件为准。"
            "本页面不构成投资建议。"
        ),
    }

    # Step 6: performance summary（真实测量，不做凭感觉优化）
    t0 = time.perf_counter()
    try:
        response_size_bytes = len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        response_size_bytes = -1
    serialization_latency_ms = int((time.perf_counter() - t0) * 1000)
    payload["performance_summary"] = {
        "total_latency_ms": int((time.perf_counter() - t_total) * 1000),
        "provider_latency_ms": provider_latency_ms,
        "stock_basic_latency_ms": stock_basic_latency_ms,
        "normalization_latency_ms": provider_latency_ms,  # 归一化在 provider 内联执行
        "validation_latency_ms": validation_latency_ms,
        "serialization_latency_ms": serialization_latency_ms,
        "response_size_bytes": response_size_bytes,
        "history_rows_total": history_rows_total,
        "baostock_aggregate_calls": 1 if modules_data else 0,
        # Phase 6T-E1: 真实外部调用统计（来自批量接口）
        "provider_calls": provider_stats.get("provider_calls", 0),
        "provider_calls_planned": provider_stats.get("provider_calls_planned", provider_stats.get("planned_calls", 0)),
        "planned_calls": provider_stats.get("planned_calls", 0),
        "actual_calls": provider_stats.get("actual_calls", provider_stats.get("provider_calls", 0)),
        "calls_by_endpoint": provider_stats.get("calls_by_endpoint", {}),
        "duplicate_calls_avoided": provider_stats.get("duplicate_calls_avoided", 0),
        "login_batches": provider_stats.get("login_batches", 0),
        "years_from_cache": provider_stats.get("years_from_cache", 0),
        "years_fetched": provider_stats.get("years_fetched", 0),
        "years_completed": provider_stats.get("years_completed", []),
        "valid_quarters_total": provider_stats.get("valid_quarters_total", len(valid_quarters or [])),
        "provider_history_clamped_to_2007": provider_stats.get("provider_history_clamped_to_2007", False),
        "status": provider_stats.get("status"),
        "reason_code": provider_stats.get("reason_code"),
        "errors": provider_stats.get("errors", []),
        "cache_hit": False,
    }
    if data_success_count > 0:
        ttl = _CACHE_TTL_ANNUAL if period == "annual" else _CACHE_TTL_QUARTERLY
        try:
            await company_v2_snapshot_cache_service.set(cache_key, payload, ttl=ttl)
        except Exception as exc:
            log.debug("history dashboard cache set failed: %s", exc)
    return payload


def _build_history_range(
    modules: dict[str, Any],
    *,
    list_date: str,
    list_date_status: str,
    period: str,
) -> dict[str, Any]:
    """
    Phase 6T-E: 根据真实 coverage 生成历史范围语义。
    不得仅因请求参数 start_year=list_year 就标记为完整覆盖。
    """
    starts: list[str] = []
    ends: list[str] = []
    max_rows = 0
    truncated_any = False
    for mdata in modules.values():
        cov = mdata.get("history_coverage") or {}
        if cov.get("start_period"):
            starts.append(cov["start_period"])
        if cov.get("end_period"):
            ends.append(cov["end_period"])
        max_rows = max(max_rows, len(mdata.get("history") or []))
        if cov.get("history_truncated"):
            truncated_any = True

    start_period = min(starts) if starts else ""
    end_period = max(ends) if ends else ""

    list_year: int | None = None
    if list_date and len(list_date) >= 4 and list_date[:4].isdigit():
        list_year = int(list_date[:4])

    is_full_since_listing = False
    if list_year and start_period:
        try:
            # 上市当年或次年即有数据，视为覆盖上市以来
            is_full_since_listing = int(start_period[:4]) <= list_year + 1 and not truncated_any
        except ValueError:
            is_full_since_listing = False

    if not start_period:
        label = "暂无历史数据"
        truncation_reason = "PROVIDER_EMPTY"
    elif list_year is None or list_date_status == "unknown":
        label = "历史数据范围未知"
        truncation_reason = "LIST_DATE_UNKNOWN"
    elif is_full_since_listing:
        label = "上市以来"
        truncation_reason = ""
    elif max_rows <= 8:
        label = f"最近 {max_rows} 期"
        truncation_reason = "PROVIDER_HISTORY_LIMIT"
    else:
        label = f"当前数据源覆盖 {start_period[:4]}—{end_period[:4]} 年"
        truncation_reason = "PROVIDER_HISTORY_LIMIT"

    return {
        "history_range_label": label,
        "history_start_period": start_period,
        "history_end_period": end_period,
        "history_is_full_since_listing": is_full_since_listing,
        "history_truncated": truncated_any or not is_full_since_listing,
        "truncation_reason": truncation_reason,
    }


async def get_module_history(
    market: str,
    symbol: str,
    module_key: str,
    *,
    period: str = "quarterly",
    start_year: int | None = None,
    end_year: int | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    获取单个模块的全历史数据（轻量接口）。
    """
    ts = _ts_code(symbol)
    today_year = date.today().year
    if end_year is None:
        end_year = today_year

    if start_year is None:
        try:
            stock_basic = await get_stock_basic(symbol)
            start_year, _ = get_default_start_year(stock_basic)
        except Exception:
            start_year = today_year - 10

    from app.datasource.history_financial_provider import fetch_module_history
    try:
        result = await fetch_module_history(
            ts, module_key,
            start_year=start_year,
            end_year=end_year,
            period=period,
        )
    except Exception as e:
        log.warning("get_module_history [%s/%s] failed: %s", ts, module_key, e)
        result = {
            "module_key": module_key,
            "history": [],
            "latest": {},
            "period_type": "unknown",
            "data_success": False,
        }

    return {
        "market": market.upper(),
        "symbol": symbol,
        "ts_code": ts,
        "module_key": module_key,
        "period": period,
        "start_year": start_year,
        "end_year": end_year,
        **result,
    }
