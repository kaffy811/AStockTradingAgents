#!/usr/bin/env python3
"""
scripts/report_free_data_coverage.py — Free Mode 数据覆盖率报告（Phase 6N-3）

对指定股票列表计算每只股票在 Free Mode 下的数据覆盖情况：
  - BaoStock 成功/失败模块
  - AkShare 成功/失败接口
  - PDF 年报发现状态
  - RAG 准备状态
  - 可渲染模块数 / 总模块数
  - 不可用数据清单
  - recommended_action（建议操作）

输出：
  docs/artifacts/free_data_coverage_report.json
  docs/artifacts/free_data_coverage_report.csv

用法：
    uv run python scripts/report_free_data_coverage.py --symbols 600519,000725,601686
    uv run python scripts/report_free_data_coverage.py --symbols 600519,300750,601318,600186
    uv run python scripts/report_free_data_coverage.py --symbols 600519 --years 2025,2024
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

# ── Add backend/ to sys.path ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── BaoStock module definitions (must match free mode tool chain) ─────────────
_BS_MODULE_KEYS: list[str] = ["profit", "growth", "balance", "operation", "cash_flow", "dupont"]

_BS_RENDERABLE_FIELDS: dict[str, list[str]] = {
    "profit":    ["roe_avg", "net_margin", "gross_margin"],
    "growth":    ["yoy_ni", "yoy_equity"],
    "balance":   ["current_ratio", "quick_ratio", "liability_to_asset"],
    "operation": ["nr_turn_ratio", "inv_turn_ratio"],
    "cash_flow": ["cfo_to_or", "cfo_to_np"],
    "dupont":    ["dupont_roe", "dupont_at"],
}

# Frontend module sections that depend on BaoStock
_BS_SECTION_MAP: dict[str, str] = {
    "profit":     "profitability",
    "growth":     "growth",
    "balance":    "solvency",
    "operation":  "operations",
    "cash_flow":  "earnings-quality",
    "dupont":     "dupont",
}

_AKSHARE_PROBES: list[str] = ["financial_abstract", "cash_flow", "real_time_quote"]


def _to_ts_code(symbol: str) -> str:
    """Convert 6-digit code to ts_code format."""
    symbol = symbol.strip()
    if "." in symbol:
        return symbol.upper()
    if symbol.startswith(("6", "5", "9")):
        return f"{symbol}.SH"
    return f"{symbol}.SZ"


def _to_bs_code(ts_code: str) -> str:
    """Convert ts_code to BaoStock format (sh.600519)."""
    if "." not in ts_code:
        ts_code = _to_ts_code(ts_code)
    sym, mkt = ts_code.split(".")
    return f"{mkt.lower()}.{sym}"


# ── BaoStock probe ────────────────────────────────────────────────────────────

def _probe_baostock_sync(bs_code: str, years: list[int]) -> dict[str, Any]:
    """
    Run BaoStock probes for a single stock synchronously.
    Returns dict with results per module.
    """
    results: dict[str, dict] = {}

    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != "0":
            for mk in _BS_MODULE_KEYS:
                results[mk] = {"status": "failed", "rows": 0, "reason": "baostock login failed"}
            return results
    except Exception as e:
        for mk in _BS_MODULE_KEYS:
            results[mk] = {"status": "failed", "rows": 0, "reason": f"baostock import error: {e}"}
        return results

    _YEAR_TYPES = {y: "5" for y in years}  # 5 = 年报

    def _fetch(method_name: str) -> list[dict]:
        rows = []
        for year in sorted(years, reverse=True)[:4]:
            try:
                func = getattr(bs, method_name)
                rs = func(code=bs_code, year=str(year), quarter=4, fields="")
                if rs.error_code != "0":
                    continue
                while rs.error_code == "0" and rs.next():
                    rows.append(rs.get_row_data())
            except Exception:
                pass
        return rows

    method_map = {
        "profit":     "query_profit_data",
        "growth":     "query_growth_data",
        "balance":    "query_balance_data",
        "operation":  "query_operation_data",
        "cash_flow":  "query_cash_flow_data",
        "dupont":     "query_dupont_data",
    }

    for mk in _BS_MODULE_KEYS:
        t0 = time.time()
        try:
            rows = _fetch(method_map[mk])
            renderable_fields = _BS_RENDERABLE_FIELDS.get(mk, [])
            has_data = len(rows) > 0
            # Check field availability from header
            latency_ms = round((time.time() - t0) * 1000)
            results[mk] = {
                "status": "ok" if has_data else "empty",
                "rows": len(rows),
                "latency_ms": latency_ms,
                "reason": None,
            }
        except Exception as e:
            results[mk] = {
                "status": "failed",
                "rows": 0,
                "latency_ms": round((time.time() - t0) * 1000),
                "reason": str(e),
            }

    try:
        bs.logout()
    except Exception:
        pass

    return results


async def _probe_akshare(ts_code: str) -> dict[str, Any]:
    """Run AkShare probes for a single stock."""
    results: dict[str, Any] = {}
    symbol_6 = ts_code.split(".")[0]

    for probe in _AKSHARE_PROBES:
        t0 = time.time()
        try:
            import akshare as ak
            if probe == "real_time_quote":
                df = ak.stock_zh_a_spot_em()
                found = df[df["代码"] == symbol_6] if df is not None else None
                ok = found is not None and not found.empty
                results[probe] = {"status": "ok" if ok else "empty", "latency_ms": round((time.time() - t0) * 1000)}
            elif probe == "financial_abstract":
                df = ak.stock_financial_abstract_ths(symbol=symbol_6, indicator="按年度")
                ok = df is not None and not df.empty
                results[probe] = {"status": "ok" if ok else "empty", "rows": len(df) if ok else 0, "latency_ms": round((time.time() - t0) * 1000)}
            elif probe == "cash_flow":
                df = ak.stock_financial_cash_ths(symbol=symbol_6, indicator="按年度")
                ok = df is not None and not df.empty
                results[probe] = {"status": "ok" if ok else "empty", "rows": len(df) if ok else 0, "latency_ms": round((time.time() - t0) * 1000)}
        except Exception as e:
            results[probe] = {"status": "failed", "reason": str(e)[:80], "latency_ms": round((time.time() - t0) * 1000)}

    return results


async def _probe_db(ts_code: str) -> dict[str, Any]:
    """Check report_documents and report_chunks counts.

    NOTE: requires DATABASE_URL env var (PostgreSQL DSN).  When not set or
    unreachable the result carries ``rag_status: "unknown"`` rather than 0 to
    avoid misleading output — the running backend server may have chunks even
    when this script cannot reach the DB directly.
    """
    result: dict[str, Any] = {"report_documents": 0, "report_chunks": 0, "rag_ready": False, "rag_status": "unknown"}
    try:
        import asyncpg
        dsn = os.environ.get("DATABASE_URL", "")
        if not dsn:
            result["error"] = "DATABASE_URL not set — use the /api/v1/fundamentals/{symbol}/diagnostics endpoint for live RAG status"
            result["rag_status"] = "unknown"
            return result
        conn = await asyncpg.connect(dsn)
        try:
            rd = await conn.fetchval("SELECT COUNT(*) FROM report_documents WHERE ts_code=$1", ts_code)
            rc = await conn.fetchval("SELECT COUNT(*) FROM report_chunks WHERE ts_code=$1", ts_code)
            result["report_documents"] = int(rd or 0)
            result["report_chunks"] = int(rc or 0)
            result["rag_ready"] = result["report_chunks"] > 0
            result["rag_status"] = "ok" if result["rag_ready"] else "empty"
        finally:
            await conn.close()
    except Exception as e:
        result["error"] = str(e)[:80]
        result["rag_status"] = "unknown"
    return result


async def _probe_pdf(ts_code: str, years: list[int]) -> dict[str, Any]:
    """Check PDF discovery for a stock."""
    result = {"found_years": [], "total_candidates": 0}
    try:
        from app.services.report_discovery_agent import discover_annual_reports
        for year in sorted(years, reverse=True)[:2]:
            r = await discover_annual_reports(ts_code, year)
            if r and r.get("candidates"):
                result["found_years"].append(year)
                result["total_candidates"] += len(r["candidates"])
    except Exception as e:
        result["error"] = str(e)[:80]
    return result


def _recommended_action(bs_ok: int, ak_ok: bool, rag: bool, pdf: bool) -> str:
    """Generate a recommended action based on data availability."""
    if bs_ok == 0 and not ak_ok:
        return "enable_baostock=true 并确认网络可访问 BaoStock；检查 AkShare 安装"
    if bs_ok == 0:
        return "检查 BaoStock 登录状态；确认 enable_baostock=true"
    if not rag and not pdf:
        return "上传年报 PDF 至 RAG 管道以启用问财报功能（可选）"
    if not rag and pdf:
        return "PDF 已发现，运行 embed_reports.py 建立 RAG 索引"
    return "数据基本完整，可正常使用 Free Mode"


async def _process_stock(ts_code: str, years: list[int]) -> dict[str, Any]:
    """Generate coverage report for a single stock."""
    print(f"  [{ts_code}] 开始覆盖率分析...")

    # BaoStock (sync, run in thread)
    bs_code = _to_bs_code(ts_code)
    t0 = time.time()
    bs_results = await asyncio.to_thread(_probe_baostock_sync, bs_code, years)
    bs_total_ms = round((time.time() - t0) * 1000)

    bs_ok_modules = [k for k, v in bs_results.items() if v.get("rows", 0) > 0]
    bs_total = len(_BS_MODULE_KEYS)
    print(f"  [{ts_code}] BaoStock: {len(bs_ok_modules)}/{bs_total} modules OK ({bs_total_ms}ms)")

    # AkShare
    ak_results = await _probe_akshare(ts_code)
    ak_quote_ok = ak_results.get("real_time_quote", {}).get("status") == "ok"
    ak_fin_ok = ak_results.get("financial_abstract", {}).get("status") == "ok"
    print(f"  [{ts_code}] AkShare: quote={'ok' if ak_quote_ok else 'fail'}, fin={'ok' if ak_fin_ok else 'fail'}")

    # DB / RAG
    db_results = await _probe_db(ts_code)
    rag_ready = db_results.get("rag_ready", False)
    rag_status = db_results.get("rag_status", "unknown")
    print(f"  [{ts_code}] RAG: {db_results.get('report_chunks', 0)} chunks, status={rag_status}")

    # PDF
    pdf_results = await _probe_pdf(ts_code, years)
    pdf_found = len(pdf_results.get("found_years", [])) > 0
    print(f"  [{ts_code}] PDF: found_years={pdf_results.get('found_years', [])}")

    # Section visibility (based on BaoStock modules)
    renderable_sections = []
    hidden_sections = []
    for bs_mk, section in _BS_SECTION_MAP.items():
        r = bs_results.get(bs_mk, {})
        if r.get("rows", 0) > 0:
            renderable_sections.append(section)
        else:
            hidden_sections.append(section)

    # Unavailable data
    unavailable = []
    for bs_mk in _BS_MODULE_KEYS:
        r = bs_results.get(bs_mk, {})
        if r.get("rows", 0) == 0:
            reason = r.get("reason") or r.get("status", "no data")
            unavailable.append({"module": bs_mk, "reason": reason})

    action = _recommended_action(
        bs_ok=len(bs_ok_modules),
        ak_ok=ak_quote_ok or ak_fin_ok,
        rag=rag_ready,
        pdf=pdf_found,
    )

    return {
        "ts_code": ts_code,
        "generated_at": datetime.now().isoformat(),
        "baostock": {
            "ok_modules": bs_ok_modules,
            "failed_modules": [k for k in _BS_MODULE_KEYS if k not in bs_ok_modules],
            "ok_count": len(bs_ok_modules),
            "total": bs_total,
            "total_latency_ms": bs_total_ms,
            "per_module": bs_results,
        },
        "akshare": {
            "quote_ok": ak_quote_ok,
            "financial_abstract_ok": ak_fin_ok,
            "per_probe": ak_results,
        },
        "rag": {
            "ready": rag_ready,
            "status": rag_status,
            "report_documents": db_results.get("report_documents", 0),
            "report_chunks": db_results.get("report_chunks", 0),
            "error": db_results.get("error"),
        },
        "pdf": pdf_results,
        "visibility": {
            "renderable_sections": renderable_sections,
            "hidden_sections": hidden_sections,
            "renderable_count": len(renderable_sections),
            "total_data_driven": len(_BS_SECTION_MAP),
        },
        "unavailable_data": unavailable,
        "recommended_action": action,
    }


async def main(symbols: list[str], years: list[int], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Free Mode Data Coverage Report")
    print(f"Symbols : {symbols}")
    print(f"Years   : {years}")
    print(f"{'='*60}\n")

    results = []
    # Process stocks sequentially to avoid BaoStock Lock contention
    for sym in symbols:
        ts_code = _to_ts_code(sym)
        result = await _process_stock(ts_code, years)
        results.append(result)

    # Write JSON
    json_path = out_dir / "free_data_coverage_report.json"
    json_path.write_text(json.dumps({"generated_at": datetime.now().isoformat(), "stocks": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ JSON: {json_path}")

    # Write CSV
    csv_path = out_dir / "free_data_coverage_report.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "ts_code", "bs_ok_count", "bs_total", "bs_ok_modules",
            "ak_quote_ok", "ak_fin_ok",
            "pdf_found", "rag_ready", "report_chunks",
            "renderable_sections", "hidden_sections",
            "recommended_action",
        ])
        for r in results:
            w.writerow([
                r["ts_code"],
                r["baostock"]["ok_count"],
                r["baostock"]["total"],
                ",".join(r["baostock"]["ok_modules"]),
                r["akshare"]["quote_ok"],
                r["akshare"]["financial_abstract_ok"],
                len(r["pdf"].get("found_years", [])) > 0,
                r["rag"]["ready"],
                r["rag"]["report_chunks"],
                ",".join(r["visibility"]["renderable_sections"]),
                ",".join(r["visibility"]["hidden_sections"]),
                r["recommended_action"],
            ])
    print(f"✓ CSV : {csv_path}")

    # Print summary
    print(f"\n{'='*60}")
    print("COVERAGE SUMMARY")
    print(f"{'='*60}")
    for r in results:
        bs = r["baostock"]
        vis = r["visibility"]
        rag = r["rag"]
        print(f"\n{r['ts_code']}:")
        print(f"  BaoStock  : {bs['ok_count']}/{bs['total']} modules — {bs['ok_modules']}")
        print(f"  Sections  : {vis['renderable_count']}/{vis['total_data_driven']} renderable — {vis['renderable_sections']}")
        print(f"  RAG       : ready={rag['ready']} ({rag['report_chunks']} chunks)")
        print(f"  Action    : {r['recommended_action']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Free Mode Data Coverage Report")
    parser.add_argument("--symbols", required=True, help="Comma-separated stock symbols (e.g. 600519,000725)")
    parser.add_argument("--years", default="2024,2023", help="Comma-separated years to probe (default: 2024,2023)")
    parser.add_argument("--out-dir", default="docs/artifacts", help="Output directory")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
    out_dir = Path(args.out_dir)

    asyncio.run(main(symbols, years, out_dir))
