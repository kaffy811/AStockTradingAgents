"""Phase 6T-J Stage 2 manual preparation for Company V2 financial fusion."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.report_document import ReportDocument
from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics
from app.services.company_v2_financial_fusion_stage2_plan import company_v2_financial_fusion_stage2_plan_service
from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
from app.services.company_v2_report_rag_index_service import ReportDescriptor, company_v2_report_rag_index_service
from app.services.report_pdf_download_service import report_pdf_download_service
from app.services.report_text_extract_service import report_text_extract_service

ARTIFACT_DIR = ROOT / "docs" / "artifacts"
DEFAULT_SYMBOLS = ["600519", "300750", "000725", "000001"]
DEFAULT_STEP = "download"
DEFAULT_TIMEOUT = 180.0
STAGE2_JSON = ARTIFACT_DIR / "company_v2_financial_fusion_stage2_prepare_phase6tj.json"
STAGE2_MD = ARTIFACT_DIR / "company_v2_financial_fusion_stage2_prepare_phase6tj.md"
STAGE2_MULTI_JSON = ARTIFACT_DIR / "company_v2_financial_fusion_stage2_multistock_phase6tj.json"
CHECKPOINT_PATH = ARTIFACT_DIR / "company_v2_financial_fusion_stage2_prepare_phase6tj.checkpoint.json"


@dataclass(slots=True)
class SymbolStepResult:
    symbol: str
    report_id: int | None
    report_year: int | None
    report_type: str | None
    step: str
    status: str
    ok: bool
    timeout: bool
    elapsed_ms: float
    duplicate_download_avoided: bool | None = None
    download_status: str | None = None
    parse_status: str | None = None
    index_status: str | None = None
    rag_document_id: int | None = None
    page_count_if_available: int | None = None
    chunk_count: int | None = None
    embedded_chunks: int | None = None
    pdf_hash: str | None = None
    file_size: int | None = None
    error: str | None = None
    error_code: str | None = None
    current_job: dict[str, Any] | None = None
    next_manual_action: str | None = None
    fusion_readiness: str | None = None
    report_title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _report_descriptor(doc: ReportDocument, symbol: str) -> ReportDescriptor:
    return ReportDescriptor(
        report_id=int(doc.id),
        market="CN",
        symbol=symbol,
        company_name=None,
        report_year=int(doc.report_year or 0),
        report_type=doc.report_type or "annual",
        announcement_date=doc.disclosure_date,
        source_url=doc.pdf_url or doc.source_url or "",
        pdf_hash=doc.file_sha256,
        report_title=doc.title,
    )


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"step": None, "symbols": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"step": None, "symbols": {}}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Phase 6T-J Stage 2 Manual Preparation",
        "",
        f"- step: {payload.get('step')}",
        f"- symbols: {', '.join(payload.get('symbols', []))}",
        f"- ready_symbols: {payload.get('summary', {}).get('ready_symbols', 0)}",
        f"- failed_symbols: {payload.get('summary', {}).get('failed_symbols', 0)}",
        "",
        "## Summary",
        json.dumps(payload.get("summary", {}), ensure_ascii=False, indent=2),
        "",
        "## Results",
        json.dumps(payload.get("results", []), ensure_ascii=False, indent=2),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


async def _load_latest_annual_doc(db, symbol: str) -> ReportDocument | None:
    result = await db.execute(select(ReportDocument).where(ReportDocument.ts_code.like(f"{symbol}.%")))
    docs = list(result.scalars().all())
    annuals = [doc for doc in docs if (doc.report_type or "").lower() == "annual"]
    pool = annuals or docs
    if not pool:
        return None
    return sorted(pool, key=lambda item: ((item.report_year or 0), item.id), reverse=True)[0]


async def _run_symbol_step(symbol: str, step: str, timeout_seconds: float) -> SymbolStepResult:
    started = perf_counter()
    async with AsyncSessionLocal() as db:
        doc = await _load_latest_annual_doc(db, symbol)
        if not doc:
            return SymbolStepResult(
                symbol=symbol,
                report_id=None,
                report_year=None,
                report_type=None,
                step=step,
                status="report_not_discovered",
                ok=False,
                timeout=False,
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
                error="no report found",
                error_code="REPORT_NOT_DISCOVERED",
            )

        async def _download() -> dict[str, Any]:
            return await report_pdf_download_service.download(doc.id, db)

        async def _parse() -> dict[str, Any]:
            return await report_text_extract_service.parse(doc.id, db)

        async def _index() -> dict[str, Any]:
            if not doc.local_path:
                return {"ok": False, "status": "failed", "error_code": "PDF_NOT_DOWNLOADED", "message": "PDF not downloaded"}
            sidecar = Path(doc.local_path).with_suffix(".pages.json")
            if not sidecar.exists():
                return {"ok": False, "status": "failed", "error_code": "PDF_NOT_PARSED", "message": "page sidecar unavailable"}
            return await asyncio.to_thread(company_v2_report_rag_index_service.index_report, _report_descriptor(doc, symbol), sidecar)

        work = {"download": _download, "parse": _parse, "index": _index}.get(step)
        if not work:
            return SymbolStepResult(
                symbol=symbol,
                report_id=doc.id,
                report_year=doc.report_year,
                report_type=doc.report_type,
                step=step,
                status="failed",
                ok=False,
                timeout=False,
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
                error=f"unsupported step: {step}",
                error_code="UNSUPPORTED_STEP",
            )

        try:
            result = await asyncio.wait_for(work(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return SymbolStepResult(
                symbol=symbol,
                report_id=doc.id,
                report_year=doc.report_year,
                report_type=doc.report_type,
                step=step,
                status="timed_out",
                ok=False,
                timeout=True,
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
                error=f"symbol timeout exceeded: {timeout_seconds}s",
                error_code="SYMBOL_TIMEOUT_EXCEEDED",
            )
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        download_status = result.get("status") or doc.download_status
        parse_status = result.get("status") or doc.parse_status
        index_status = result.get("status") if step == "index" else company_v2_report_rag_index_service.status(doc.id).get("status")
        prepare_status = await company_v2_financial_fusion_stage2_plan_service.get_report_prepare_status("CN", symbol, doc.id, db)
        payload = SymbolStepResult(
            symbol=symbol,
            report_id=doc.id,
            report_year=doc.report_year,
            report_type=doc.report_type,
            step=step,
            status=result.get("status") or "failed",
            ok=bool(result.get("ok", result.get("status") in {"downloaded", "exists", "parsed", "partial", "indexed"})),
            timeout=False,
            elapsed_ms=elapsed_ms,
            duplicate_download_avoided=bool(result.get("status") == "exists") if step == "download" else None,
            download_status=download_status,
            parse_status=parse_status,
            index_status=index_status,
            rag_document_id=result.get("rag_document_id"),
            page_count_if_available=result.get("page_count") or None,
            chunk_count=result.get("chunk_count"),
            embedded_chunks=result.get("embedded_chunks"),
            pdf_hash=result.get("sha256") or doc.file_sha256,
            file_size=result.get("file_size") or doc.file_size,
            error=None if result.get("ok", True) else result.get("message") or result.get("reason"),
            error_code=result.get("error_code"),
            current_job=company_v2_report_rag_index_manager.get_index_progress(doc.id),
            next_manual_action=prepare_status.get("next_manual_action"),
            fusion_readiness=prepare_status.get("fusion_readiness"),
            report_title=doc.title,
        )
        return payload


async def run_stage2_prepare(step: str, symbols: list[str], timeout_seconds: float, checkpoint_path: Path, *, resume: bool) -> dict[str, Any]:
    checkpoint = _load_checkpoint(checkpoint_path) if resume else {"step": step, "symbols": {}}
    checkpoint_step = checkpoint.get("step")
    if checkpoint_step and checkpoint_step != step:
        checkpoint = {"step": step, "symbols": {}}
    checkpoint.setdefault("symbols", {})

    results: list[dict[str, Any]] = []
    for symbol in symbols:
        symbol_checkpoint = checkpoint["symbols"].get(symbol, {})
        resume_note: str | None = None
        if symbol_checkpoint.get(step) and symbol_checkpoint[step].get("ok") and not symbol_checkpoint[step].get("timeout"):
            if step == "index":
                # Phase 6T-J1: checkpoint ok=true is NOT sufficient for index —
                # verify a persisted active document actually exists. A missing
                # document (e.g. legacy in-memory index) forces a real re-index.
                checkpoint_report_id = symbol_checkpoint[step].get("report_id")
                persisted_doc = None
                if checkpoint_report_id:
                    try:
                        persisted_doc = await asyncio.to_thread(
                            company_v2_report_rag_index_service.repository.get_document,
                            int(checkpoint_report_id),
                        )
                    except Exception:
                        persisted_doc = None
                if persisted_doc is not None:
                    results.append(symbol_checkpoint[step])
                    continue
                resume_note = "PERSISTENCE_MISSING_REINDEX_REQUIRED"
            else:
                results.append(symbol_checkpoint[step])
                continue
        result = await _run_symbol_step(symbol, step, timeout_seconds)
        result_dict = result.to_dict()
        if resume_note:
            result_dict["resume_note"] = resume_note
        checkpoint["symbols"].setdefault(symbol, {})[step] = result_dict
        _write_json(checkpoint_path, checkpoint)
        results.append(result_dict)

    summary = {
        "requests_total": len(symbols),
        "ready_symbols": sum(1 for item in results if item.get("ok") and not item.get("timeout")),
        "failed_symbols": sum(1 for item in results if not item.get("ok") and not item.get("timeout")),
        "timed_out_symbols": sum(1 for item in results if item.get("timeout")),
        "duplicate_downloads_avoided": sum(1 for item in results if item.get("duplicate_download_avoided")),
        "elapsed_ms_total": round(sum(float(item.get("elapsed_ms") or 0.0) for item in results), 2),
        "circuit_state": "closed",
        "false_conflict": int(company_v2_financial_fusion_metrics.snapshot().get("fusion_false_conflict_suspected_total", 0)),
        "cross_report_leakage": int(company_v2_financial_fusion_metrics.snapshot().get("fusion_cross_report_leakage_total", 0)),
        "missing_citation": int(company_v2_financial_fusion_metrics.snapshot().get("fusion_missing_citation_total", 0)),
        "incomplete_source_trace": int(company_v2_financial_fusion_metrics.snapshot().get("fusion_incomplete_source_trace_total", 0)),
    }
    payload = {
        "step": step,
        "symbols": symbols,
        "summary": summary,
        "results": results,
        "checkpoint_path": str(checkpoint_path),
    }
    _write_json(STAGE2_JSON, payload)
    _write_md(STAGE2_MD, payload)
    _write_json(STAGE2_MULTI_JSON, payload)
    return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 2 manual preparation for Company V2 financial fusion")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--step", required=True, choices=["download", "parse", "index"])
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--per-symbol-timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--out-json", default=str(STAGE2_JSON))
    parser.add_argument("--out-md", default=str(STAGE2_MD))
    parser.add_argument("--checkpoint", default=str(CHECKPOINT_PATH))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]
    payload = asyncio.run(run_stage2_prepare(args.step, symbols, args.per_symbol_timeout, Path(args.checkpoint), resume=bool(args.resume)))
    if args.out_json:
        _write_json(Path(args.out_json), payload)
    if args.out_md:
        _write_md(Path(args.out_md), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
