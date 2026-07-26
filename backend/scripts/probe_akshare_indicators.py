#!/usr/bin/env python3
"""
scripts/probe_akshare_indicators.py — AKShare 财务指标字段 Probe（Phase 6N-7B）

主源：东方财富 stock_financial_analysis_indicator_em
备源：新浪 stock_financial_analysis_indicator

核心指标（11个）：
  roe / roa / gross_margin / net_margin / debt_ratio / current_ratio /
  revenue_growth / net_profit_growth / asset_turnover / inventory_turnover / ocf_to_np

用法：
    uv run python scripts/probe_akshare_indicators.py --symbols 600519.SH,000725.SZ,601686.SH
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.providers.akshare_provider import _direct_connect

# Sina stock_financial_analysis_indicator 列名 mapping
SINA_INDICATOR_MAP = {
    "净资产收益率(%)":               ("roe",                "percent"),
    "总资产净利润率(%)":             ("roa",                "percent"),
    "销售毛利率(%)":                 ("gross_margin",       "percent"),
    "销售净利率(%)":                 ("net_margin",         "percent"),
    "资产负债率(%)":                 ("debt_ratio",         "percent"),
    "流动比率":                      ("current_ratio",      "ratio"),
    "主营业务收入增长率(%)":         ("revenue_growth",     "percent"),
    "净利润增长率(%)":               ("net_profit_growth",  "percent"),
    "总资产周转率(次)":              ("asset_turnover",     "ratio"),
    "存货周转率(次)":                ("inventory_turnover", "ratio"),
    # 注意：该列虽带 (%) 后缀，实际值已是比率（probe 验证 OCF/NP=0.9558=raw），不除 100
    "经营现金净流量与净利润的比率(%)": ("ocf_to_np",          "ratio"),
}

KEY_FIELDS = [v[0] for v in SINA_INDICATOR_MAP.values()]


def _to_em_code(ts_code: str) -> str:
    code, ex = ts_code.split(".", 1)
    return f"{ex.upper()}{code}"


def _safe_float(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in ("None", "nan", "--", ""):
        return None
    try:
        f = float(s)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def probe_em(ak, ts_code: str) -> dict:
    t0 = time.monotonic()
    try:
        with _direct_connect():
            df = ak.stock_financial_analysis_indicator_em(symbol=_to_em_code(ts_code), indicator="按报告期")
        elapsed_ms = int((time.monotonic() - t0) * 1000)
    except Exception as exc:
        msg = repr(exc).lower()
        rc = ("PROVIDER_TIMEOUT" if "timeout" in msg
              else "NETWORK_UNAVAILABLE" if any(k in msg for k in ("connection", "proxy", "remote"))
              else "PROVIDER_EMPTY")
        return {"status": "failed", "reason_code": rc,
                "elapsed_ms": int((time.monotonic() - t0) * 1000), "error": str(exc)[:120]}
    if df is None or len(df) == 0:
        return {"status": "empty", "reason_code": "PROVIDER_EMPTY", "elapsed_ms": elapsed_ms}
    return {"status": "ok", "elapsed_ms": elapsed_ms, "rows_count": len(df),
            "columns_count": len(df.columns), "columns": list(df.columns), "df": df}


def probe_sina(ak, ts_code: str) -> dict:
    plain = ts_code.split(".")[0]
    t0 = time.monotonic()
    try:
        with _direct_connect():
            df = ak.stock_financial_analysis_indicator(symbol=plain, start_year="2025")
        elapsed_ms = int((time.monotonic() - t0) * 1000)
    except Exception as exc:
        msg = repr(exc).lower()
        rc = ("PROVIDER_TIMEOUT" if "timeout" in msg
              else "NETWORK_UNAVAILABLE" if any(k in msg for k in ("connection", "proxy", "remote"))
              else "PROVIDER_EMPTY")
        return {"status": "failed", "reason_code": rc,
                "elapsed_ms": int((time.monotonic() - t0) * 1000), "error": str(exc)[:120]}
    if df is None or len(df) == 0:
        return {"status": "empty", "reason_code": "PROVIDER_EMPTY", "elapsed_ms": elapsed_ms}

    cols = set(df.columns)
    latest = df.iloc[-1]  # sina sorted ascending by 日期
    found, missing, samples = [], [], {}
    for src, (norm, unit) in SINA_INDICATOR_MAP.items():
        if src in cols:
            raw = _safe_float(latest.get(src))
            val = raw / 100 if (raw is not None and unit == "percent") else raw
            if raw is None:
                missing.append((norm, src, "PROVIDER_EMPTY"))
            else:
                found.append(norm)
                samples[norm] = (src, raw, val)
        else:
            missing.append((norm, src, "COLUMN_RENAMED"))
    return {"status": "ok", "elapsed_ms": elapsed_ms, "rows_count": len(df),
            "columns_count": len(df.columns),
            "latest_period": str(latest.get("日期", "?")),
            "key_fields_found": found, "key_fields_missing": missing, "samples": samples}


def main() -> None:
    p = argparse.ArgumentParser(description="Probe AKShare financial indicator interfaces")
    p.add_argument("--symbols", required=True)
    p.add_argument("--out-json", default="", help="Write structured probe result JSON")
    args = p.parse_args()
    ts_codes = [s.strip() for s in args.symbols.split(",") if s.strip()]
    all_results: dict[str, dict] = {}

    import akshare as ak

    print("\n=== AKShare Financial Indicator Probe ===")
    print(f"  symbols: {', '.join(ts_codes)}")

    for ts_code in ts_codes:
        print(f"\n{'='*70}\n  {ts_code}\n{'='*70}")

        # EM primary
        em = probe_em(ak, ts_code)
        print(f"\n  [EM stock_financial_analysis_indicator_em]")
        if em["status"] == "ok":
            print(f"    status=ok  elapsed_ms={em['elapsed_ms']}  rows={em['rows_count']}  cols={em['columns_count']}")
            print(f"    columns: {em['columns'][:30]}")
        else:
            print(f"    status={em['status']}  reason_code={em.get('reason_code')}  "
                  f"elapsed_ms={em['elapsed_ms']}  error={em.get('error','')}")

        # Sina fallback
        sina = probe_sina(ak, ts_code)
        all_results[ts_code] = {
            "em":   {k: v for k, v in em.items() if k != "df"},
            "sina": sina,
        }
        print(f"\n  [Sina stock_financial_analysis_indicator]")
        if sina["status"] != "ok":
            print(f"    status={sina['status']}  reason_code={sina.get('reason_code')}  error={sina.get('error','')}")
            continue
        print(f"    status=ok  elapsed_ms={sina['elapsed_ms']}  rows={sina['rows_count']}  "
              f"cols={sina['columns_count']}  latest_period={sina['latest_period']}")
        print(f"    key_fields_found ({len(sina['key_fields_found'])}/11):")
        for norm, (src, raw, val) in sina["samples"].items():
            print(f"      {norm:20s} ← {src:26s} raw={raw}  normalized={val}")
        if sina["key_fields_missing"]:
            print(f"    key_fields_missing:")
            for norm, src, rc in sina["key_fields_missing"]:
                print(f"      {norm:20s} (source col: {src})  [{rc}]")

    print()

    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({
                "provider": "akshare",
                "interfaces": "stock_financial_analysis_indicator_em (primary) "
                              "+ stock_financial_analysis_indicator sina (fallback)",
                "cache_hit": False,
                "symbols": all_results,
            }, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"  JSON → {out}")


if __name__ == "__main__":
    main()
