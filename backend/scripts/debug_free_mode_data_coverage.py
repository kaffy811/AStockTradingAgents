#!/usr/bin/env python3
"""
scripts/debug_free_mode_data_coverage.py — Free Mode 数据覆盖率诊断脚本

对指定股票运行完整数据诊断，输出 JSON 和 CSV。
直接调用 BaoStockClient，不经过 FastAPI，适用于离线调试和数据覆盖率验证。

Usage:
    uv run python scripts/debug_free_mode_data_coverage.py --symbols 601686,000725,600519
    uv run python scripts/debug_free_mode_data_coverage.py --symbols 601686 --out-dir docs/artifacts
    uv run python scripts/debug_free_mode_data_coverage.py --symbols 600519 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# ── BaoStock 方法映射 ──────────────────────────────────────────────────────────

# (module_key, baostock_method_name)
_BAOSTOCK_PROBES: list[tuple[str, str]] = [
    ("profit",      "get_profit_data"),
    ("growth",      "get_growth_data"),
    ("balance",     "get_balance_data"),
    ("operation",   "get_operation_data"),
    ("cash_flow",   "get_cash_flow_data"),
    ("dupont",      "get_dupont_data"),
]


def _to_ts_code(symbol: str) -> str:
    """将纯 6 位代码转换为 ts_code 格式。"""
    symbol = symbol.strip()
    if "." in symbol:
        return symbol  # already formatted
    if symbol.startswith(("6", "5", "9")):
        return f"{symbol}.SH"
    return f"{symbol}.SZ"


def _count_non_null_fields(row: dict) -> list[str]:
    """返回 row 中值不为 None 的字段名（排除 ts_code/pub_date/stat_date）。"""
    skip = {"ts_code", "pub_date", "stat_date"}
    return [k for k, v in row.items() if v is not None and k not in skip]


async def _probe_symbol(ts_code: str) -> list[dict]:
    """
    对单只股票运行所有 BaoStock 数据探针，返回每个 module 的诊断结果。
    """
    from app.datasource.baostock_client import BaoStockClient

    client = BaoStockClient()
    results = []

    for module_key, method_name in _BAOSTOCK_PROBES:
        t0 = time.time()
        try:
            method = getattr(client, method_name)
            rows: list[dict] = await method(ts_code=ts_code)
            elapsed_ms = round((time.time() - t0) * 1000)
            rows_count = len(rows) if rows else 0

            # 收集第一行中非 null 字段作为样本
            if rows:
                non_null_fields = _count_non_null_fields(rows[0])
            else:
                non_null_fields = []

            results.append({
                "module_key":      module_key,
                "provider":        "baostock",
                "rows_count":      rows_count,
                "non_null_fields": non_null_fields,
                "elapsed_ms":      elapsed_ms,
                "status":          "ok" if rows_count > 0 else "empty",
                "error":           None,
            })
        except Exception as exc:
            elapsed_ms = round((time.time() - t0) * 1000)
            results.append({
                "module_key":      module_key,
                "provider":        "baostock",
                "rows_count":      0,
                "non_null_fields": [],
                "elapsed_ms":      elapsed_ms,
                "status":          "failed",
                "error":           f"{type(exc).__name__}: {exc}",
            })

    return results


def _build_summary(ts_code: str, module_results: list[dict]) -> dict:
    ok_count = sum(1 for m in module_results if m["status"] == "ok")
    empty_count = sum(1 for m in module_results if m["status"] == "empty")
    failed_count = sum(1 for m in module_results if m["status"] == "failed")
    total = len(module_results)
    coverage_pct = round(ok_count / total * 100, 1) if total > 0 else 0.0

    return {
        "ts_code":      ts_code,
        "total":        total,
        "ok":           ok_count,
        "empty":        empty_count,
        "failed":       failed_count,
        "coverage_pct": coverage_pct,
        "modules":      module_results,
    }


def _write_json(summary: dict, out_dir: Path) -> Path:
    ts_code_safe = summary["ts_code"].replace(".", "_")
    out_path = out_dir / f"free_mode_coverage_{ts_code_safe}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _write_csv(summaries: list[dict], out_dir: Path) -> Path:
    out_path = out_dir / "free_mode_coverage_summary.csv"
    rows = []
    for s in summaries:
        for m in s["modules"]:
            rows.append({
                "ts_code":         s["ts_code"],
                "module_key":      m["module_key"],
                "provider":        m["provider"],
                "status":          m["status"],
                "rows_count":      m["rows_count"],
                "elapsed_ms":      m["elapsed_ms"],
                "non_null_fields": "|".join(m.get("non_null_fields") or []),
                "error":           m.get("error") or "",
            })
    if not rows:
        return out_path

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out_path


async def _run(symbols: list[str], out_dir: Path, dry_run: bool) -> int:
    """主诊断逻辑，返回退出码（0=有数据, 1=全空）。"""
    summaries: list[dict] = []
    any_ok = False

    for raw_symbol in symbols:
        ts_code = _to_ts_code(raw_symbol.strip())
        print(f"\n[{ts_code}] 开始诊断...", flush=True)

        module_results = await _probe_symbol(ts_code)
        summary = _build_summary(ts_code, module_results)
        summaries.append(summary)

        if summary["ok"] > 0:
            any_ok = True

        # 打印单股摘要
        print(json.dumps({
            "ts_code":      summary["ts_code"],
            "ok":           summary["ok"],
            "empty":        summary["empty"],
            "failed":       summary["failed"],
            "coverage_pct": summary["coverage_pct"],
        }, ensure_ascii=False))

        for m in module_results:
            status_icon = {"ok": "✓", "empty": "○", "failed": "✗"}.get(m["status"], "?")
            fields_preview = ", ".join(m["non_null_fields"][:5]) if m["non_null_fields"] else "-"
            print(
                f"  {status_icon} {m['module_key']:25s} rows={m['rows_count']:3d} "
                f"elapsed={m['elapsed_ms']:5d}ms  fields=[{fields_preview}]"
            )
            if m.get("error"):
                print(f"      ERROR: {m['error']}")

    if not dry_run and summaries:
        out_dir.mkdir(parents=True, exist_ok=True)
        for s in summaries:
            json_path = _write_json(s, out_dir)
            print(f"\n[output] JSON → {json_path}")
        csv_path = _write_csv(summaries, out_dir)
        print(f"[output] CSV  → {csv_path}")
    elif dry_run:
        print("\n[dry-run] 不写入文件。")

    return 0 if any_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Free Mode 数据覆盖率诊断脚本 — 对指定股票运行 BaoStock 数据探针",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--symbols",
        required=True,
        help="逗号分隔的股票代码列表，如 601686,000725,600519",
    )
    parser.add_argument(
        "--out-dir",
        default="docs/artifacts",
        help="输出目录（默认：docs/artifacts）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅运行诊断并打印结果，不写入文件",
    )

    args = parser.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    out_dir = Path(args.out_dir)

    if not symbols:
        print("错误：--symbols 不能为空", file=sys.stderr)
        sys.exit(1)

    exit_code = asyncio.run(_run(symbols=symbols, out_dir=out_dir, dry_run=args.dry_run))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
