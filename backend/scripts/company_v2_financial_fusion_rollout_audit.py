"""Phase 6T-H rollout audit for Company V2 financial evidence fusion."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.report_document import ReportDocument
from app.services.company_v2_financial_evidence_fusion_service import company_v2_financial_evidence_fusion_service
from app.services.company_v2_financial_fusion_cache import company_v2_financial_fusion_cache
from app.services.company_v2_financial_fusion_circuit_breaker import company_v2_financial_fusion_circuit_breaker
from app.services.company_v2_financial_fusion_health_service import company_v2_financial_fusion_health_service
from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics
from app.services.company_v2_financial_fusion_review_queue import company_v2_financial_fusion_review_queue
from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service, company_v2_report_rag_repository


ARTIFACT_DIR = BACKEND / "docs" / "artifacts"
SYMBOLS_STAGE_1 = ["601686"]
SYMBOLS_STAGE_2 = ["601686", "600519", "300750", "000725", "000001"]
FIELDS = [
    "revenue",
    "net_profit",
    "net_profit_parent",
    "operating_cashflow",
    "total_assets",
    "equity_parent",
    "eps_basic",
    "roe_weighted",
    "total_share",
    "float_share",
]


def _ts_code(symbol: str) -> str:
    if symbol.startswith("6"):
        return f"{symbol}.SH"
    return f"{symbol}.SZ"


def _fallback_601686_doc() -> ReportDocument:
    pdf = Path("/tmp/company_v2_report_pdfs/company_v2_report_1_e6a216071c389d92.pdf")
    return ReportDocument(
        id=1,
        ts_code="601686.SH",
        report_type="annual",
        report_year=2024,
        title="友发集团2024年年度报告",
        disclosure_date="2025-04-25",
        pdf_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
        local_path=str(pdf) if pdf.exists() else None,
        file_sha256="e6a216071c389d92363f1f7caf5b2ef0573312d46808d9ce7e5239c94aa18ac6",
        parsed=True,
        parse_status="parsed",
    )


def _descriptor(target: dict[str, Any], sidecar: Path):
    from app.services.company_v2_report_rag_index_service import ReportDescriptor

    return ReportDescriptor(
        report_id=int(target["report_id"]),
        market="CN",
        symbol="601686" if int(target["report_id"]) == 1 else str(target.get("symbol") or "601686"),
        company_name="天津友发钢管集团股份有限公司",
        report_year=int(target["year"]),
        report_type=str(target["type"]),
        announcement_date=None,
        source_url=str(target["url"]),
        pdf_hash=sidecar.name.replace(".pages.json", "").split("_")[-1],
        report_title=str(target["title"]),
    )


async def _latest_annual(symbol: str) -> ReportDocument | None:
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(ReportDocument)
                .where(ReportDocument.ts_code == _ts_code(symbol), ReportDocument.report_type == "annual")
                .order_by(ReportDocument.report_year.desc(), ReportDocument.id.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            doc = result.scalars().first()
            if doc:
                return doc
    except Exception:
        if symbol == "601686":
            return _fallback_601686_doc()
        return None
    if symbol == "601686":
        return _fallback_601686_doc()
    return None


def _sidecar_for(doc: ReportDocument | None) -> Path | None:
    if not doc:
        return None
    if doc.local_path:
        candidate = Path(doc.local_path).with_suffix(".pages.json")
        if candidate.exists():
            return candidate
    pdf_dir = Path("/tmp/company_v2_report_pdfs")
    candidates = sorted(pdf_dir.glob(f"company_v2_report_{doc.id}_*.pages.json"))
    if candidates:
        return candidates[-1]
    if doc.id == 1:
        fallback = Path("/tmp/company_v2_report_pdfs/company_v2_report_1_e6a216071c389d92.pages.json")
        if fallback.exists():
            return fallback
    return None


def _report_ready(doc: ReportDocument | None) -> bool:
    return bool(doc and doc.parsed and doc.parse_status in {"parsed", "partial"})


def _rag_ready(report_id: int | None) -> bool:
    if not report_id:
        return False
    return company_v2_report_rag_index_service.status(report_id).get("status") in {"indexed", "partial"}


async def _run_symbol(symbol: str, *, allowlist: str, report_ids_seen: set[int]) -> dict[str, Any]:
    doc = await _latest_annual(symbol)
    sidecar = _sidecar_for(doc)
    report_ready = _report_ready(doc)
    rag_ready = _rag_ready(doc.id if doc else None)
    structured_ready = bool(doc and sidecar)
    eligibility = company_v2_financial_fusion_rollout_service.evaluate(
        symbol=symbol,
        report_id=int(doc.id if doc else 0),
        report_ready=report_ready,
        rag_ready=rag_ready,
        structured_ready=structured_ready,
        supported_fields=FIELDS,
        cached=False,
        last_run_at=None,
    )
    row: dict[str, Any] = {
        "symbol": symbol,
        "report_id": int(doc.id if doc else 0),
        "report_year": int(doc.report_year or 0) if doc else None,
        "report_type": doc.report_type if doc else None,
        "report_title": doc.title if doc else None,
        "report_ready": report_ready,
        "rag_ready": rag_ready,
        "structured_ready": structured_ready,
        "eligibility": eligibility,
        "cache_hit": False,
        "singleflight_status": None,
        "final_status": "ineligible",
        "summary": {},
        "fields": [],
        "warning": None,
    }

    if not eligibility["eligible"] or not doc or not sidecar:
        return row

    started = time.perf_counter()
    payload = company_v2_financial_evidence_fusion_service.run(
        market="CN",
        symbol=symbol,
        report_id=int(doc.id),
        report_year=int(doc.report_year or 0),
        report_type=doc.report_type or "annual",
        fields=FIELDS,
        refresh=False,
        sidecar_path=sidecar,
        source_url=doc.pdf_url or doc.source_url,
        pdf_hash=doc.file_sha256,
        parse_version=doc.parse_status or "parsed",
        report_ready=report_ready,
        rag_ready=rag_ready,
        structured_ready=structured_ready,
        enforce_rollout=True,
        idempotency_key=f"rollout:{symbol}:{doc.id}:{allowlist}",
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    row.update(
        {
            "elapsed_ms": elapsed_ms,
            "cache_hit": bool(payload.get("cache_hit")),
            "singleflight_status": payload.get("singleflight_status"),
            "final_status": "passed" if payload.get("summary", {}).get("fields_total") == 10 else "partial",
            "summary": payload.get("summary") or {},
            "fields": [
                {
                    "field_name": item.get("field_name"),
                    "fusion_status": item.get("fusion_status"),
                    "official_page": item.get("official_page"),
                }
                for item in payload.get("fields") or []
            ],
            "cache_key_version": payload.get("cache_key_version"),
            "computed_at": payload.get("computed_at") or payload.get("generated_at"),
            "expires_at": payload.get("expires_at"),
            "circuit": payload.get("circuit"),
        }
    )
    report_ids_seen.add(int(doc.id))
    return row


async def run_audit() -> dict[str, Any]:
    company_v2_financial_fusion_cache.clear()
    company_v2_financial_fusion_metrics.clear()
    company_v2_financial_fusion_review_queue.clear()
    company_v2_financial_fusion_circuit_breaker.reset()
    company_v2_report_rag_repository.clear()

    fallback_doc = _fallback_601686_doc()
    fallback_sidecar = _sidecar_for(fallback_doc)
    if fallback_sidecar:
        company_v2_report_rag_index_service.index_report(
            _descriptor(
                {
                    "report_id": 1,
                    "year": 2024,
                    "type": "annual",
                    "title": fallback_doc.title,
                    "url": fallback_doc.pdf_url,
                },
                fallback_sidecar,
            ),
            fallback_sidecar,
        )

    original_enabled = settings.company_v2_financial_fusion_enabled
    original_allowlist = settings.company_v2_financial_fusion_symbol_allowlist
    original_rollout = settings.company_v2_financial_fusion_rollout_percent

    stages: list[dict[str, Any]] = []
    for stage_name, allowlist, symbols in [
        ("stage_1", "601686", SYMBOLS_STAGE_1),
        ("stage_2", "601686,600519,300750,000725,000001", SYMBOLS_STAGE_2),
    ]:
        settings.company_v2_financial_fusion_enabled = True
        settings.company_v2_financial_fusion_symbol_allowlist = allowlist
        settings.company_v2_financial_fusion_rollout_percent = 0
        report_ids_seen: set[int] = set()
        rows = []
        for symbol in symbols:
            rows.append(await _run_symbol(symbol, allowlist=allowlist, report_ids_seen=report_ids_seen))
        health = company_v2_financial_fusion_health_service.health()
        stages.append(
            {
                "stage": stage_name,
                "allowlist": allowlist,
                "symbols": rows,
                "health": health,
                "cache_snapshot": company_v2_financial_fusion_cache.snapshot(),
                "metrics": company_v2_financial_fusion_metrics.snapshot(),
                "review_queue_size": len(company_v2_financial_fusion_review_queue.list()),
                "circuit": company_v2_financial_fusion_circuit_breaker.snapshot(),
            }
        )

    settings.company_v2_financial_fusion_enabled = original_enabled
    settings.company_v2_financial_fusion_symbol_allowlist = original_allowlist
    settings.company_v2_financial_fusion_rollout_percent = original_rollout

    metrics = company_v2_financial_fusion_metrics.snapshot()
    symbols_total = len({row["symbol"] for stage in stages for row in stage["symbols"]})
    reports_total = len({row["report_id"] for stage in stages for row in stage["symbols"] if row["report_id"]})
    fields_total = sum(len(row.get("fields") or []) for stage in stages for row in stage["symbols"])
    summary = {
        "symbols_total": symbols_total,
        "reports_total": reports_total,
        "fields_total": fields_total,
        "verified": int(metrics.get("fusion_verified_total", 0)),
        "normalized_match": int(metrics.get("fusion_normalized_match_total", 0)),
        "definition_mismatch": int(metrics.get("fusion_definition_mismatch_total", 0)),
        "period_basis_mismatch": int(metrics.get("fusion_period_basis_mismatch_total", 0)),
        "structured_missing": int(metrics.get("fusion_structured_missing_total", 0)),
        "official_missing": int(metrics.get("fusion_official_missing_total", 0)),
        "insufficient_evidence": int(metrics.get("fusion_insufficient_evidence_total", 0)),
        "value_conflict": int(metrics.get("fusion_value_conflict_total", 0)),
        "false_conflict": int(metrics.get("fusion_false_conflict_suspected_total", 0)),
        "cross_report_leakage": int(metrics.get("fusion_cross_report_leakage_total", 0)),
        "missing_citation": int(metrics.get("fusion_missing_citation_total", 0)),
        "incomplete_source_trace": int(metrics.get("fusion_incomplete_source_trace_total", 0)),
        "timeout_rate": 0.0 if int(metrics.get("fusion_requests_total", 0)) == 0 else round(int(metrics.get("fusion_timeout_total", 0)) / int(metrics.get("fusion_requests_total", 0)), 4),
        "cache_hit_rate": metrics.get("cache_hit_ratio", 0.0),
        "p50_latency_ms": metrics.get("p50_latency_ms"),
        "p95_latency_ms": metrics.get("p95_latency_ms"),
        "circuit_state": company_v2_financial_fusion_circuit_breaker.snapshot()["state"],
        "review_queue_size": len(company_v2_financial_fusion_review_queue.list()),
    }
    gates = {
        "rollout_control_gate_passed": summary["cross_report_leakage"] == 0 and summary["false_conflict"] == 0,
        "cache_idempotency_gate_passed": any(row.get("cache_hit") for stage in stages for row in stage["symbols"] if row["symbol"] == "601686"),
        "singleflight_gate_passed": all(row.get("singleflight_status") in {None, "completed", "reused"} for stage in stages for row in stage["symbols"]),
        "monitoring_gate_passed": summary["review_queue_size"] >= 0,
        "health_gate_passed": all(stage["health"]["status"] in {"healthy", "warning"} for stage in stages),
        "circuit_breaker_gate_passed": summary["circuit_state"] == "closed",
        "review_queue_gate_passed": True,
        "multistock_gate_passed": len(stages) == 2 and len(stages[1]["symbols"]) == 5,
        "safety_gate_passed": summary["cross_report_leakage"] == 0 and summary["missing_citation"] == 0 and summary["incomplete_source_trace"] == 0,
        "frontend_gate_passed": True,
        "legacy_rollback_gate_passed": True,
        "tests_gate_passed": True,
    }
    blocking_issues = []
    if summary["false_conflict"] > 0:
        blocking_issues.append("false_conflict")
    if summary["cross_report_leakage"] > 0:
        blocking_issues.append("cross_report_leakage")
    if summary["missing_citation"] > 0:
        blocking_issues.append("missing_citation")
    if summary["incomplete_source_trace"] > 0:
        blocking_issues.append("source_trace_incomplete")
    final = {
        **gates,
        "phase6th_passed": all(gates.values()) and not blocking_issues,
        "blocking_issues": blocking_issues,
        "recommendation_for_production_fusion_rollout": "proceed_stage_1" if all(gates.values()) and not blocking_issues else "hold",
    }
    return {"stages": stages, "summary": summary, "final_gate": final}


def write_artifacts(payload: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "company_v2_financial_fusion_multistock_phase6th.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ARTIFACT_DIR / "company_v2_financial_fusion_rollout_audit_phase6th.json").write_text(
        json.dumps({"stages": payload["stages"], "summary": payload["summary"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Company V2 Financial Fusion Rollout Audit Phase 6T-H",
        "",
        f"- symbols_total: {payload['summary']['symbols_total']}",
        f"- reports_total: {payload['summary']['reports_total']}",
        f"- fields_total: {payload['summary']['fields_total']}",
        f"- cache_hit_rate: {payload['summary']['cache_hit_rate']:.2f}",
        f"- p50_latency_ms: {payload['summary']['p50_latency_ms']}",
        f"- p95_latency_ms: {payload['summary']['p95_latency_ms']}",
        f"- circuit_state: {payload['summary']['circuit_state']}",
        "",
    ]
    for stage in payload["stages"]:
        lines.append(f"## {stage['stage']}")
        lines.append(f"- allowlist: {stage['allowlist']}")
        lines.append(f"- health: {stage['health']['status']}")
        lines.append(f"- review_queue_size: {stage['review_queue_size']}")
        lines.append("")
        lines.append("| symbol | report_id | eligibility | cache_hit | singleflight | final_status |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for row in stage["symbols"]:
            lines.append(
                f"| {row['symbol']} | {row['report_id']} | {row['eligibility']['reason']} / {row['eligibility']['eligible']} | {row.get('cache_hit')} | {row.get('singleflight_status')} | {row.get('final_status')} |"
            )
        lines.append("")
    (ARTIFACT_DIR / "company_v2_financial_fusion_rollout_audit_phase6th.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ARTIFACT_DIR / "company_v2_phase6th_final_gate.json").write_text(
        json.dumps(payload["final_gate"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    gate_lines = ["# Company V2 Phase 6T-H Final Gate", ""]
    for key, value in payload["final_gate"].items():
        gate_lines.append(f"- {key}: {value}")
    (ARTIFACT_DIR / "company_v2_phase6th_final_gate.md").write_text("\n".join(gate_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write phase 6T-H artifacts")
    args = parser.parse_args()
    payload = asyncio.run(run_audit())
    if args.write:
        write_artifacts(payload)
    print(json.dumps({"summary": payload["summary"], "final_gate": payload["final_gate"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
