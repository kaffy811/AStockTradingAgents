#!/usr/bin/env python
"""
scripts/run_rag_eval.py — Phase 2D.5: RAG Evaluation CLI.

Usage
-----
    uv run scripts/run_rag_eval.py [OPTIONS]

Options
-------
  --cases      PATH   Path to eval cases JSON (default: tests/fixtures/rag_eval_cases.json)
  --top-k      INT    Results per query (default: 5)
  --search-mode STR   keyword | vector | hybrid (default: keyword)
  --output     PATH   Write JSON report to this path (optional)
  --html       PATH   Write HTML report to this path (optional)
  --db-url     STR    Override DATABASE_URL (optional; uses mock DB if omitted)

Output
------
  Always prints a summary table to stdout.
  --output saves full JSON report.
  --html   saves a self-contained HTML report.

Exit codes
----------
  0 — all cases PASS (recall_at_k == 1.0)
  1 — one or more cases FAILED
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import textwrap
from datetime import datetime, timezone

# Ensure project root is on sys.path when run directly
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── Argument parsing ──────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run RAG evaluation and report Recall@k / MRR / nDCG metrics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(__doc__ or ""),
    )
    p.add_argument(
        "--cases",
        default=None,
        help="Path to JSON eval cases file (default: tests/fixtures/rag_eval_cases.json)",
    )
    p.add_argument("--top-k",      type=int,   default=5,         help="Top-k results per query")
    p.add_argument("--search-mode", default="keyword",
                   choices=["keyword", "vector", "hybrid"],
                   help="Search mode (default: keyword)")
    p.add_argument("--output",     default=None, help="Write JSON report to FILE")
    p.add_argument("--html",       default=None, help="Write HTML report to FILE")
    p.add_argument("--db-url",     default=None, help="Override DATABASE_URL (uses mock if omitted)")
    return p.parse_args()


# ── HTML report ───────────────────────────────────────────────────────────────

def _build_html(report: dict) -> str:
    ts      = report.get("generated_at", "")
    summary = report.get("summary", {})
    cases   = report.get("per_case", [])

    def _pct(v: float) -> str:
        return f"{v * 100:.1f}%"

    rows_html = ""
    for c in cases:
        status   = "✅" if c.get("ok") else "❌"
        error    = c.get("error", "")
        err_cell = f'<span class="err">{error}</span>' if error else ""
        rows_html += (
            f"<tr>"
            f"<td>{status}</td>"
            f"<td>{c['id']}</td>"
            f"<td>{_pct(c.get('recall_at_k', 0))}</td>"
            f"<td>{c.get('rr', 0):.4f}</td>"
            f"<td>{_pct(c.get('ndcg_at_k', 0))}</td>"
            f"<td>{c.get('results_count', '-')}</td>"
            f"<td>{c.get('elapsed_ms', '-')} ms</td>"
            f"<td>{err_cell}</td>"
            f"</tr>\n"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>RAG Evaluation Report</title>
<style>
  body  {{ font-family: sans-serif; max-width: 1200px; margin: 2rem auto; color: #222; }}
  h1   {{ color: #1a1a2e; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: 1.5rem 0; }}
  .card {{ background: #f5f7fa; border-radius: 8px; padding: 1rem 1.5rem; text-align: center; }}
  .card .label {{ font-size: 0.8rem; color: #666; text-transform: uppercase; }}
  .card .value {{ font-size: 2rem; font-weight: bold; color: #1a1a2e; }}
  .card.pass .value {{ color: #2e7d32; }}
  .card.warn .value {{ color: #f57c00; }}
  .card.fail .value {{ color: #c62828; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; }}
  th    {{ background: #1a1a2e; color: white; padding: 0.6rem 1rem; text-align: left; }}
  td    {{ padding: 0.5rem 1rem; border-bottom: 1px solid #eee; }}
  tr:hover {{ background: #fafafa; }}
  .err {{ color: #c62828; font-size: 0.8rem; }}
  footer {{ margin-top: 2rem; font-size: 0.75rem; color: #999; }}
</style>
</head>
<body>
<h1>RAG Evaluation Report</h1>
<p>Generated: {ts} &nbsp;|&nbsp; Mode: <strong>{summary.get("search_mode","")}</strong>
   &nbsp;|&nbsp; Top-k: <strong>{summary.get("top_k","")}</strong></p>

<div class="summary-grid">
  <div class="card {'pass' if summary.get('recall_at_k',0) >= 0.9 else 'warn'}">
    <div class="label">Recall@k</div>
    <div class="value">{_pct(summary.get('recall_at_k', 0))}</div>
  </div>
  <div class="card {'pass' if summary.get('mrr',0) >= 0.8 else 'warn'}">
    <div class="label">MRR</div>
    <div class="value">{summary.get('mrr', 0):.3f}</div>
  </div>
  <div class="card {'pass' if summary.get('ndcg_at_k',0) >= 0.8 else 'warn'}">
    <div class="label">nDCG@k</div>
    <div class="value">{_pct(summary.get('ndcg_at_k', 0))}</div>
  </div>
  <div class="card {'pass' if summary.get('cases_failed',1) == 0 else 'fail'}">
    <div class="label">Cases</div>
    <div class="value">{summary.get('cases_ok',0)}/{summary.get('cases_total',0)}</div>
  </div>
</div>

<table>
<thead><tr>
  <th></th><th>Case ID</th><th>Recall@k</th><th>RR</th>
  <th>nDCG@k</th><th>Results</th><th>Latency</th><th>Error</th>
</tr></thead>
<tbody>
{rows_html}
</tbody>
</table>

<footer>TradingAgents RAG Eval · Phase 2D.5</footer>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

async def _main(args: argparse.Namespace) -> int:
    from app.agents.rag_eval_runner import run_rag_eval  # noqa: PLC0415

    # Resolve cases path
    cases_path = args.cases
    if not cases_path:
        cases_path = os.path.join(
            _PROJECT_ROOT, "tests", "fixtures", "rag_eval_cases.json"
        )

    # Optional real DB
    db = None
    if args.db_url:
        try:
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession  # noqa: PLC0415
            from sqlalchemy.orm import sessionmaker  # noqa: PLC0415
            engine     = create_async_engine(args.db_url, echo=False)
            async_sess = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            db         = async_sess()
        except Exception as exc:
            print(f"[warn] Could not connect to DB ({exc}); using mock DB.", flush=True)

    print(
        f"Running RAG eval: cases={cases_path} "
        f"top_k={args.top_k} mode={args.search_mode}",
        flush=True,
    )

    report = await run_rag_eval(
        cases_path=cases_path,
        db=db,
        top_k=args.top_k,
        search_mode=args.search_mode,
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report["generated_at"] = now
    report["summary"] = {
        "top_k":         report["top_k"],
        "search_mode":   report["search_mode"],
        "cases_total":   report["cases_total"],
        "cases_ok":      report["cases_ok"],
        "cases_failed":  report["cases_failed"],
        "recall_at_k":   report["recall_at_k"],
        "mrr":           report["mrr"],
        "ndcg_at_k":     report["ndcg_at_k"],
    }

    # ── Print summary table ────────────────────────────────────────────────────
    print()
    print(f"{'Case ID':<35} {'Recall@k':>9} {'RR':>7} {'nDCG@k':>8} {'Results':>8}")
    print("-" * 75)
    for c in report["per_case"]:
        status = "PASS" if c["ok"] else "FAIL"
        print(
            f"{c['id']:<35} "
            f"{c.get('recall_at_k', 0) * 100:>8.1f}% "
            f"{c.get('rr', 0):>7.4f} "
            f"{c.get('ndcg_at_k', 0) * 100:>7.1f}% "
            f"{c.get('results_count', '-'):>8}  {status}"
        )
    print("-" * 75)
    print(
        f"{'AGGREGATE':<35} "
        f"{report['recall_at_k'] * 100:>8.1f}% "
        f"{report['mrr']:>7.4f} "
        f"{report['ndcg_at_k'] * 100:>7.1f}%"
    )
    print(
        f"\nCases: {report['cases_ok']}/{report['cases_total']} OK  "
        f"({report['cases_failed']} failed)  "
        f"elapsed={report['elapsed_ms']}ms"
    )
    if report.get("errors"):
        print("\nErrors:")
        for e in report["errors"]:
            print(f"  • {e}")

    # ── Write JSON ─────────────────────────────────────────────────────────────
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nJSON report saved to: {args.output}")

    # ── Write HTML ─────────────────────────────────────────────────────────────
    if args.html:
        html = _build_html(report)
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML report saved to: {args.html}")

    # Exit 0 if all cases recalled (recall_at_k == 1.0), else 1
    return 0 if report["cases_failed"] == 0 else 1


def main() -> None:
    args   = _parse_args()
    code   = asyncio.run(_main(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
