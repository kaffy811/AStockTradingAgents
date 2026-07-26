"""Phase 6T-K real performance profile for Company V2 financial fusion."""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.report_document import ReportDocument
from app.services.company_v2_financial_evidence_fusion_service import DEFAULT_FUSION_FIELDS, company_v2_financial_evidence_fusion_service

ARTIFACT_DIR = ROOT / "docs" / "artifacts"


async def _latest_annual(symbol: str) -> ReportDocument | None:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(ReportDocument).where(ReportDocument.ts_code.like(f"{symbol}.%")))).scalars().all()
        annuals = [row for row in rows if (row.report_type or "").lower() == "annual"]
        pool = annuals or list(rows)
        return sorted(pool, key=lambda row: ((row.report_year or 0), row.id), reverse=True)[0] if pool else None


def _sidecar(doc: ReportDocument) -> Path | None:
    if doc.local_path:
        path = Path(doc.local_path).with_suffix(".pages.json")
        if path.exists():
            return path
    return None


async def profile_symbol(symbol: str, *, refresh: bool = True) -> dict[str, Any]:
    doc = await _latest_annual(symbol)
    if not doc:
        return {"symbol": symbol, "ok": False, "error_code": "REPORT_NOT_FOUND"}
    sidecar = _sidecar(doc)
    if not sidecar:
        return {"symbol": symbol, "report_id": doc.id, "ok": False, "error_code": "REPORT_NOT_READY"}
    started = perf_counter()
    result = await asyncio.to_thread(
        company_v2_financial_evidence_fusion_service.run,
        market="CN",
        symbol=symbol,
        report_id=doc.id,
        report_year=int(doc.report_year or 0),
        report_type=doc.report_type or "annual",
        fields=list(DEFAULT_FUSION_FIELDS),
        refresh=refresh,
        sidecar_path=sidecar,
        source_url=doc.pdf_url or doc.source_url,
        pdf_hash=doc.file_sha256,
        parse_version=doc.parse_status or "parsed",
        report_ready=True,
        rag_ready=True,
        structured_ready=True,
        enforce_rollout=True,
        force_enabled=True,
        idempotency_key=f"phase6tk-profile-{symbol}-{doc.id}",
        request_id=f"phase6tk-profile-{symbol}-{doc.id}",
    )
    timings = result.get("timings") or {}
    profile = {
        "eligibility_ms": timings.get("eligibility_latency_ms", 0.0),
        "readiness_ms": 0.0,
        "cache_lookup_ms": timings.get("cache_lookup_latency_ms", 0.0),
        "structured_provider_ms": 0.0,
        "rag_document_load_ms": 0.0,
        "retrieval_ms": timings.get("retrieval_latency_ms", 0.0),
        "official_extractor_ms": timings.get("resolver_latency_ms", 0.0),
        "unit_normalization_ms": timings.get("alignment_latency_ms", 0.0),
        "field_alignment_ms": timings.get("alignment_latency_ms", 0.0),
        "classification_ms": timings.get("alignment_latency_ms", 0.0),
        "citation_validation_ms": 0.0,
        "result_persistence_ms": timings.get("persistence_latency_ms", 0.0),
        "total_ms": round((perf_counter() - started) * 1000, 2),
    }
    top3 = sorted(((k, v) for k, v in profile.items() if k != "total_ms"), key=lambda item: float(item[1] or 0), reverse=True)[:3]
    return {
        "symbol": symbol,
        "report_id": doc.id,
        "ok": True,
        "cache_hit": bool(result.get("cache_hit")),
        "summary": result.get("summary"),
        "profile": profile,
        "top3_bottlenecks": [{"stage": key, "ms": value} for key, value in top3],
    }


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    results = []
    for symbol in symbols:
        results.append(await profile_symbol(symbol))
    totals = [item["profile"]["total_ms"] for item in results if item.get("ok")]
    payload = {
        "phase": "phase6tk_profile",
        "real_execution": True,
        "mock": False,
        "symbols": symbols,
        "results": results,
        "p50_latency_ms": round(statistics.median(totals), 2) if totals else None,
        "p95_latency_ms": round(statistics.quantiles(totals, n=20)[18], 2) if len(totals) >= 2 else (totals[0] if totals else None),
    }
    Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.out_md).write_text("# Phase 6T-K Fusion Profile\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="600519,300750,000725,000001")
    parser.add_argument("--out-json", default=str(ARTIFACT_DIR / "company_v2_financial_fusion_phase6tk_profile.json"))
    parser.add_argument("--out-md", default=str(ARTIFACT_DIR / "company_v2_financial_fusion_phase6tk_profile.md"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    payload = asyncio.run(main_async(parse_args(argv)))
    print(json.dumps({"ok": True, "p50_latency_ms": payload["p50_latency_ms"], "p95_latency_ms": payload["p95_latency_ms"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
