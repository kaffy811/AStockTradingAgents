#!/usr/bin/env python3
"""
scripts/probe_valuation_fields.py — 估值 P0 字段 DataField Smoke Test（Phase 6N-7A）

对 7 个估值核心字段完整输出 DataField（value / status / source / reason_code /
attempted_sources / provider_errors / formula / dependencies）。

检查优先级链：
  Tushare daily_basic (ETL) → BaoStock peTTM/pbMRQ → AkShare → Computed → null+reason_code

用法：
    uv run python scripts/probe_valuation_fields.py --symbols 600519.SH,000725.SZ,601686.SH
    uv run python scripts/probe_valuation_fields.py --symbols 600519.SH --verbose

核心字段（7个）：
  pe / pe_ttm / pb / market_cap / circ_mv / total_share / float_share

TushareProvider 状态：
  - disabled (TOKEN_MISSING) : 无 TUSHARE_TOKEN
  - disabled (PERMISSION_DENIED) : Token 有但 API 拒绝访问
  - available : Token 有且可调用
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime
import io
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import baostock as bs

from app.models.data_field import DataField, DataFieldStatus, ReasonCode
from app.models.core_schema import CORE_FIELDS


# ── Quiet context ─────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _quiet():
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = io.StringIO()
    try:
        yield
    finally:
        sys.stdout, sys.stderr = old_out, old_err


def _to_bs_code(ts_code: str) -> str:
    if "." not in ts_code:
        return f"sh.{ts_code}" if ts_code.startswith(("6", "5")) else f"sz.{ts_code}"
    code, ex = ts_code.split(".", 1)
    return f"{ex.lower()}.{code}"


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in ("None", "null", "nan", "--", ""):
        return None
    try:
        f = float(s)
        return None if f != f else round(f, 6)
    except (TypeError, ValueError):
        return None


# ── DB query ──────────────────────────────────────────────────────────────────

async def _query_etl_daily_basic(ts_code: str) -> dict[str, Any]:
    """Read valuation fields from etl_daily_basic (Tushare ETL)."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return {"__error__": "DATABASE_URL not set"}
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import text
        engine = create_async_engine(
            db_url, echo=False, pool_timeout=5,
            connect_args={"statement_cache_size": 0},
        )
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            result = await asyncio.wait_for(
                session.execute(
                    text("""
                        SELECT trade_date, close, pe, pe_ttm, pb, ps, ps_ttm,
                               total_mv, circ_mv, total_share, float_share,
                               turnover_rate, dv_ratio
                        FROM etl_daily_basic
                        WHERE ts_code = :ts_code
                        ORDER BY trade_date DESC LIMIT 1
                    """),
                    {"ts_code": ts_code},
                ),
                timeout=20.0,
            )
            row = result.mappings().first()
            await engine.dispose()
            if not row:
                return {"__empty__": True}
            d = dict(row)
            # 万元 → 元
            for k in ("total_mv", "circ_mv"):
                if d.get(k) is not None:
                    d[k] = float(d[k]) * 10_000
            return d
    except asyncio.TimeoutError:
        return {"__error__": "DB query timeout (5s)"}
    except Exception as exc:
        return {"__error__": repr(exc)}


# ── BaoStock probe ────────────────────────────────────────────────────────────

def _probe_baostock_sync(ts_code: str) -> dict[str, Any]:
    """Synchronous BaoStock probe for peTTM/pbMRQ/close."""
    bs_code = _to_bs_code(ts_code)
    today   = datetime.date.today()
    start   = today - datetime.timedelta(days=30)
    result: dict[str, Any] = {"__source__": "baostock_kline"}

    with _quiet():
        bs.login()
    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,close,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn",
            start_date=start.strftime("%Y-%m-%d"),
            end_date=today.strftime("%Y-%m-%d"),
            frequency="d",
            adjustflag="3",
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(dict(zip(rs.fields, rs.get_row_data())))
        if rows:
            lat = rows[-1]
            result.update({
                "close":       _safe_float(lat.get("close")),
                "pe_ttm":      _safe_float(lat.get("peTTM")),
                "pb":          _safe_float(lat.get("pbMRQ")),
                "ps_ttm":      _safe_float(lat.get("psTTM")),
                "pcf_ttm":     _safe_float(lat.get("pcfNcfTTM")),
                "turnover":    _safe_float(lat.get("turn")),
                "trade_date":  lat.get("date", ""),
            })
        else:
            result["__empty__"] = True
    except Exception as exc:
        result["__error__"] = repr(exc)
    finally:
        with _quiet():
            bs.logout()
    return result


