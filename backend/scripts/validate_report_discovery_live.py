#!/usr/bin/env python3
"""
scripts/validate_report_discovery_live.py — Phase 6E 真实公网 PDF 发现率验证

用法：
  cd backend
  python scripts/validate_report_discovery_live.py

输出：
  - console: 每只股票的发现率摘要
  - reports/discovery_validation_YYYYMMDD.csv   详细结果
  - reports/discovery_validation_YYYYMMDD.json  JSON 版
"""
from __future__ import annotations

import asyncio
import csv
import json
import sys
import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_STOCKS = [
    {"code": "600519", "name": "贵州茅台", "exchange": "SH"},
    {"code": "000858", "name": "五粮液",   "exchange": "SZ"},
    {"code": "600036", "name": "招商银行", "exchange": "SH"},
    {"code": "300750", "name": "宁德时代", "exchange": "SZ"},
    {"code": "000333", "name": "美的集团", "exchange": "SZ"},
]
REPORT_YEAR = 2024


async def validate_stock(agent, stock: dict) -> list[dict]:
    """Run discover_latest for one stock, return candidate rows."""
    rows = []
    try:
        result = await agent.discover_latest(
            stock_code=stock["code"],
            company_name=stock["name"],
            report_year=REPORT_YEAR,
        )
        candidates = result.get("candidates") or []
        for c in candidates:
            rows.append({
                "stock_code":  stock["code"],
                "company_name": stock["name"],
                "report_type": c.get("report_type"),
                "source":      c.get("source"),
                "confidence":  round(c.get("confidence", 0), 4),
                "auto_insert": c.get("confidence", 0) >= 0.75,
                "title":       c.get("title", ""),
                "pdf_url":     c.get("pdf_url", ""),
                "warnings":    "; ".join(c.get("warnings") or []),
            })
        if not candidates:
            # No candidates found — record a "not found" row per type
            for rtype in ["annual", "semi", "q1", "q3"]:
                rows.append({
                    "stock_code":  stock["code"],
                    "company_name": stock["name"],
                    "report_type": rtype,
                    "source":      "none",
                    "confidence":  0.0,
                    "auto_insert": False,
                    "title":       "",
                    "pdf_url":     "",
                    "warnings":    result.get("errors", ["no candidates found"])[0] if result.get("errors") else "no candidates",
                })
    except Exception as e:
        print(f"  ERROR {stock['code']}: {e}", flush=True)
        for rtype in ["annual", "semi", "q1", "q3"]:
            rows.append({
                "stock_code":  stock["code"],
                "company_name": stock["name"],
                "report_type": rtype,
                "source":      "error",
                "confidence":  0.0,
                "auto_insert": False,
                "title":       "",
                "pdf_url":     "",
                "warnings":    str(e)[:200],
            })
    return rows


async def main() -> None:
    from app.agents.report_discovery_agent import ReportDiscoveryAgent

    agent = ReportDiscoveryAgent()
    all_rows: list[dict] = []

    print(f"Phase 6E — Report Discovery Live Validation")
    print(f"Report Year: {REPORT_YEAR}")
    print(f"Stocks: {len(TEST_STOCKS)}")
    print("=" * 60)

    for stock in TEST_STOCKS:
        print(f"Testing {stock['code']} {stock['name']}...", flush=True)
        rows = await validate_stock(agent, stock)
        for r in rows:
            status = "✓ AUTO" if r["auto_insert"] else ("✗ SKIP" if r["confidence"] < 0.35 else "⚠ MANUAL")
            print(f"  [{status}] {r['report_type']:6s} {r['source']:8s} conf={r['confidence']:.2f} {r['title'][:50]}")
        all_rows.extend(rows)
        await asyncio.sleep(2)  # courtesy delay between stocks

    # Summary
    total = len(all_rows)
    auto_inserted = sum(1 for r in all_rows if r["auto_insert"])
    found = sum(1 for r in all_rows if r["pdf_url"])
    print("\n" + "=" * 60)
    print(f"Total rows:     {total}")
    print(f"Found PDF:      {found}/{total} ({100*found//total if total else 0}%)")
    print(f"Auto-inserted:  {auto_inserted}/{total} ({100*auto_inserted//total if total else 0}%)")

    # Save outputs
    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    datestamp = datetime.date.today().strftime("%Y%m%d")
    csv_path  = out_dir / f"discovery_validation_{datestamp}.csv"
    json_path = out_dir / f"discovery_validation_{datestamp}.json"

    fieldnames = ["stock_code","company_name","report_type","source","confidence","auto_insert","title","pdf_url","warnings"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_date": datestamp,
            "report_year": REPORT_YEAR,
            "summary": {"total": total, "found_pdf": found, "auto_inserted": auto_inserted},
            "rows": all_rows,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nCSV:  {csv_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
