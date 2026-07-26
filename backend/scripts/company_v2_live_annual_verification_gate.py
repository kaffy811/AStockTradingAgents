"""Run Phase 6T-C1 live annual-history official verification gate.

By default this uses the local FastAPI ASGI app, so it exercises the same
routes as HTTP without requiring a separate uvicorn process. Pass --base-url
to target a deployed dev/staging API.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _first_annual_report(discover: dict[str, Any], *, year: int = 2024, report_type: str = "annual") -> dict[str, Any] | None:
    for report in discover.get("reports") or []:
        if report.get("report_year") == year and report.get("report_type") == report_type and report.get("pdf_url"):
            return report
    return None


def _summary_markdown(*, discover: dict[str, Any], download: dict[str, Any], parse: dict[str, Any], verify: dict[str, Any], report: dict[str, Any]) -> str:
    verification = verify.get("official_verification") or {}
    fields = verification.get("fields") or {}
    official_fields = verify.get("official_fields") or {}
    extracted = [key for key, value in official_fields.items() if value]
    conflict_types: dict[str, int] = {}
    for entry in fields.values():
        key = entry.get("reason_code") or entry.get("conflict_type") or entry.get("reason")
        if key:
            conflict_types[key] = conflict_types.get(key, 0) + 1
    return "\n".join([
        "# CompanyV2 Phase 6T-C2 Lite Live Verification Summary",
        "",
        f"- report_id: {report.get('report_id') or report.get('id')}",
        f"- report_year: {report.get('report_year')}",
        f"- report_type: {report.get('report_type')}",
        f"- pdf_url: {report.get('pdf_url')}",
        f"- download_status: {download.get('status')}",
        f"- parse_status: {parse.get('parse_status') or parse.get('status')}",
        f"- official_fields_extracted: {', '.join(extracted) if extracted else 'none'}",
        f"- structured_period_matched: {verification.get('structured_period_matched')}",
        f"- verified_fields_count: {verification.get('verified_fields_count', 0)}",
        f"- conflict_fields_count: {verification.get('conflict_fields_count', 0)}",
        f"- unverified_fields_count: {verification.get('unverified_fields_count', 0)}",
        f"- period_mismatch_count: {verification.get('period_mismatch_count', 0)}",
        f"- unit_mismatch_count: {verification.get('unit_mismatch_count', 0)}",
        f"- extraction_low_confidence_count: {verification.get('extraction_low_confidence_count', 0)}",
        f"- provider_value_conflict_count: {verification.get('provider_value_conflict_count', 0)}",
        f"- safe_for_rag_fields: {[k for k, v in fields.items() if v.get('safe_for_rag')]}",
        f"- manual_review_fields: {[k for k, v in fields.items() if v.get('requires_manual_review')]}",
        f"- conflict_classification: {conflict_types}",
        f"- final_verification_status: {verification.get('status')}",
        "",
        "说明：conflict / mismatch / unverified 字段默认 safe_for_rag=false，只能作为待复核字段展示。",
    ])


def _manual_review_markdown(verify: dict[str, Any]) -> str:
    fields = (verify.get("official_verification") or {}).get("fields") or {}
    rows = [
        "| field | status | reason_code | provider_value | official_value | review_priority | safe_for_rag | suggested_action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for field, entry in fields.items():
        if not entry.get("requires_manual_review"):
            continue
        policy = entry.get("rag_usage_policy") or {}
        rows.append(
            "| {field} | {status} | {reason} | {provider} | {official} | {priority} | {safe} | {action} |".format(
                field=field,
                status=entry.get("status"),
                reason=entry.get("reason_code") or "",
                provider=entry.get("provider_value"),
                official=entry.get("official_value"),
                priority=entry.get("review_priority"),
                safe=entry.get("safe_for_rag"),
                action=(policy.get("suggested_caveat") or entry.get("review_reason") or "").replace("|", "/"),
            )
        )
    if len(rows) == 2:
        rows.append("| none | verified | VERIFIED | - | - | low | true | no manual review required |")
    return "\n".join([
        "# CompanyV2 Phase 6T-C2 Lite Manual Review Queue",
        "",
        *rows,
        "",
    ])


async def _client(base_url: str | None):
    if base_url:
        return httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=120)
    from httpx import ASGITransport
    from app.main import app
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver", timeout=120)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--market", default="CN")
    parser.add_argument("--symbol", default="601686")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--report-type", default="annual")
    parser.add_argument("--phase", default="phase6tc2")
    parser.add_argument("--out-dir", default="backend/docs/artifacts")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    prefix = f"company_v2_{args.symbol}_live"
    async with await _client(args.base_url) as client:
        discover_resp = await client.get(
            f"/api/v2/company/{args.market}/{args.symbol}/reports/discover",
            params={"start_year": args.year, "end_year": args.year, "report_type": args.report_type, "force_refresh": "true"},
        )
        discover = discover_resp.json()
        _write(out_dir / f"{prefix}_discover_{args.phase}.json", discover)
        report = _first_annual_report(discover, year=args.year, report_type=args.report_type)
        if not report:
            failure = {"ok": False, "error_code": "ANNUAL_REPORT_NOT_FOUND", "discover": discover}
            _write(out_dir / f"{prefix}_verify_{args.phase}.json", failure)
            print(json.dumps(failure, ensure_ascii=False, indent=2))
            return 1
        report_id = report.get("report_id") or report.get("id")
        if not report_id:
            failure = {"ok": False, "error_code": "REPORT_ID_MISSING", "report": report}
            _write(out_dir / f"{prefix}_verify_{args.phase}.json", failure)
            print(json.dumps(failure, ensure_ascii=False, indent=2))
            return 1

        download = (await client.post(f"/api/v2/company/{args.market}/{args.symbol}/reports/{report_id}/download")).json()
        _write(out_dir / f"{prefix}_download_{args.phase}.json", download)
        parse = (await client.post(f"/api/v2/company/{args.market}/{args.symbol}/reports/{report_id}/parse")).json()
        _write(out_dir / f"{prefix}_parse_{args.phase}.json", parse)
        verify = (await client.post(f"/api/v2/company/{args.market}/{args.symbol}/reports/{report_id}/verify")).json()
        _write(out_dir / f"{prefix}_verify_{args.phase}.json", verify)
        (out_dir / f"{prefix}_verification_summary_{args.phase}.md").write_text(
            _summary_markdown(discover=discover, download=download, parse=parse, verify=verify, report=report),
            encoding="utf-8",
        )
        (out_dir / f"company_v2_{args.symbol}_manual_review_queue_{args.phase}_lite.md").write_text(
            _manual_review_markdown(verify),
            encoding="utf-8",
        )
        print(json.dumps({
            "ok": True,
            "report_id": report_id,
            "download_status": download.get("status"),
            "parse_status": parse.get("parse_status") or parse.get("status"),
            "verification_status": (verify.get("official_verification") or {}).get("status"),
            "structured_period_matched": (verify.get("official_verification") or {}).get("structured_period_matched"),
            "verified_fields_count": (verify.get("official_verification") or {}).get("verified_fields_count"),
            "conflict_fields_count": (verify.get("official_verification") or {}).get("conflict_fields_count"),
            "unverified_fields_count": (verify.get("official_verification") or {}).get("unverified_fields_count"),
            "manual_review_fields": [k for k, v in ((verify.get("official_verification") or {}).get("fields") or {}).items() if v.get("requires_manual_review")],
        }, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