# ── Tushare availability check ───────────────────────────────────────────────

def _check_tushare() -> dict[str, Any]:
    """Check Tushare token and permission status."""
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        return {
            "enabled": False,
            "reason_code": ReasonCode.TOKEN_MISSING.value,
            "detail": "TUSHARE_TOKEN not set in environment",
        }
    try:
        from app.datasource.tushare_client import TushareAuthError, TushareError
        import tushare as ts
        ts.set_token(token)
        pro = ts.pro_api()
        # Probe with a single-row, low-cost call
        df = pro.daily_basic(ts_code="600519.SH", trade_date="20260704",
                              fields="ts_code,trade_date,pe_ttm,pb,total_mv")
        if df is not None and not df.empty:
            return {
                "enabled": True,
                "reason_code": None,
                "detail": f"daily_basic OK: {len(df)} row(s)",
                "sample": df.to_dict(orient="records")[0] if len(df) > 0 else {},
            }
        return {
            "enabled": False,
            "reason_code": ReasonCode.PROVIDER_EMPTY.value,
            "detail": "daily_basic returned empty DataFrame",
        }
    except Exception as exc:
        err = str(exc)
        if "40001" in err or "权限" in err or "token" in err.lower():
            rc = ReasonCode.PERMISSION_DENIED.value
        else:
            rc = ReasonCode.PROVIDER_EMPTY.value
        return {
            "enabled": False,
            "reason_code": rc,
            "detail": err[:200],
        }


# ── Build DataField for each valuation field ─────────────────────────────────

