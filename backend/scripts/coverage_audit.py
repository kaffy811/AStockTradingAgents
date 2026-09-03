#!/usr/bin/env python3
"""
scripts/coverage_audit.py — 数据完整性审计 CLI（Phase 6N-6/7）

对指定股票池调用 CoverageAuditService，输出字段级完整率报告。

用法：
    uv run python scripts/coverage_audit.py --symbols 600519,000725,601686
    uv run python scripts/coverage_audit.py --symbols 600519 --trade-date 2024-12-31
    uv run python scripts/coverage_audit.py --symbols 600519 --debug --no-persist
    uv run python scripts/coverage_audit.py --symbols 600519,000725 --out-dir docs/artifacts

输出（out-dir，默认 docs/artifacts）：
    coverage_audit_<YYYY-MM-DD>.json   — 每只股票的完整 CoverageReport
    coverage_audit_<YYYY-MM-DD>.csv    — 汇总行

--debug 模式：
  - 每个阶段独立 timeout，超时不卡死
  - 输出每阶段 start/done/elapsed/status
  - 禁止吞异常（异常直接打印）
  - 输出 quote/valuation/financial/rag 四类 completeness
  - 输出 overall_without_rag

Per-stage timeouts (--debug 模式下生效):
  load_local_fields:   3s
  baostock_supplement: 30s
  rag_diagnostics:     5s
  compute_fields:      3s
  persist_snapshot:    5s
  write_artifacts:     3s
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ── sys.path setup ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Stage result ─────────────────────────────────────────────────────────────

class StepResult:
    def __init__(
        self,
        name: str,
        ok: bool,
        elapsed: float,
        detail: str = "",
        data: Any = None,
    ) -> None:
        self.name    = name
        self.ok      = ok
        self.elapsed = elapsed
        self.detail  = detail
        self.data    = data

    def __str__(self) -> str:
        icon = "✓" if self.ok else "✗"
        return f"    [{icon}] {self.name:25s}  {self.elapsed:5.1f}s  {self.detail}"

    @classmethod
    def failed(cls, name: str, elapsed: float, reason: str) -> "StepResult":
        return cls(name, ok=False, elapsed=elapsed, detail=f"FAILED: {reason}")


# ── Per-stage timeout wrapper ─────────────────────────────────────────────────

async def _run_step(
    name: str,
    coro,
    timeout_s: float,
    *,
    debug: bool = False,
) -> StepResult:
    if debug:
        print(f"    → {name} ...", flush=True)
    t0 = time.monotonic()
    try:
        data = await asyncio.wait_for(coro, timeout=timeout_s)
        elapsed = time.monotonic() - t0
        step = StepResult(name, ok=True, elapsed=elapsed, data=data)
        if debug:
            print(str(step), flush=True)
        return step
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - t0
        step = StepResult.failed(name, elapsed, f"timeout after {timeout_s}s")
        if debug:
            print(str(step), flush=True)
        return step
    except Exception as exc:
        elapsed = time.monotonic() - t0
        detail = repr(exc)
        step = StepResult.failed(name, elapsed, detail)
        if debug:
            print(str(step), flush=True)
        else:
            # In non-debug mode, log but don't raise
            print(f"    [!] {name}: {detail}", file=sys.stderr, flush=True)
        return step


# ── Single-stock audit with per-stage isolation ───────────────────────────────

async def _audit_one_stock(
    ts_code: str,
    trade_date: str,
    *,
    debug: bool = False,
    no_persist: bool = False,
) -> dict[str, Any]:
    """
    Audit one stock with per-stage timeouts.
    Each stage gets its own DB session to avoid shared-session issues.
    Provider network calls are isolated from DB transactions.
    """
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    from app.core.database import AsyncSessionLocal
    from app.models.data_field import ReasonCode

    if debug:
        print(f"\n  ── {ts_code} ──────────────────────────────────────", flush=True)

    steps: list[StepResult] = []
    etl_daily:  dict[str, Any] = {}
    etl_fina:   dict[str, Any] = {}
    bs_quote:   dict[str, Any] = {}
    bs_fina:    dict[str, Any] = {}
    rag_info:   dict[str, Any] = {}
    report_dict: dict[str, Any] = {}

    # ── Stage 1: load ETL (DB) ────────────────────────────────────────────────
    async def _load_etl():
        async with AsyncSessionLocal() as db:
            from app.services.coverage_audit_service import CoverageAuditService
            svc = CoverageAuditService(db, trade_date)
            daily = await svc._fetch_daily_basic(ts_code)
            fina  = await svc._fetch_fina_indicator(ts_code)
            rag   = await svc._fetch_rag_status(ts_code)
        return daily, fina, rag

    s1 = await _run_step("load_local_fields", _load_etl(), 20.0, debug=debug)
    steps.append(s1)
    if s1.ok and s1.data:
        etl_daily, etl_fina, rag_info = s1.data
        tushare_ok = bool(etl_daily or etl_fina)
        if debug:
            print(f"      etl_daily: {'data' if etl_daily else 'empty'} "
                  f"| etl_fina: {'data' if etl_fina else 'empty'} "
                  f"| rag_status: {rag_info.get('rag_status','?')}", flush=True)
    else:
        tushare_ok = False

    # ── Stage 2: BaoStock supplemental (only if ETL empty) ───────────────────
    if not tushare_ok:
        async def _bs_fetch():
            async with AsyncSessionLocal() as db:
                from app.services.coverage_audit_service import CoverageAuditService
                svc = CoverageAuditService(db, trade_date)
                return await svc._fetch_baostock_supplemental(ts_code)

        s2 = await _run_step("baostock_supplement", _bs_fetch(), 35.0, debug=debug)
        steps.append(s2)
        if s2.ok and s2.data:
            bs_quote, bs_fina = s2.data
            if debug:
                n_quote = sum(1 for k, v in bs_quote.items() if v is not None and not k.startswith("__"))
                n_fina  = sum(1 for k, v in bs_fina.items()  if v is not None and not k.startswith("__"))
                print(f"      bs_quote fields: {n_quote}  |  bs_fina fields: {n_fina}", flush=True)
                for k, v in bs_quote.items():
                    if v is not None and not k.startswith("__"):
                        print(f"        quote.{k}: {v}", flush=True)
                for k, v in bs_fina.items():
                    if v is not None and not k.startswith("__"):
                        print(f"        fina.{k}: {v}", flush=True)
    else:
        steps.append(StepResult("baostock_supplement", True, 0.0, "skipped (ETL has data)"))

    # ── Stage 2b: AKShare supplemental (statements + indicators + quote) ─────
    ak_quote: dict[str, Any] = {}
    ak_stmt:  dict[str, Any] = {}
    ak_ind:   dict[str, Any] = {}

    async def _ak_fetch():
        async with AsyncSessionLocal() as db:
            from app.services.coverage_audit_service import CoverageAuditService
            svc = CoverageAuditService(db, trade_date)
            return await svc._fetch_akshare_supplement(ts_code)

    s2b = await _run_step("akshare_supplement", _ak_fetch(), 60.0, debug=debug)
    steps.append(s2b)
    if s2b.ok and s2b.data:
        ak_quote, ak_stmt, ak_ind, ak_meta = s2b.data
        if debug:
            for part, d in (("quote", ak_quote), ("statements", ak_stmt), ("indicators", ak_ind)):
                m = ak_meta.get(part, {})
                n = sum(1 for k, v in d.items() if v is not None and not k.startswith("__"))
                print(f"      ak_{part}: status={m.get('status','?')} "
                      f"fields={n} rc={m.get('reason_code')} "
                      f"({m.get('elapsed_ms', 0)}ms)", flush=True)
                for k, v in d.items():
                    if v is not None and not k.startswith("__"):
                        print(f"        {part}.{k}: {v}", flush=True)

    # ── Stage 3: build CoverageReport ────────────────────────────────────────
    async def _build_report():
        from app.services.coverage_audit_service import (
            CoverageAuditService, CoverageReport, merge_coverage_rows,
        )
        from app.models.data_field import ReasonCode

        merged_daily, merged_fina = merge_coverage_rows(
            etl_daily, etl_fina, bs_quote, bs_fina, ak_quote, ak_stmt, ak_ind,
        )

        tushare_miss_rc = (
            ReasonCode.PROVIDER_EMPTY.value if tushare_ok
            else ReasonCode.PERMISSION_DENIED.value
        )

        # Use a dummy DB session for category building (pure computation)
        cats = {}
        async with AsyncSessionLocal() as db:
            svc = CoverageAuditService(db, trade_date)
            cats["quote"]      = svc._audit_quote(merged_daily, tushare_miss_rc)
            cats["valuation"]  = svc._audit_valuation(merged_daily, tushare_miss_rc)
            cats["income"]     = svc._audit_income(merged_fina, tushare_miss_rc)
            cats["balance"]    = svc._audit_balance(merged_fina, tushare_miss_rc)
            cats["cashflow"]   = svc._audit_cashflow(merged_fina, tushare_miss_rc)
            cats["indicators"] = svc._audit_indicators(merged_fina, tushare_miss_rc)
            cats["rag"]        = svc._audit_rag(rag_info)

        rag_status = rag_info.get("rag_status", "unknown")
        return CoverageReport(
            ts_code=ts_code,
            trade_date=trade_date,
            categories=cats,
            rag_status=rag_status,
        )

    s3 = await _run_step("compute_fields", _build_report(), 20.0, debug=debug)
    steps.append(s3)
    report = s3.data

    if debug and report:
        rd = report.to_dict()
        rag_cat = rd.get("categories", {}).get("rag", {})
        print(f"      quote:          {rd.get('quote_completeness', 0):.1%}", flush=True)
        print(f"      valuation:      {rd.get('valuation_completeness', 0):.1%}  "
              f"(P0: {rd.get('valuation_p0_completeness', 0):.1%}, "
              f"P1: {rd.get('valuation_p1_completeness', 0):.1%})", flush=True)
        print(f"      fin-statement:  {rd.get('financial_statement_completeness', 0):.1%}", flush=True)
        print(f"      fin-indicator:  {rd.get('financial_indicator_completeness', 0):.1%}", flush=True)
        print(f"      rag:            {rd.get('rag_completeness', 0):.1%}  "
              f"(data_status={rag_cat.get('data_status', '?')}, "
              f"rc={rag_cat.get('reason_code')})", flush=True)
        print(f"      overall:        {rd.get('overall_completeness', 0):.1%}  "
              f"(ex-RAG: {rd.get('overall_without_rag', 0):.1%})", flush=True)

    # ── Stage 4: persist snapshot ─────────────────────────────────────────────
    if not no_persist and report:
        async def _persist():
            async with AsyncSessionLocal() as db:
                from app.services.coverage_audit_service import CoverageAuditService
                svc = CoverageAuditService(db, trade_date)
                await svc._save_snapshot(report)
                await svc._enqueue_missing(ts_code, report.missing_fields)

        s4 = await _run_step("persist_snapshot", _persist(), 8.0, debug=debug)
        steps.append(s4)
    else:
        steps.append(StepResult("persist_snapshot", True, 0.0, "skipped (no-persist)"))

    # Final report dict
    if report:
        report_dict = report.to_dict()
    else:
        report_dict = {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "error": "audit failed",
            "overall_completeness": 0.0,
            "overall_without_rag": 0.0,
            "steps": [{"name": s.name, "ok": s.ok, "elapsed": s.elapsed, "detail": s.detail}
                      for s in steps],
        }

    if debug:
        # Print step summary
        print(f"\n    Steps summary for {ts_code}:")
        for s in steps:
            print(f"    {str(s)}", flush=True)

    return report_dict


# ── Parse args ────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Data completeness coverage audit for a stock pool",
    )
    p.add_argument(
        "--symbols", required=True,
        help="Comma-separated A-share symbols, e.g. 600519,000725 (no market suffix needed)",
    )
    p.add_argument(
        "--trade-date",
        default=datetime.utcnow().strftime("%Y-%m-%d"),
        help="Reference trade date YYYY-MM-DD (default: today UTC)",
    )
    p.add_argument(
        "--out-dir", default="docs/artifacts",
        help="Output directory for JSON + CSV reports (default: docs/artifacts)",
    )
    p.add_argument(
        "--no-persist", action="store_true",
        help="Dry-run: skip writing DB snapshots / missing_field_queue",
    )
    p.add_argument(
        "--debug", action="store_true",
        help="Debug mode: per-stage timing, no exception swallowing, verbose output",
    )
    return p.parse_args()


def _normalize_symbol(sym: str) -> str:
    sym = sym.strip()
    if "." in sym:
        return sym
    code = sym.zfill(6)
    if code.startswith(("6",)):
        return f"{code}.SH"
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    return f"{code}.SH"


# ── Output ────────────────────────────────────────────────────────────────────

def _write_outputs(
    reports: list[dict[str, Any]],
    out_dir: Path,
    trade_date: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"coverage_audit_{trade_date}"

    json_path = out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  JSON → {json_path}")

    csv_path  = out_dir / f"{stem}.csv"
    headers = [
        "ts_code", "trade_date",
        "overall_completeness", "overall_without_rag",
        "quote_completeness", "valuation_completeness",
        "valuation_p0_completeness", "valuation_p1_completeness",
        "financial_statement_completeness", "financial_indicator_completeness",
        "financial_completeness", "rag_completeness",
        "rag_status", "missing_field_count",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for r in reports:
            w.writerow({
                "ts_code":                r.get("ts_code", ""),
                "trade_date":             r.get("trade_date", trade_date),
                "overall_completeness":   r.get("overall_completeness", 0.0),
                "overall_without_rag":    r.get("overall_without_rag", 0.0),
                "quote_completeness":     r.get("quote_completeness", 0.0),
                "valuation_completeness": r.get("valuation_completeness", 0.0),
                "valuation_p0_completeness": r.get("valuation_p0_completeness", 0.0),
                "valuation_p1_completeness": r.get("valuation_p1_completeness", 0.0),
                "financial_statement_completeness": r.get("financial_statement_completeness", 0.0),
                "financial_indicator_completeness": r.get("financial_indicator_completeness", 0.0),
                "financial_completeness": r.get("financial_completeness", 0.0),
                "rag_completeness":       r.get("rag_completeness", 0.0),
                "rag_status":             r.get("rag_status", "unknown"),
                "missing_field_count":    len(r.get("missing_fields", [])),
            })
    print(f"  CSV  → {csv_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

async def _main(args: argparse.Namespace) -> None:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    raw_symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    ts_codes    = [_normalize_symbol(s) for s in raw_symbols]
    trade_date  = args.trade_date
    out_dir     = Path(args.out_dir)
    debug       = args.debug
    no_persist  = args.no_persist

    print(f"\n=== Coverage Audit  trade_date={trade_date} ===")
    print(f"  symbols ({len(ts_codes)}): {', '.join(ts_codes)}")
    print(f"  out_dir: {out_dir}")
    print(f"  persist: {'NO (dry-run)' if no_persist else 'YES'}")
    print(f"  debug:   {'YES' if debug else 'NO'}")
    print()

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("  WARNING: DATABASE_URL not set — DB queries will return empty")

    reports: list[dict[str, Any]] = []
    for ts_code in ts_codes:
        t0 = time.monotonic()
        if not debug:
            print(f"  auditing {ts_code} ...", end="", flush=True)
        try:
            r = await _audit_one_stock(
                ts_code, trade_date,
                debug=debug, no_persist=no_persist,
            )
            elapsed = time.monotonic() - t0
            reports.append(r)
            if not debug:
                ov    = r.get("overall_completeness", 0.0)
                ov_nr = r.get("overall_without_rag",  0.0)
                q     = r.get("quote_completeness",    0.0)
                v     = r.get("valuation_completeness",0.0)
                v_p0  = r.get("valuation_p0_completeness", 0.0)
                v_p1  = r.get("valuation_p1_completeness", 0.0)
                f_st  = r.get("financial_statement_completeness", 0.0)
                f_in  = r.get("financial_indicator_completeness", 0.0)
                rag_c = r.get("rag_completeness",      0.0)
                rag_s = r.get("rag_status", "?")
                n_miss = len(r.get("missing_fields", []))
                print(
                    f"\n    overall={ov:.0%} (ex-RAG={ov_nr:.0%})  "
                    f"quote={q:.0%}  val={v:.0%}(P0={v_p0:.0%}/P1={v_p1:.0%})  "
                    f"stmt={f_st:.0%}  ind={f_in:.0%}  "
                    f"rag={rag_c:.0%}[{rag_s}]  missing={n_miss}  ({elapsed:.1f}s)"
                )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            print(f"\n    ✗ {ts_code}: {exc}  ({elapsed:.1f}s)", file=sys.stderr)
            if debug:
                import traceback
                traceback.print_exc()
            reports.append({
                "ts_code": ts_code,
                "trade_date": trade_date,
                "error": repr(exc),
                "overall_completeness": 0.0,
                "overall_without_rag": 0.0,
            })

    # ── Write output files ─────────────────────────────────────────────────
    step_out = await _run_step(
        "write_artifacts",
        asyncio.to_thread(_write_outputs, reports, out_dir, trade_date),
        5.0,
        debug=debug,
    )

    # ── Summary ────────────────────────────────────────────────────────────
    if reports:
        avg_ov    = sum(r.get("overall_completeness", 0) for r in reports) / len(reports)
        avg_ov_nr = sum(r.get("overall_without_rag",  0) for r in reports) / len(reports)
        avg_v     = sum(r.get("valuation_completeness",0) for r in reports) / len(reports)
        avg_f     = sum(r.get("financial_completeness",0) for r in reports) / len(reports)
        avg_p0    = sum(r.get("valuation_p0_completeness",0) for r in reports) / len(reports)
        avg_p1    = sum(r.get("valuation_p1_completeness",0) for r in reports) / len(reports)
        avg_st    = sum(r.get("financial_statement_completeness",0) for r in reports) / len(reports)
        avg_in    = sum(r.get("financial_indicator_completeness",0) for r in reports) / len(reports)
        print(f"\n  ── Final Summary ──────────────────────────────────────")
        print(f"  Stocks processed:               {len(reports)}")
        print(f"  Avg overall completeness:       {avg_ov:.1%}")
        print(f"  Avg overall (ex-RAG):           {avg_ov_nr:.1%}")
        print(f"  Avg valuation completeness:     {avg_v:.1%}")
        print(f"  Avg valuation P0 completeness:  {avg_p0:.1%}")
        print(f"  Avg valuation P1 completeness:  {avg_p1:.1%}")
        print(f"  Avg fin-statement completeness: {avg_st:.1%}")
        print(f"  Avg fin-indicator completeness: {avg_in:.1%}")
        print(f"  Avg financial completeness:     {avg_f:.1%}")

    print("\nDone.\n")


def main() -> None:
    args = _parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
