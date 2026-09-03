#!/usr/bin/env python3
"""
scripts/probe_akshare_quote.py — AKShare 行情/市值字段 Probe（Phase 6N-7B）

验证 stock_zh_a_spot_em 能否提供 latest_price / market_cap / circ_mv /
turnover_rate / pe_ttm / pb 等字段，并输出中文列名 → core_schema mapping。

用法：
    uv run python scripts/probe_akshare_quote.py --symbols 600519.SH,000725.SZ,601686.SH
    uv run python scripts/probe_akshare_quote.py --symbols 600519.SH \
        --out-json docs/artifacts/phase6n7b_akshare_market_cap_probe.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.providers.akshare_provider import _direct_connect

# 中文列名 → core_schema 字段 mapping（stock_zh_a_spot_em）
SPOT_EM_COLUMN_MAP = {
    "最新价":   "latest_price",
    "涨跌幅":   "change_pct",       # percent, needs /100
    "成交量":   "volume",           # 手 (lots of 100 shares)
    "成交额":   "amount",           # 元
    "总市值":   "market_cap",       # 元
    "流通市值": "circ_mv",          # 元
    "换手率":   "turnover_rate",    # percent
    "市盈率-动态": "pe",            # dynamic PE
    "市净率":   "pb",
    "60日涨跌幅": None,
    "代码":     "__symbol__",
    "名称":     "__name__",
}

KEY_FIELDS = ["latest_price", "change_pct", "volume", "amount",
              "market_cap", "circ_mv", "turnover_rate", "pe", "pb"]


def main() -> None:
    p = argparse.ArgumentParser(description="Probe AKShare stock_zh_a_spot_em")
    p.add_argument("--symbols", required=True)
    p.add_argument("--out-json", default="", help="Write structured probe result JSON")
    args = p.parse_args()
    ts_codes = [s.strip() for s in args.symbols.split(",") if s.strip()]
    plain_codes = {t.split(".")[0]: t for t in ts_codes}

    print("\n=== AKShare Quote Probe (stock_zh_a_spot_em) ===")
    print(f"  symbols: {', '.join(ts_codes)}")

    import akshare as ak

    t0 = time.monotonic()
    try:
        with _direct_connect():
            df = ak.stock_zh_a_spot_em()
        elapsed_ms = int((time.monotonic() - t0) * 1000)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        rc = "PROVIDER_TIMEOUT" if "timeout" in repr(exc).lower() else "NETWORK_UNAVAILABLE"
        print(f"\n  status=FAILED  reason_code={rc}  elapsed_ms={elapsed_ms}")
        print(f"  error: {exc!r}")
        if args.out_json:
            _write_json(args.out_json, {
                "provider": "akshare", "interface_name": "stock_zh_a_spot_em",
                "status": "failed", "reason_code": rc, "elapsed_ms": elapsed_ms,
                "error": str(exc)[:200], "symbols": ts_codes,
                "recommended_action": "spot_em(push2) blocked in this network; "
                                      "rely on BaoStock kline + computed market_cap",
            })
        sys.exit(1)

    cols = list(df.columns)
    print(f"\n  provider:       akshare")
    print(f"  interface_name: stock_zh_a_spot_em")
    print(f"  status:         ok")
    print(f"  elapsed_ms:     {elapsed_ms}")
    print(f"  rows_count:     {len(df)}")
    print(f"  columns_count:  {len(cols)}")
    print(f"  available_columns: {cols}")

    matched = {cn: norm for cn, norm in SPOT_EM_COLUMN_MAP.items()
               if norm and cn in cols and not norm.startswith("__")}
    missing = {cn: norm for cn, norm in SPOT_EM_COLUMN_MAP.items()
               if norm and cn not in cols and not norm.startswith("__")}
    print(f"\n  matched_columns ({len(matched)}):")
    for cn, norm in matched.items():
        print(f"    {cn:12s} → {norm}")
    if missing:
        print(f"  MISSING columns (COLUMN_RENAMED?):")
        for cn, norm in missing.items():
            print(f"    {cn:12s} → {norm}")

    # Per-symbol normalized samples
    per_symbol: dict[str, dict] = {}
    for plain, ts_code in plain_codes.items():
        row = df[df["代码"] == plain]
        print(f"\n  ── {ts_code} ──")
        if row.empty:
            print("    NOT FOUND in spot_em (PROVIDER_EMPTY)")
            per_symbol[ts_code] = {"status": "empty", "reason_code": "PROVIDER_EMPTY"}
            continue
        r = row.iloc[0]
        normalized: dict[str, float | None] = {}
        for cn, norm in matched.items():
            v = r.get(cn)
            note = ""
            if norm == "change_pct":
                note = f"  (normalized: {float(v)/100:.6f})" if v == v else ""
            elif norm == "turnover_rate":
                note = "  (percent)"
            elif norm in ("market_cap", "circ_mv"):
                note = f"  ({float(v)/1e8:.1f} 亿元)" if v == v else ""
            elif norm == "volume":
                note = "  (手)"
            print(f"    {norm:15s} = {v}{note}")
            try:
                normalized[norm] = None if v != v else float(v)
            except (TypeError, ValueError):
                normalized[norm] = None
        per_symbol[ts_code] = {"status": "ok", "normalized_fields": normalized}

    # Summary
    found   = [f for f in KEY_FIELDS if f in matched.values()]
    missing_kf = [f for f in KEY_FIELDS if f not in matched.values()]
    print(f"\n  ── SUMMARY ──")
    print(f"  key_fields_found:   {found}")
    print(f"  key_fields_missing: {missing_kf}")
    print()

    if args.out_json:
        _write_json(args.out_json, {
            "provider": "akshare", "interface_name": "stock_zh_a_spot_em",
            "status": "ok", "elapsed_ms": elapsed_ms,
            "rows_count": len(df), "columns_count": len(cols),
            "matched_columns": matched,
            "missing_columns": missing,
            "key_fields_found": found, "key_fields_missing": missing_kf,
            "symbols": per_symbol,
            "cache_hit": False,
            "recommended_action": (
                "wire spot_em into coverage merge as lowest-priority quote source"
                if found else "investigate COLUMN_RENAMED"),
        })


def _write_json(path: str, payload: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                   encoding="utf-8")
    print(f"  JSON → {out}")


if __name__ == "__main__":
    main()