def _build_fields(
    ts_code: str,
    etl: dict,
    bs_data: dict,
    tushare_status: dict,
) -> dict[str, DataField]:
    """
    Construct DataField for each of the 7 valuation fields using the
    priority chain: ETL (Tushare) → BaoStock → computed → missing.
    """
    fields: dict[str, DataField] = {}

    etl_ok = not etl.get("__empty__") and not etl.get("__error__")
    bs_ok  = not bs_data.get("__empty__") and not bs_data.get("__error__")

    tushare_enabled  = tushare_status["enabled"]
    tushare_miss_rc  = (
        ReasonCode.PERMISSION_DENIED
        if not tushare_enabled and tushare_status.get("reason_code") == ReasonCode.PERMISSION_DENIED.value
        else ReasonCode.TOKEN_MISSING
        if not tushare_enabled
        else ReasonCode.PROVIDER_EMPTY
    )

    def _make(
        field_name: str,
        etl_key: str | None,
        bs_key: str | None,
        unit_mult: float = 1.0,
        formula: str = "",
        deps: list[str] | None = None,
    ) -> DataField:
        spec = CORE_FIELDS.get(field_name)

        # 1. Tushare ETL
        if etl_ok and etl_key and etl.get(etl_key) is not None:
            val = float(etl[etl_key]) * unit_mult
            return DataField.ok(
                field_name, val, "tushare_etl_daily_basic",
                as_of=str(etl.get("trade_date", "")),
                source_priority=1,
            )

        attempted = ["tushare_daily_basic"]
        etl_err = etl.get("__error__", "")
        errors: dict[str, str] = {}
        if etl_err:
            errors["tushare_daily_basic"] = etl_err
        elif not etl_ok:
            errors["tushare_daily_basic"] = (
                tushare_status.get("detail", "PERMISSION_DENIED")
                if not tushare_enabled else "empty"
            )

        # 2. BaoStock
        if bs_key and bs_ok and bs_data.get(bs_key) is not None:
            val = float(bs_data[bs_key]) * unit_mult
            attempted.append("baostock_kline")
            return DataField(
                field_name=field_name,
                value=val,
                status=DataFieldStatus.OK,
                source="baostock_kline",
                source_priority=2,
                as_of=str(bs_data.get("trade_date", "")),
                attempted_sources=attempted,
                provider_errors=errors,
                formula=formula,
                dependencies=deps or [],
            )
        if bs_ok and bs_key:
            attempted.append("baostock_kline")
            bs_err = bs_data.get("__error__", "")
            if bs_err:
                errors["baostock_kline"] = bs_err
            else:
                errors["baostock_kline"] = f"field {bs_key!r} empty in BaoStock kline"
        elif bs_data.get("__empty__"):
            attempted.append("baostock_kline")
            errors["baostock_kline"] = "baostock_kline returned no rows"

        # 3. Computed fallback (only if formula provided)
        if formula and deps:
            return DataField(
                field_name=field_name,
                value=None,
                status=DataFieldStatus.MISSING,
                source="",
                reason_code=ReasonCode.FIELD_MISSING_DEPENDENCY,
                attempted_sources=attempted + ["computed"],
                provider_errors={**errors, "computed": f"dependencies missing: {deps}"},
                formula=formula,
                dependencies=deps,
            )

        # 4. Missing with reason_code
        return DataField(
            field_name=field_name,
            value=None,
            status=DataFieldStatus.MISSING,
            reason_code=tushare_miss_rc,
            attempted_sources=attempted,
            provider_errors=errors,
            formula=formula,
            dependencies=deps or [],
        )

    # pe — not in BaoStock kline
    fields["pe"] = _make("pe_ttm", "pe", None)
    fields["pe_ttm"] = _make(
        "pe_ttm",   "pe_ttm",     "pe_ttm",
        formula="market_cap / ttm_net_profit_parent",
        deps=["market_cap", "ttm_net_profit_parent"],
    )
    fields["pb"] = _make(
        "pb",        "pb",          "pb",
        formula="market_cap / book_value_parent",
        deps=["market_cap", "book_value_parent"],
    )
    fields["market_cap"] = _make(
        "market_cap", "total_mv",  None,
        formula="latest_price * total_share * 10000",
        deps=["latest_price", "total_share"],
    )
    fields["circ_mv"] = _make(
        "market_cap", "circ_mv",   None,
    )
    fields["total_share"] = _make(
        "total_share", "total_share", None,
    )
    fields["float_share"] = _make(
        "float_share", "float_share", None,
    )

    return fields


# ── Pretty print ─────────────────────────────────────────────────────────────

def _status_icon(df: DataField) -> str:
    icons = {
        DataFieldStatus.OK:              "✓",
        DataFieldStatus.COMPUTED:        "◎",
        DataFieldStatus.ESTIMATED:       "~",
        DataFieldStatus.MISSING:         "✗",
        DataFieldStatus.PROVIDER_FAILED: "!",
        DataFieldStatus.DISABLED:        "-",
        DataFieldStatus.STALE:           "~",
    }
    return icons.get(df.status, "?")


def print_field_table(ts_code: str, fields: dict[str, DataField]) -> None:
    print(f"\n{'─'*72}")
    print(f"  {ts_code}  — Valuation Field DataField Report")
    print(f"{'─'*72}")

    header = f"  {'Field':18s} {'St':>2s}  {'Value':>14s}  {'Source':22s}  {'Reason / Formula'}"
    print(header)
    print(f"  {'─'*18} {'──':>2s}  {'─'*14}  {'─'*22}  {'─'*28}")

    for fname, df in fields.items():
        icon  = _status_icon(df)
        val   = f"{df.value:,.4f}" if df.value is not None else "—"
        src   = (df.source or "")[:22]
        extra = ""
        if df.reason_code:
            extra = df.reason_code.value
        elif df.formula:
            extra = f"={df.formula}"[:32]
        print(f"  {fname:18s} {icon:>2s}  {val:>14s}  {src:22s}  {extra}")

    print()
    for fname, df in fields.items():
        if not df.has_value:
            print(f"  [{fname}]")
            print(f"    attempted_sources: {df.attempted_sources}")
            for prov, err in (df.provider_errors or {}).items():
                print(f"    {prov}: {err[:120]}")


