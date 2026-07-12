#!/usr/bin/env python3
"""Phase 6T-J: generate structured verification seed artifacts for the Stage 2
target symbols (600519/300750/000725/000001) by reusing the Phase 6T-C chain.

Thin driver only — reuses:
- company_v2_debug_service.build_full (real structured provider data)
- company_v2_ai_official_verification_agent.verify_with_ai (real LLM)
- sanitize_ai_verification_payload (no local_path / no full PDF text)

Scope guards:
- uses ONLY the already-discovered/downloaded/parsed ReportDocuments (2-5);
- no discovery / download / parse / index / fusion here;
- one seed artifact per symbol: company_v2_{symbol}_ai_official_verification_phase6tj.json
  (glob-compatible with the fusion service's _artifact_paths).

Usage:
    cd backend && .venv/bin/python scripts/company_v2_run_phase6tj_seed_verify.py \
        [--symbols 600519,300750,000725,000001]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.models.report_document import ReportDocument
from app.services.company_v2_ai_official_verification_agent import verify_with_ai
from app.services.company_v2_ai_verification_response import sanitize_ai_verification_payload
from app.services.company_v2_debug_service import company_v2_debug_service

ARTIFACT_DIR = ROOT / "docs" / "artifacts"
MARKET = "CN"
REPORT_TYPE = "annual"
REPORT_YEAR = 2025
# Explicit, audited mapping — never guess report_ids.
TARGETS = {"600519": 2, "300750": 3, "000725": 4, "000001": 5}


def _contains(text_payload: Any, needle: str) -> bool:
    return needle in json.dumps(text_payload, ensure_ascii=False, default=str)


async def _run_symbol(symbol: str, report_id: int) -> dict[str, Any]:
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        doc = (
            await db.execute(select(ReportDocument).where(ReportDocument.id == report_id))
        ).scalars().first()
        if not doc or not doc.ts_code.startswith(symbol):
            return {"symbol": symbol, "ok": False, "error_code": "REPORT_ID_SYMBOL_MISMATCH"}
        if int(doc.report_year or 0) != REPORT_YEAR or (doc.report_type or "") != REPORT_TYPE:
            return {"symbol": symbol, "ok": False, "error_code": "REPORT_YEAR_TYPE_MISMATCH"}
        sidecar = Path(doc.local_path).with_suffix(".pages.json") if doc.local_path else None
        if not sidecar or not sidecar.exists():
            return {"symbol": symbol, "ok": False, "error_code": "SIDECAR_MISSING"}
        parsed_source = json.loads(sidecar.read_text(encoding="utf-8"))

        debug_data = await company_v2_debug_service.build_full(
            MARKET,
            symbol,
            include_raw=False,
            providers=None,
            force_refresh=False,
            max_raw_chars=5000,
            db=db,
            history=True,
            period="annual",
            start_year=REPORT_YEAR,
            end_year=REPORT_YEAR,
        )

        report_document = {
            "report_id": report_id,
            "ts_code": doc.ts_code,
            "symbol": symbol,
            "report_year": REPORT_YEAR,
            "report_type": REPORT_TYPE,
            "pdf_url": doc.pdf_url,
            "source": doc.source or "cninfo",
        }
        ai_result = await asyncio.to_thread(
            verify_with_ai,
            report_document,
            parsed_source,
            debug_data,
            None,
            REPORT_YEAR,
            REPORT_TYPE,
        )

    payload = sanitize_ai_verification_payload(
        {
            "ok": True,
            "report_id": report_id,
            "symbol": symbol,
            "report_year": REPORT_YEAR,
            "report_type": REPORT_TYPE,
            "pdf_url": doc.pdf_url,
            "page_count": parsed_source.get("page_count"),
            "ai_verification_status": ai_result.get("verification_status"),
            "fields": ai_result.get("fields") or {},
            "human_review_queue": ai_result.get("human_review_queue") or [],
            "warnings": ai_result.get("warnings") or [],
        }
    )
    official = ARTIFACT_DIR / f"company_v2_{symbol}_ai_official_verification_phase6tj.json"
    queue = ARTIFACT_DIR / f"company_v2_{symbol}_ai_human_review_queue_phase6tj.json"
    official.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    queue.write_text(
        json.dumps(
            {"report_id": report_id, "symbol": symbol, "human_review_queue": payload.get("human_review_queue") or []},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    fields = payload.get("fields") or {}
    statuses: dict[str, int] = {}
    for entry in fields.values():
        if isinstance(entry, dict):
            statuses[entry.get("status") or "unknown"] = statuses.get(entry.get("status") or "unknown", 0) + 1
    return {
        "symbol": symbol,
        "ok": True,
        "report_id": report_id,
        "fields_checked": len(fields),
        "status_counts": statuses,
        "ai_verification_status": payload.get("ai_verification_status"),
        "human_review_queue_count": len(payload.get("human_review_queue") or []),
        "local_path_leaked": _contains(payload, "local_path"),
        "full_pdf_text_returned": _contains(payload, "text_pages"),
        "artifact": official.name,
    }


async def main_async(symbols: list[str]) -> int:
    results = []
    for symbol in symbols:
        report_id = TARGETS.get(symbol)
        if not report_id:
            results.append({"symbol": symbol, "ok": False, "error_code": "SYMBOL_NOT_IN_SCOPE"})
            continue
        results.append(await _run_symbol(symbol, report_id))
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0 if all(r.get("ok") for r in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 6T-J structured seed generation (real LLM)")
    parser.add_argument("--symbols", default=",".join(TARGETS))
    args = parser.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    return asyncio.run(main_async(symbols))


if __name__ == "__main__":
    raise SystemExit(main())
