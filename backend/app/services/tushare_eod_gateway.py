"""Grounded Tushare EOD projection for public company pages and stock research.

Only the approved stock_basic, daily, daily_basic, fina_indicator and explicitly
mapped index_daily endpoints are reachable here. The gateway never calls news or
web-scraping providers and never returns SDK payloads, credentials or headers.
"""
from __future__ import annotations

import asyncio
import math
import re
from datetime import date, datetime
from typing import Any, Awaitable, Callable

import pandas as pd

from app.datasource.tushare_client import (
    TushareAuthError,
    TushareError,
    TushareRateLimitError,
    _to_ts_code,
    tushare_client,
)
from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service


_FRESH_TTL_SECONDS = 15 * 60
_STALE_TTL_SECONDS = 60 * 60
_PERMISSION_PATTERN = re.compile(r"40203|permission|权限|积分", re.IGNORECASE)
_CREDENTIAL_PATTERN = re.compile(r"token|credential|未初始化|认证|无效", re.IGNORECASE)
_NETWORK_PATTERN = re.compile(r"timeout|timed out|超时|network|connection|连接|remote", re.IGNORECASE)
_HTTP_PATTERN = re.compile(r"http|status\s*[45]\d\d", re.IGNORECASE)


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "item"):
        try:
            return _clean_value(value.item())
        except (TypeError, ValueError):
            return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _date_text(value: Any) -> str | None:
    clean = str(_clean_value(value) or "").strip()
    if len(clean) == 8 and clean.isdigit():
        return f"{clean[:4]}-{clean[4:6]}-{clean[6:]}"
    return clean or None


def _fact(value: Any, *, unit: str | None, as_of: str | None, freshness: str) -> dict[str, Any] | None:
    value = _clean_value(value)
    if value is None or value == "":
        return None
    return {
        "value": value,
        "unit": unit,
        "as_of": as_of,
        "source": "tushare",
        "source_status": "verified",
        "freshness": freshness,
        "field_availability": "available",
        "reason_code": None,
    }


def _latest_row(frame: pd.DataFrame, date_field: str) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("provider result is not a table")
    if frame.empty:
        raise ValueError("empty result")
    if date_field not in frame.columns:
        raise KeyError(f"missing required date field: {date_field}")
    ordered = frame.sort_values(date_field, ascending=False)
    return ordered.iloc[0].to_dict()


def _module(endpoint: str, row: dict[str, Any], date_field: str, fields: dict[str, str | None], freshness: str) -> dict[str, Any]:
    as_of = _date_text(row.get(date_field))
    facts = {
        name: fact
        for name, unit in fields.items()
        if (fact := _fact(row.get(name), unit=unit, as_of=as_of, freshness=freshness)) is not None
    }
    if not facts:
        raise KeyError("no approved fields in provider result")
    return {
        "status": "fulfilled",
        "endpoint": endpoint,
        "source": "tushare",
        "source_status": "verified",
        "as_of": as_of,
        "freshness": freshness,
        "fields": facts,
        "field_availability": {name: name in facts for name in fields},
        "reason_code": None,
        "warnings": [],
    }


def _safe_failure(endpoint: str, exc: Exception) -> dict[str, Any]:
    message = str(exc)
    if isinstance(exc, TushareRateLimitError):
        category, reason = "network", "RATE_LIMITED"
    elif isinstance(exc, TushareAuthError) and _PERMISSION_PATTERN.search(message):
        category, reason = "permission", "PROVIDER_PERMISSION_DENIED"
    elif isinstance(exc, TushareAuthError) or _CREDENTIAL_PATTERN.search(message):
        category, reason = "credential", "PROVIDER_CREDENTIAL_ERROR"
    elif isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError)) or _NETWORK_PATTERN.search(message):
        category, reason = "network", "PROVIDER_NETWORK_ERROR"
    elif _HTTP_PATTERN.search(message):
        category, reason = "http", "PROVIDER_HTTP_ERROR"
    elif isinstance(exc, (KeyError, TypeError)):
        category, reason = "schema", "PROVIDER_SCHEMA_ERROR"
    elif isinstance(exc, ValueError) or "empty" in message.lower() or "空数据" in message:
        category, reason = "empty_result", "DATA_NOT_AVAILABLE"
    else:
        category, reason = "schema", "PROVIDER_SCHEMA_ERROR"
    return {
        "status": "unavailable",
        "endpoint": endpoint,
        "source": "tushare",
        "source_status": category,
        "as_of": None,
        "freshness": "unavailable",
        "fields": {},
        "field_availability": {},
        "reason_code": reason,
        "warnings": [],
    }


