"""
app/etl/loaders.py — Tushare → PostgreSQL ETL 加载器（Phase 2B）

三个公开函数：
  load_stock_basic()
      从 Tushare stock_basic 拉取全市场股票基本信息，批量 upsert 到 etl_stock_basic。

  load_daily_basic_by_trade_date(trade_date)
      按 trade_date 拉取全市场 daily_basic（一次性，非按票循环），
      批量 upsert 到 etl_daily_basic。

  load_fina_indicator_by_period_or_disclosure(end_date=None, ann_date=None)
      按 period 或 ann_date 拉取全市场 fina_indicator，
      批量 upsert 到 etl_fina_indicator。

每个函数返回 LoadResult = {"inserted": n, "updated": n, "skipped": n, "errors": [...]}

设计约束：
  ✅ 按 trade_date / end_date 批量拉取（一次 API 调用）
  ❌ 不允许循环 5000 只股票逐一调用 Tushare
  ✅ 使用 PostgreSQL ON CONFLICT DO UPDATE 批量 upsert
  ✅ ETL_ENABLED=false 时即刻报错（不影响 FastAPI 主服务）
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from app.etl.db import require_etl, get_etl_session, build_upsert_sql
from app.datasource.tushare_client import tushare_client

log = logging.getLogger(__name__)


class LoadResult(TypedDict):
    inserted: int
    updated: int
    skipped: int
    errors: list[str]


def _empty_result() -> LoadResult:
    return {"inserted": 0, "updated": 0, "skipped": 0, "errors": []}


def _safe_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s != "nan" else None


def _safe_num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f  # NaN → None
    except (TypeError, ValueError):
        return None


# ── load_stock_basic ─────────────────────────────────────────────────────────

async def load_stock_basic() -> LoadResult:
    """
    加载全市场 A 股基本信息 → etl_stock_basic。
    使用 Tushare stock_basic（list_status=L 上市中，不过滤停牌）。
    单次 API 调用，一次性获取全部股票。
    """
    require_etl()
    result = _empty_result()

    try:
        df = await tushare_client.get_stock_basic()
    except Exception as exc:
        result["errors"].append(f"Tushare stock_basic 调用失败: {exc}")
        log.error("load_stock_basic 失败: %s", exc)
        return result

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "ts_code":   _safe_str(row.get("ts_code")),
            "symbol":    _safe_str(row.get("symbol")),
            "name":      _safe_str(row.get("name")),
            "area":      _safe_str(row.get("area")),
            "industry":  _safe_str(row.get("industry")),
            "fullname":  _safe_str(row.get("fullname")),
            "enname":    _safe_str(row.get("enname")),
            "market":    _safe_str(row.get("market")),
            "exchange":  _safe_str(row.get("exchange")),
            "list_date": _safe_str(row.get("list_date")),
            "is_hs":     _safe_str(row.get("is_hs")),
        })

    rows = [r for r in rows if r["ts_code"]]  # 过滤无效行

    if not rows:
        result["skipped"] = len(df)
        return result

    sql, rows = build_upsert_sql(
        table="etl_stock_basic",
        rows=rows,
        conflict_cols=["ts_code"],
        update_cols=["symbol", "name", "area", "industry", "fullname",
                     "enname", "market", "exchange", "list_date", "is_hs"],
    )

    try:
        from sqlalchemy import text
        async with await get_etl_session() as session:
            await session.execute(text(sql), rows)
            await session.commit()
        result["inserted"] = len(rows)
        log.info("load_stock_basic: upserted %d rows", len(rows))
    except Exception as exc:
        result["errors"].append(f"DB write 失败: {exc}")
        log.error("load_stock_basic DB write 失败: %s", exc)

    return result


# ── load_daily_basic_by_trade_date ────────────────────────────────────────────

async def load_daily_basic_by_trade_date(trade_date: str) -> LoadResult:
    """
    按交易日期批量加载全市场日频估值/市值 → etl_daily_basic。

    trade_date 格式：YYYYMMDD。
    一次 API 调用获取当日所有股票（不循环）。
    """
    require_etl()
    result = _empty_result()

    try:
        df = await tushare_client.get_daily_basic_by_trade_date(trade_date)
    except Exception as exc:
        result["errors"].append(f"Tushare daily_basic 调用失败 [{trade_date}]: {exc}")
        log.error("load_daily_basic 失败 date=%s: %s", trade_date, exc)
        return result

    rows = []
    for _, row in df.iterrows():
        ts_code = _safe_str(row.get("ts_code"))
        if not ts_code:
            result["skipped"] += 1
            continue
        rows.append({
            "ts_code":       ts_code,
            "trade_date":    _safe_str(row.get("trade_date")) or trade_date,
            "close":         _safe_num(row.get("close")),
            "turnover_rate": _safe_num(row.get("turnover_rate")),
            "volume_ratio":  _safe_num(row.get("volume_ratio")),
            "pe":            _safe_num(row.get("pe")),
            "pe_ttm":        _safe_num(row.get("pe_ttm")),
            "pb":            _safe_num(row.get("pb")),
            "ps":            _safe_num(row.get("ps")),
            "ps_ttm":        _safe_num(row.get("ps_ttm")),
            "dv_ratio":      _safe_num(row.get("dv_ratio")),
            "dv_ttm":        _safe_num(row.get("dv_ttm")),
            "total_share":   _safe_num(row.get("total_share")),
            "float_share":   _safe_num(row.get("float_share")),
            "free_share":    _safe_num(row.get("free_share")),
            "total_mv":      _safe_num(row.get("total_mv")),
            "circ_mv":       _safe_num(row.get("circ_mv")),
        })

    if not rows:
        result["skipped"] += len(df)
        return result

    sql, rows = build_upsert_sql(
        table="etl_daily_basic",
        rows=rows,
        conflict_cols=["ts_code", "trade_date"],
        update_cols=["close", "turnover_rate", "volume_ratio",
                     "pe", "pe_ttm", "pb", "ps", "ps_ttm",
                     "dv_ratio", "dv_ttm", "total_share", "float_share",
                     "free_share", "total_mv", "circ_mv"],
    )

    try:
        from sqlalchemy import text
        async with await get_etl_session() as session:
            await session.execute(text(sql), rows)
            await session.commit()
        result["inserted"] = len(rows)
        log.info("load_daily_basic: trade_date=%s upserted %d rows", trade_date, len(rows))
    except Exception as exc:
        result["errors"].append(f"DB write 失败: {exc}")
        log.error("load_daily_basic DB write 失败 date=%s: %s", trade_date, exc)

    return result


# ── load_fina_indicator_by_period_or_disclosure ───────────────────────────────

async def load_fina_indicator_by_period_or_disclosure(
    end_date: str | None = None,
    ann_date: str | None = None,
) -> LoadResult:
    """
    按报告期（end_date）或披露日（ann_date）批量加载全市场财务指标 → etl_fina_indicator。

    一次 API 调用获取所有股票在该期间的数据（不循环）。
    end_date / ann_date 格式：YYYYMMDD。
    """
    require_etl()
    result = _empty_result()

    if not end_date and not ann_date:
        result["errors"].append("end_date 和 ann_date 至少传一个")
        return result

    try:
        df = await tushare_client.get_fina_indicator_by_period(period=end_date, ann_date=ann_date)
    except Exception as exc:
        result["errors"].append(f"Tushare fina_indicator 调用失败: {exc}")
        log.error("load_fina_indicator 失败: %s", exc)
        return result

    rows = []
    for _, row in df.iterrows():
        ts_code = _safe_str(row.get("ts_code"))
        period_val = _safe_str(row.get("end_date")) or end_date
        if not ts_code or not period_val:
            result["skipped"] += 1
            continue
        rows.append({
            "ts_code":            ts_code,
            "end_date":           period_val,
            "ann_date":           _safe_str(row.get("ann_date")),
            "roe":                _safe_num(row.get("roe")),
            "roa":                _safe_num(row.get("roa")),
            "roic":               _safe_num(row.get("roic")),
            "grossprofit_margin": _safe_num(row.get("grossprofit_margin")),
            "netprofit_margin":   _safe_num(row.get("netprofit_margin")),
            "revenue_yoy":        _safe_num(row.get("or_yoy") or row.get("tr_yoy")),
            "netprofit_yoy":      _safe_num(row.get("netprofit_yoy")),
            "dt_netprofit_yoy":   _safe_num(row.get("dt_netprofit_yoy")),
            "assets_turn":        _safe_num(row.get("assets_turn")),
            "inv_turn":           _safe_num(row.get("inv_turn")),
            "ar_turn":            _safe_num(row.get("ar_turn")),
            "current_ratio":      _safe_num(row.get("current_ratio")),
            "quick_ratio":        _safe_num(row.get("quick_ratio")),
            "debt_to_assets":     _safe_num(row.get("debt_to_assets")),
        })

    if not rows:
        result["skipped"] += len(df)
        return result

    sql, rows = build_upsert_sql(
        table="etl_fina_indicator",
        rows=rows,
        conflict_cols=["ts_code", "end_date"],
        update_cols=["ann_date", "roe", "roa", "roic",
                     "grossprofit_margin", "netprofit_margin",
                     "revenue_yoy", "netprofit_yoy", "dt_netprofit_yoy",
                     "assets_turn", "inv_turn", "ar_turn",
                     "current_ratio", "quick_ratio", "debt_to_assets"],
    )

    try:
        from sqlalchemy import text
        async with await get_etl_session() as session:
            await session.execute(text(sql), rows)
            await session.commit()
        result["inserted"] = len(rows)
        log.info(
            "load_fina_indicator: end_date=%s ann_date=%s upserted %d rows",
            end_date, ann_date, len(rows),
        )
    except Exception as exc:
        result["errors"].append(f"DB write 失败: {exc}")
        log.error("load_fina_indicator DB write 失败: %s", exc)

    return result
