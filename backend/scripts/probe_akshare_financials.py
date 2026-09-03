#!/usr/bin/env python3
"""
scripts/probe_akshare_financials.py — AKShare 三大报表字段 Probe（Phase 6N-7B）

主源：东方财富 EM 接口（stock_profit_sheet_by_report_em 等）
备源：新浪 stock_financial_report_sina

输出每个接口的 rows/columns/latest_period/key_fields_found/key_fields_missing。

用法：
    uv run python scripts/probe_akshare_financials.py --symbols 600519.SH,000725.SZ,601686.SH
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.providers.akshare_provider import _direct_connect

# ── Sina 中文列名 → core_schema mapping ──────────────────────────────────────

SINA_PROFIT_MAP = {
    "营业总收入":               "revenue",
    "营业收入":                 "operating_income",
    "营业成本":                 "operating_cost",
    "营业利润":                 "operating_profit",
    "净利润":                   "net_profit",
    "归属于母公司所有者的净利润": "net_profit_parent",
}
SINA_BALANCE_MAP = {
    "资产总计":                     "total_assets",
    "负债合计":                     "total_liabilities",
    "所有者权益(或股东权益)合计":    "total_equity",
    "归属于母公司股东权益合计":      "parent_equity",
    "流动资产合计":                 "current_assets",
    "流动负债合计":                 "current_liabilities",
}
SINA_CASHFLOW_MAP = {
    "经营活动产生的现金流量净额": "operating_cashflow",
    "投资活动产生的现金流量净额": "investing_cashflow",
    "筹资活动产生的现金流量净额": "financing_cashflow",
}

# EM 接口列名（英文 API 字段）
EM_PROFIT_MAP = {
    "TOTAL_OPERATE_INCOME": "revenue",
    "OPERATE_INCOME":       "operating_income",
    "OPERATE_COST":         "operating_cost",
    "OPERATE_PROFIT":       "operating_profit",
    "NETPROFIT":            "net_profit",
    "PARENT_NETPROFIT":     "net_profit_parent",
}
EM_BALANCE_MAP = {
    "TOTAL_ASSETS":              "total_assets",
    "TOTAL_LIABILITIES":         "total_liabilities",
    "TOTAL_EQUITY":              "total_equity",
    "TOTAL_PARENT_EQUITY":       "parent_equity",
    "TOTAL_CURRENT_ASSETS":      "current_assets",
    "TOTAL_CURRENT_LIAB":        "current_liabilities",
}
EM_CASHFLOW_MAP = {
    "NETCASH_OPERATE":  "operating_cashflow",
    "NETCASH_INVEST":   "investing_cashflow",
    "NETCASH_FINANCE":  "financing_cashflow",
}


def _to_sina_code(ts_code: str) -> str:
    code, ex = ts_code.split(".", 1)
    return f"{ex.lower()}{code}"


def _to_em_code(ts_code: str) -> str:
    code, ex = ts_code.split(".", 1)
    return f"{ex.upper()}{code}"


def _probe_interface(label: str, fn, colmap: dict, date_col_candidates: list[str]) -> dict:
    """Run one interface, return probe result dict."""
    t0 = time.monotonic()
    try:
        with _direct_connect():
            df = fn()
        elapsed_ms = int((time.monotonic() - t0) * 1000)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        msg = repr(exc).lower()
        rc = ("PROVIDER_TIMEOUT" if "timeout" in msg
              else "NETWORK_UNAVAILABLE" if any(k in msg for k in ("connection", "proxy", "remote"))
              else "PROVIDER_EMPTY")
        return {"status": "failed", "reason_code": rc, "elapsed_ms": elapsed_ms,
                "error": str(exc)[:150]}

    if df is None or len(df) == 0:
        return {"status": "empty", "reason_code": "PROVIDER_EMPTY", "elapsed_ms": elapsed_ms}

    cols = set(df.columns)
    latest = df.iloc[0]
    date_col = next((c for c in date_col_candidates if c in cols), None)
    found, missing, samples = [], [], {}
    for src, norm in colmap.items():
        if src in cols:
            found.append(norm)
            samples[norm] = (src, latest.get(src))
        else:
            missing.append((norm, src, "COLUMN_RENAMED"))
    return {
        "status": "ok", "elapsed_ms": elapsed_ms,
        "rows_count": len(df), "columns_count": len(df.columns),
        "latest_period": str(latest.get(date_col, "?")) if date_col else "?",
        "key_fields_found": found, "key_fields_missing": missing,
        "samples": samples,
    }


def _print_result(name: str, res: dict) -> None:
    print(f"\n  [{name}]")
    print(f"    status={res['status']}  elapsed_ms={res['elapsed_ms']}", end="")
    if res["status"] != "ok":
        print(f"  reason_code={res.get('reason_code')}  error={res.get('error','')}")
        return
    print(f"  rows={res['rows_count']}  cols={res['columns_count']}  latest_period={res['latest_period']}")
    print(f"    key_fields_found ({len(res['key_fields_found'])}):")
    for norm, (src, val) in res["samples"].items():
        print(f"      {norm:22s} ← {src:20s} = {val}")
    if res["key_fields_missing"]:
        print(f"    key_fields_missing:")
        for norm, src, rc in res["key_fields_missing"]:
            print(f"      {norm:22s} (expected column: {src})  [{rc}]")


def main() -> None:
    p = argparse.ArgumentParser(description="Probe AKShare financial statement interfaces")
    p.add_argument("--symbols", required=True)
    p.add_argument("--out-json", default="", help="Write structured probe result JSON")
    args = p.parse_args()
    ts_codes = [s.strip() for s in args.symbols.split(",") if s.strip()]
    all_results: dict[str, dict] = {}

    import akshare as ak

    print("\n=== AKShare Financial Statement Probe ===")
    print(f"  symbols: {', '.join(ts_codes)}")

    for ts_code in ts_codes:
        sina_code = _to_sina_code(ts_code)
        em_code   = _to_em_code(ts_code)
        print(f"\n{'='*70}\n  {ts_code}\n{'='*70}")

        # EM primary
        em_specs = [
            ("EM profit_sheet_by_report",  lambda: ak.stock_profit_sheet_by_report_em(symbol=em_code),   EM_PROFIT_MAP,   ["REPORT_DATE"]),
            ("EM balance_sheet_by_report", lambda: ak.stock_balance_sheet_by_report_em(symbol=em_code),  EM_BALANCE_MAP,  ["REPORT_DATE"]),
            ("EM cash_flow_sheet_by_report", lambda: ak.stock_cash_flow_sheet_by_report_em(symbol=em_code), EM_CASHFLOW_MAP, ["REPORT_DATE"]),
        ]
        # Sina fallback
        sina_specs = [
            ("Sina 利润表",     lambda: ak.stock_financial_report_sina(stock=sina_code, symbol="利润表"),     SINA_PROFIT_MAP,   ["报告日"]),
            ("Sina 资产负债表", lambda: ak.stock_financial_report_sina(stock=sina_code, symbol="资产负债表"), SINA_BALANCE_MAP,  ["报告日"]),
            ("Sina 现金流量表", lambda: ak.stock_financial_report_sina(stock=sina_code, symbol="现金流量表"), SINA_CASHFLOW_MAP, ["报告日"]),
        ]

        sym_results: dict[str, dict] = {}
        for (em_name, em_fn, em_map, em_dc), (sina_name, sina_fn, sina_map, sina_dc) in zip(em_specs, sina_specs):
            res = _probe_interface(em_name, em_fn, em_map, em_dc)
            _print_result(em_name, res)
            sym_results[em_name] = {k: v for k, v in res.items() if k != "df"}
            if res["status"] != "ok":
                res2 = _probe_interface(sina_name, sina_fn, sina_map, sina_dc)
                _print_result(sina_name, res2)
                sym_results[sina_name] = {k: v for k, v in res2.items() if k != "df"}
        all_results[ts_code] = sym_results

    print()

    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({
                "provider": "akshare",
                "interfaces": "EM report sheets (primary) + Sina reports (fallback)",
                "cache_hit": False,
                "symbols": all_results,
            }, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"  JSON → {out}")


if __name__ == "__main__":
    main()