class TushareEodGateway:
    def __init__(self, client: Any = None) -> None:
        self.client = client or tushare_client

    async def _run(self, endpoint: str, call: Callable[[], Awaitable[pd.DataFrame]], normalizer: Callable[[pd.DataFrame], dict[str, Any]]) -> dict[str, Any]:
        try:
            return normalizer(await call())
        except Exception as exc:
            return _safe_failure(endpoint, exc)

    async def get_company_snapshot(
        self,
        market: str,
        symbol: str,
        *,
        index_ts_code: str | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        market = str(market or "").upper()
        symbol = str(symbol or "").strip()
        if market != "CN" or not re.fullmatch(r"\d{6}", symbol):
            return self._response(market, symbol, {}, reason_code="UNSUPPORTED_SECURITY")
        ts_code = _to_ts_code(market, symbol)
        cache_key = company_v2_snapshot_cache_service.make_company_key(
            "tushare_eod", market, symbol, version="v1"
        )
        if use_cache:
            try:
                cached, cache_status, _ = await company_v2_snapshot_cache_service.get_swr(cache_key)
                if cache_status in {"fresh", "stale"} and isinstance(cached, dict):
                    result = dict(cached)
                    result["cache_status"] = cache_status
                    return result
            except Exception:
                pass

        tasks = {
            "profile": self._run(
                "stock_basic", lambda: self.client.get_stock_basic(ts_code=ts_code),
                lambda df: _module("stock_basic", _latest_row(df, "list_date"), "list_date", {
                    "name": None, "fullname": None, "exchange": None, "industry": None,
                    "list_date": None, "list_status": None,
                }, "reference_data"),
            ),
            "quote": self._run(
                "daily", lambda: self.client.get_daily(ts_code),
                lambda df: _module("daily", _latest_row(df, "trade_date"), "trade_date", {
                    "open": "CNY", "high": "CNY", "low": "CNY", "close": "CNY",
                    "pre_close": "CNY", "change": "CNY", "pct_chg": "%",
                    "vol": "lot", "amount": "CNY_thousand",
                }, "latest_available_eod"),
            ),
            "valuation": self._run(
                "daily_basic", lambda: self.client.get_daily_basic(ts_code),
                lambda df: _module("daily_basic", _latest_row(df, "trade_date"), "trade_date", {
                    "close": "CNY", "pe": "multiple", "pe_ttm": "multiple", "pb": "multiple",
                    "ps": "multiple", "ps_ttm": "multiple", "dv_ratio": "%", "dv_ttm": "%",
                    "turnover_rate": "%", "turnover_rate_f": "%", "volume_ratio": "multiple",
                    "total_mv": "CNY_10k", "circ_mv": "CNY_10k",
                }, "latest_available_eod"),
            ),
            "financial": self._run(
                "fina_indicator", lambda: self.client.get_fina_indicator(ts_code),
                lambda df: _module("fina_indicator", _latest_row(df, "end_date"), "end_date", {
                    "eps": "CNY_per_share", "bps": "CNY_per_share", "roe": "%", "roe_waa": "%",
                    "roa": "%", "roic": "%", "grossprofit_margin": "%", "netprofit_margin": "%",
                    "current_ratio": "multiple", "quick_ratio": "multiple", "debt_to_assets": "%",
                    "assets_turn": "multiple", "inv_turn": "multiple", "ar_turn": "multiple",
                    "netprofit_yoy": "%", "tr_yoy": "%", "or_yoy": "%",
                }, "reported_period"),
            ),
        }
        if index_ts_code:
            tasks["index_comparison"] = self._run(
                "index_daily", lambda: self.client.get_index_daily(index_ts_code),
                lambda df: _module("index_daily", _latest_row(df, "trade_date"), "trade_date", {
                    "close": "index_point", "change": "index_point", "pct_chg": "%",
                }, "latest_available_eod"),
            )
        keys = list(tasks)
        values = await asyncio.gather(*(tasks[key] for key in keys))
        result = self._response(market, symbol, dict(zip(keys, values)))
        if result["fulfillment"] != "unavailable":
            try:
                await company_v2_snapshot_cache_service.set_swr(
                    cache_key, result, fresh_ttl=_FRESH_TTL_SECONDS, stale_ttl=_STALE_TTL_SECONDS
                )
            except Exception:
                pass
        return result

    @staticmethod
    def _response(market: str, symbol: str, modules: dict[str, Any], reason_code: str | None = None) -> dict[str, Any]:
        available = [module for module in modules.values() if module.get("status") == "fulfilled"]
        if available and len(available) == len(modules):
            fulfillment = "fulfilled"
        elif available:
            fulfillment = "partial"
        else:
            fulfillment = "unavailable"
        dates = [module.get("as_of") for module in available if module.get("as_of")]
        return {
            "ok": bool(available),
            "market": market,
            "symbol": symbol,
            "fulfillment": fulfillment,
            "reason_code": reason_code or (None if available else "DATA_NOT_AVAILABLE"),
            "source": "tushare",
            "as_of": max(dates) if dates else None,
            "freshness": "latest_available_eod_not_realtime",
            "modules": modules,
            "field_availability": {key: module.get("status") == "fulfilled" for key, module in modules.items()},
            "warnings": ["盘后数据可能延迟；本响应不包含实时或分钟行情。"],
            "cache_status": "miss",
            "fallback_providers_used": [],
        }


tushare_eod_gateway = TushareEodGateway()