# ── Main ─────────────────────────────────────────────────────────────────────

async def _async_main(args: argparse.Namespace) -> None:
    ts_codes = [s.strip() for s in args.symbols.split(",") if s.strip()]

    print(f"\n=== Valuation Field Probe (Phase 6N-7A) ===")
    print(f"  symbols: {', '.join(ts_codes)}")
    print(f"  date:    {datetime.date.today()}\n")

    # ── 1. Tushare status ─────────────────────────────────────────────────
    print("  [Step 1/4] Checking TushareProvider status...")
    t0 = time.monotonic()
    tushare_status = _check_tushare()
    elapsed = time.monotonic() - t0
    icon = "✓" if tushare_status["enabled"] else "✗"
    print(f"  {icon} TushareProvider: enabled={tushare_status['enabled']}  "
          f"reason_code={tushare_status.get('reason_code','—')}  ({elapsed:.1f}s)")
    print(f"    detail: {tushare_status.get('detail','')[:100]}")
    if args.verbose and tushare_status.get("sample"):
        print(f"    sample: {tushare_status['sample']}")

    print()

    for ts_code in ts_codes:
        print(f"  {'─'*60}")
        print(f"  {ts_code}")
        print(f"  {'─'*60}")

        # ── 2. ETL query ─────────────────────────────────────────────────
        print(f"  [Step 2/4] etl_daily_basic query...")
        t0 = time.monotonic()
        try:
            etl = await asyncio.wait_for(_query_etl_daily_basic(ts_code), timeout=8.0)
        except asyncio.TimeoutError:
            etl = {"__error__": "DB timeout 8s"}
        elapsed = time.monotonic() - t0
        etl_ok = not etl.get("__empty__") and not etl.get("__error__")
        print(f"    {'✓' if etl_ok else '✗'} etl_daily_basic: "
              f"{'data found' if etl_ok else etl.get('__error__') or 'empty'}  ({elapsed:.1f}s)")
        if etl_ok and args.verbose:
            for k, v in etl.items():
                if not k.startswith("__"):
                    print(f"      {k}: {v}")

        # ── 3. BaoStock probe ─────────────────────────────────────────────
        print(f"  [Step 3/4] BaoStock kline (peTTM/pbMRQ) probe...")
        t0 = time.monotonic()
        try:
            bs_data = await asyncio.wait_for(
                asyncio.to_thread(_probe_baostock_sync, ts_code),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            bs_data = {"__error__": "BaoStock timeout 15s"}
        elapsed = time.monotonic() - t0
        bs_ok = not bs_data.get("__empty__") and not bs_data.get("__error__")
        print(f"    {'✓' if bs_ok else '✗'} baostock_kline: "
              f"close={bs_data.get('close','—')}  peTTM={bs_data.get('pe_ttm','—')}  "
              f"pbMRQ={bs_data.get('pb','—')}  ({elapsed:.1f}s)")
        if not bs_ok:
            print(f"    error: {bs_data.get('__error__','empty')}")

        # ── 4. Build DataField ────────────────────────────────────────────
        print(f"  [Step 4/4] Building DataField objects...")
        fields = _build_fields(ts_code, etl, bs_data, tushare_status)
        print_field_table(ts_code, fields)

        # Quick summary
        ok_count = sum(1 for df in fields.values() if df.has_value)
        total = len(fields)
        print(f"  Valuation coverage: {ok_count}/{total} fields  ({ok_count/total:.0%})")
        print()


def main() -> None:
    p = argparse.ArgumentParser(
        description="Probe valuation P0 fields with full DataField lineage",
    )
    p.add_argument("--symbols", required=True,
                   help="Comma-separated ts_codes, e.g. 600519.SH,000725.SZ")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Show raw ETL row values")
    args = p.parse_args()

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
