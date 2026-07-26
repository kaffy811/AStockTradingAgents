from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.company_v2_production_smoke_test import analyze_smoke_payload, fetch_payload


def _read_symbols(args: argparse.Namespace) -> list[str]:
    if args.symbols_file:
        path = Path(args.symbols_file)
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [item.strip() for item in args.symbols.split(",") if item.strip()]


def summarize_daily(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    pass_records = [record for record in records if record.get("smoke_gate_pass")]
    warning_records = [
        record for record in records
        if record.get("smoke_gate_pass") and int(record.get("semantic_warning_count") or 0) > 0
    ]
    fail_records = [record for record in records if not record.get("smoke_gate_pass")]
    return {
        "total_symbols": total,
        "pass_count": len(pass_records),
        "warning_count": len(warning_records),
        "fail_count": len(fail_records),
        "avg_modules_renderable": round(sum(float(r.get("modules_renderable") or 0) for r in records) / max(1, total), 2),
        "avg_coverage": None,
        "avg_data_quality_score": round(sum(float(r.get("data_quality_score") or 0) for r in records) / max(1, total), 2),
        "total_provider_timeouts": sum(int(r.get("providers_timeout") or 0) for r in records),
        "total_mapping_errors": sum(int(r.get("mapping_error_count") or 0) for r in records),
        "total_render_rule_errors": sum(int(r.get("render_rule_error_count") or 0) for r in records),
        "total_semantic_warnings": sum(int(r.get("semantic_warning_count") or 0) for r in records),
        "total_strong_failures": sum(int(r.get("strong_failed_count") or 0) for r in records),
        "symbols_failed": [r.get("symbol") for r in fail_records],
        "symbols_warning": [r.get("symbol") for r in warning_records],
    }


def _write_md(path: Path, snapshot: dict[str, Any]) -> None:
    summary = snapshot["summary"]
    lines = [
        f"# CompanyV2 Daily Health {snapshot['date']}",
        "",
        f"- total_symbols: {summary['total_symbols']}",
        f"- pass_count: {summary['pass_count']}",
        f"- warning_count: {summary['warning_count']}",
        f"- fail_count: {summary['fail_count']}",
        f"- avg_modules_renderable: {summary['avg_modules_renderable']}",
        f"- avg_data_quality_score: {summary['avg_data_quality_score']}",
        f"- total_provider_timeouts: {summary['total_provider_timeouts']}",
        f"- total_semantic_warnings: {summary['total_semantic_warnings']}",
        f"- total_strong_failures: {summary['total_strong_failures']}",
        "",
        "| Symbol | Pass | Modules | Quality | Semantic Warnings | Reasons |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for record in snapshot["records"]:
        lines.append(
            "| {symbol} | {smoke_gate_pass} | {modules_renderable} | {data_quality_score} | {semantic_warning_count} | {reasons} |".format(
                reasons=",".join(record.get("failure_reasons") or []),
                **record,
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")


async def run_daily(args: argparse.Namespace) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for symbol in _read_symbols(args):
        try:
            status, payload = await fetch_payload(
                base_url=args.base_url,
                market=args.market,
                symbol=symbol,
                include_raw=False,
                force_refresh=False,
                artifacts_dir=Path(args.artifacts_dir) if args.artifacts_dir else None,
            )
        except Exception as exc:
            status, payload = 0, {"error": type(exc).__name__, "message": str(exc)[:200]}
        records.append(analyze_smoke_payload(payload, symbol=symbol, http_status=status))
    today = datetime.now().strftime("%Y%m%d")
    snapshot = {"date": today, "summary": summarize_daily(records), "records": records}
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"company_v2_daily_health_{today}.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_md(out_dir / f"company_v2_daily_health_{today}.md", snapshot)
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Create CompanyV2 daily health snapshot.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--symbols", default="600519,000725,601686")
    parser.add_argument("--symbols-file", default=None)
    parser.add_argument("--market", default="CN")
    parser.add_argument("--out-dir", default="backend/docs/artifacts")
    parser.add_argument("--artifacts-dir", default=None)
    args = parser.parse_args()
    snapshot = asyncio.run(run_daily(args))
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0 if snapshot["summary"]["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
