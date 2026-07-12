#!/usr/bin/env python3
"""
scripts/probe_baostock_valuation.py — BaoStock 估值字段 Smoke Test（Phase 6N-7A）

验证 BaoStock query_history_k_data_plus 是否能提供 peTTM / pbMRQ / psTTM / pcfNcfTTM。

用法：
    uv run python scripts/probe_baostock_valuation.py --symbols 600519.SH,000725.SZ,601686.SH
    uv run python scripts/probe_baostock_valuation.py --symbols 600519.SH --days 5

输出：
  每只股票最近 N 个交易日的估值数据表。
  如果字段为空字符串或 "--"，表示 BaoStock 无此字段数据。

BaoStock 字段说明：
  peTTM       市盈率 TTM（滚动12月）
  pbMRQ       市净率 MRQ（最近一季）
  psTTM       市销率 TTM
  pcfNcfTTM   市现率 TTM（经营现金流）
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime
import baostock as bs


# ── suppress BaoStock login/logout console spam ───────────────────────────────

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


def _safe(v) -> str:
    if v is None:
        return "—"
    s = str(v).strip()
    return s if s and s not in ("None", "null", "nan", "--", "") else "—"


def probe_stock(ts_code: str, days: int) -> list[dict]:
    """Query BaoStock k-data with valuation fields for one stock."""
    bs_code = _to_bs_code(ts_code)
    today   = datetime.date.today()
    start   = today - datetime.timedelta(days=max(days * 2, 30))

    with _quiet():
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM",
            start_date=start.strftime("%Y-%m-%d"),
            end_date=today.strftime("%Y-%m-%d"),
            frequency="d",
            adjustflag="3",
        )

    rows = []
    while rs.error_code == "0" and rs.next():
        data = rs.get_row_data()
        row  = dict(zip(rs.fields, data))
        rows.append(row)

    return rows[-days:] if rows else []


def _col_width(rows: list[dict], key: str, header: str) -> int:
    vals = [_safe(r.get(key)) for r in rows] + [header]
    return max(len(v) for v in vals)


def print_table(ts_code: str, rows: list[dict]) -> None:
    print(f"\n{'='*64}")
    print(f"  {ts_code}  ({len(rows)} rows)")
    print(f"{'='*64}")

    if not rows:
        print("  [NO DATA — BaoStock returned empty for this symbol]")
        return

    cols = [
        ("date",       "Date"),
        ("close",      "Close"),
        ("peTTM",      "PE(TTM)"),
        ("pbMRQ",      "PB(MRQ)"),
        ("psTTM",      "PS(TTM)"),
        ("pcfNcfTTM",  "PCF(TTM)"),
    ]

    widths = [max(len(h), _col_width(rows, k, h)) for k, h in cols]

    header  = "  " + "  ".join(h.ljust(w) for (_, h), w in zip(cols, widths))
    divider = "  " + "  ".join("-" * w for w in widths)

    print(header)
    print(divider)
    for r in rows:
        line = "  " + "  ".join(_safe(r.get(k)).ljust(w) for (k, _), w in zip(cols, widths))
        print(line)

    # Summary
    print()
    last = rows[-1]
    for key, label in [("peTTM", "PE(TTM)"), ("pbMRQ", "PB(MRQ)"),
                        ("psTTM", "PS(TTM)"), ("pcfNcfTTM", "PCF(TTM)")]:
        v = _safe(last.get(key))
        status = "✓ available" if v != "—" else "✗ missing / empty"
        print(f"  {label:12s}: {v:>10s}  [{status}]")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Probe BaoStock valuation fields (peTTM/pbMRQ/psTTM/pcfNcfTTM)",
    )
    p.add_argument("--symbols", required=True,
                   help="Comma-separated ts_codes, e.g. 600519.SH,000725.SZ")
    p.add_argument("--days", type=int, default=5,
                   help="Number of recent trading days to display (default: 5)")
    args = p.parse_args()

    ts_codes = [s.strip() for s in args.symbols.split(",") if s.strip()]

    print(f"\n=== BaoStock Valuation Field Probe ===")
    print(f"  symbols: {', '.join(ts_codes)}")
    print(f"  days:    {args.days}")
    print(f"  fields:  date, close, peTTM, pbMRQ, psTTM, pcfNcfTTM")

    with _quiet():
        login_res = bs.login()
    if login_res.error_code != "0":
        print(f"\nERROR: BaoStock login failed: {login_res.error_msg}")
        sys.exit(1)

    print(f"  BaoStock login: OK\n")

    summary = {}
    for ts_code in ts_codes:
        try:
            rows = probe_stock(ts_code, args.days)
            print_table(ts_code, rows)
            last = rows[-1] if rows else {}
            summary[ts_code] = {
                "rows":       len(rows),
                "peTTM_ok":   _safe(last.get("peTTM")) != "—",
                "pbMRQ_ok":   _safe(last.get("pbMRQ")) != "—",
                "close":      _safe(last.get("close")),
                "peTTM":      _safe(last.get("peTTM")),
                "pbMRQ":      _safe(last.get("pbMRQ")),
            }
        except Exception as exc:
            print(f"\n  ERROR [{ts_code}]: {exc}")
            summary[ts_code] = {"error": str(exc)}

    with _quiet():
        bs.logout()

    # Final summary table
    print(f"\n{'='*64}")
    print("  SUMMARY — peTTM / pbMRQ availability")
    print(f"{'='*64}")
    print(f"  {'Symbol':15s}  {'Close':>10s}  {'peTTM':>10s}  {'pbMRQ':>10s}  {'PE ok':>6s}  {'PB ok':>6s}")
    print(f"  {'-'*15}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*6}  {'-'*6}")
    for sym, s in summary.items():
        if "error" in s:
            print(f"  {sym:15s}  ERROR: {s['error']}")
        else:
            pe_ok = "✓" if s.get("peTTM_ok") else "✗"
            pb_ok = "✓" if s.get("pbMRQ_ok") else "✗"
            print(f"  {sym:15s}  {s.get('close','—'):>10s}  {s.get('peTTM','—'):>10s}  {s.get('pbMRQ','—'):>10s}  {pe_ok:>6s}  {pb_ok:>6s}")

    print(f"\n  Conclusion:")
    any_pe = any(s.get("peTTM_ok") for s in summary.values() if "error" not in s)
    any_pb = any(s.get("pbMRQ_ok") for s in summary.values() if "error" not in s)
    if any_pe:
        print("  ✓ peTTM available from BaoStock — can supplement PE(TTM) coverage")
    else:
        print("  ✗ peTTM NOT available from BaoStock — need Tushare daily_basic or AkShare")
    if any_pb:
        print("  ✓ pbMRQ available from BaoStock — can supplement PB coverage")
    else:
        print("  ✗ pbMRQ NOT available from BaoStock — need Tushare daily_basic or AkShare")
    print()


if __name__ == "__main__":
    main()
