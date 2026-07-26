#!/usr/bin/env python3
"""Phase 6U-D1 demo stock data readiness check.

This script is intentionally allowlist-only. It can discover CNINFO reports,
prepare already discovered reports, fetch annual history, and write sanitized
readiness artifacts for the Phase 6U demo stocks.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.report_document import ReportDocument
from app.services.cninfo_report_discovery_agent import cninfo_report_discovery_agent
from app.services.company_v2_history_service import build_company_history_dashboard
from app.services.company_v2_pdf_text_parser import company_v2_pdf_text_parser
from app.services.company_v2_report_pdf_service import company_v2_report_pdf_service, validate_cninfo_pdf_url
from app.services.company_v2_report_rag_index_service import ReportDescriptor, company_v2_report_rag_index_service
from app.services.report_document_service import report_document_service


ALLOWLIST = {"600519", "300750", "000725", "000001", "601686"}
ARTIFACT_JSON = ROOT / "docs/artifacts/phase6u_demo_data_readiness.json"
ARTIFACT_MD = ROOT / "docs/artifacts/phase6u_demo_data_readiness.md"


def _ts_code(symbol: str) -> str:
    if symbol.startswith(("6", "5", "9")):
        return f"{symbol}.SH"
    if symbol.startswith(("0", "2", "3")):
        return f"{symbol}.SZ"
    if symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    return f"{symbol}.SH"


def _host(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(url).hostname or None


def _sanitize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)[:300]
    text = re.sub(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*\S+", r"\1=[redacted]", text)
    text = re.sub(r"(/[A-Za-z0-9_.@ -]+)+", "[path]", text)
    return text


async def _latest_report(db, symbol: str) -> ReportDocument | None:
    result = await db.execute(
        select(ReportDocument)
        .where(ReportDocument.ts_code == _ts_code(symbol), ReportDocument.report_type == "annual")
        .order_by(
            ReportDocument.report_year.desc().nullslast(),
            ReportDocument.period_end.desc().nullslast(),
            ReportDocument.disclosure_date.desc().nullslast(),
            ReportDocument.id.desc(),
        )
        .limit(1)
    )
    return result.scalars().first()


async def _discover_latest(db, symbol: str, *, force_refresh: bool) -> dict[str, Any]:
    result = await cninfo_report_discovery_agent.discover(
        "CN",
        symbol,
        force_refresh=force_refresh,
        report_types=["annual"],
    )
    persisted: list[dict[str, Any]] = []
    for report in (result.get("reports") or [])[:3]:
        candidate = {
            **report,
            "stock_code": symbol,
            "source": report.get("source") or "cninfo",
        }
        persisted.append(await report_document_service.upsert_discovered_report(candidate, db))
    return {
        "status": "success" if result.get("reports") else "empty",
        "documents_count": result.get("documents_count", 0),
        "persisted": persisted,
        "errors": [_sanitize_text(item) for item in result.get("errors") or []],
    }


def _descriptor(doc: ReportDocument, symbol: str) -> ReportDescriptor:
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


async def _prepare_report(db, doc: ReportDocument, symbol: str) -> dict[str, Any]:
    steps: dict[str, Any] = {}
    if not (doc.download_status in {"downloaded", "exists"} and doc.local_path and Path(doc.local_path).exists()):
        steps["download"] = await company_v2_report_pdf_service.download_report(int(doc.id), db)
    else:
        steps["download"] = {"ok": True, "status": doc.download_status, "report_id": int(doc.id)}

    await db.refresh(doc)
    if not bool(doc.parsed or doc.parse_status in {"parsed", "partial"}):
        steps["parse"] = await company_v2_pdf_text_parser.parse_report(int(doc.id), db)
    else:
        steps["parse"] = {"ok": True, "status": doc.parse_status, "report_id": int(doc.id)}

    await db.refresh(doc)
    rag_status = company_v2_report_rag_index_service.status(int(doc.id))
    if rag_status.get("status") not in {"indexed", "partial"}:
        sidecar = Path(doc.local_path).with_suffix(".pages.json") if doc.local_path else None
        if sidecar and sidecar.exists():
            steps["index"] = await asyncio.to_thread(
                company_v2_report_rag_index_service.index_report,
                _descriptor(doc, symbol),
                sidecar,
            )
        else:
            steps["index"] = {"ok": False, "status": "failed", "error_code": "PARSE_SIDECAR_MISSING"}
    else:
        steps["index"] = {"ok": True, "status": rag_status.get("status"), "report_id": int(doc.id)}
    return steps


async def _history_points(symbol: str, *, force_refresh: bool) -> tuple[int, dict[str, Any]]:
    dashboard = await build_company_history_dashboard(
        "CN",
        symbol,
        period="annual",
        start_year=2020,
        end_year=2025,
        force_refresh=force_refresh,
        include_stock_basic=False,
    )
    points = 0
    for module in (dashboard.get("modules") or {}).values():
        years = {
            row.get("report_year") or str(row.get("period") or "")[:4]
            for row in (module.get("history") or [])
            if row.get("period")
        }
        points = max(points, len({str(year) for year in years if year}))
    return points, {
        "data_success_count": dashboard.get("data_success_count", 0),
        "provider_status": (dashboard.get("performance_summary") or {}).get("status"),
        "reason_code": (dashboard.get("performance_summary") or {}).get("reason_code"),
    }


async def _readiness_for_symbol(symbol: str, args: argparse.Namespace) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        discovery = None
        if args.discover:
            discovery = await _discover_latest(db, symbol, force_refresh=args.force_refresh)

        doc = await _latest_report(db, symbol)
        prepare_steps = None
        if doc and args.prepare:
            prepare_steps = await _prepare_report(db, doc, symbol)
            await db.refresh(doc)

        historical_points, history_diag = (0, {})
        if args.history:
            historical_points, history_diag = await _history_points(symbol, force_refresh=args.force_refresh)

        rag_status = company_v2_report_rag_index_service.status(int(doc.id)) if doc else {}
        rag_chunks = int(rag_status.get("chunk_count") or doc.chunk_count or 0) if doc else 0
        if doc and rag_status.get("status") in {"indexed", "partial"}:
            changed = False
            if doc.rag_status != rag_status.get("status"):
                doc.rag_status = rag_status.get("status")
                changed = True
            if doc.chunk_count != rag_chunks:
                doc.chunk_count = rag_chunks
                changed = True
            if changed:
                await db.commit()

        pdf_url = doc.pdf_url if doc else None
        source_url = doc.source_url if doc else None
        valid_pdf, pdf_reason = validate_cninfo_pdf_url(pdf_url or "")
        parsed = bool(doc and (doc.parsed or doc.parse_status in {"parsed", "partial"}))
        indexed = bool(rag_status.get("status") in {"indexed", "partial"} and rag_chunks > 0)
        chat_report_ready = bool(doc and valid_pdf and parsed and indexed)

        blocking = []
        if historical_points < 3:
            blocking.append("historical_annual_points_lt_3")
        if not doc:
            blocking.append("latest_report_not_found")
        if doc and not valid_pdf:
            blocking.append(f"invalid_pdf_url:{pdf_reason}")
        if doc and not parsed:
            blocking.append("report_not_parsed")
        if doc and not indexed:
            blocking.append("rag_not_indexed")

        return {
            "symbol": symbol,
            "market": "CN",
            "historical_annual_points": historical_points,
            "latest_report_found": bool(doc),
            "report_id": int(doc.id) if doc else None,
            "report_year": int(doc.report_year) if doc and doc.report_year else None,
            "report_type": doc.report_type if doc else None,
            "source_url_host": _host(source_url),
            "pdf_url_host": _host(pdf_url),
            "report_url_valid": valid_pdf,
            "downloaded": bool(doc and doc.download_status in {"downloaded", "exists"}),
            "parsed": parsed,
            "indexed": indexed,
            "rag_chunks": rag_chunks,
            "chat_report_ready": chat_report_ready,
            "blocking_reason": "; ".join(_sanitize_text(item) or "" for item in blocking) or None,
            "history": history_diag,
            "discovery": discovery,
            "prepare_steps": prepare_steps,
        }


def _write_artifacts(payload: dict[str, Any]) -> None:
    ARTIFACT_JSON.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Phase 6U-D1 Demo Data Readiness",
        "",
        f"- gate_passed: `{payload['gate_passed']}`",
        f"- symbols: `{', '.join(payload['symbols'])}`",
        "",
        "| symbol | history points | report | url | parsed | indexed | chunks | chat ready | blocking |",
        "| --- | ---: | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for item in payload["stocks"]:
        lines.append(
            "| {symbol} | {historical_annual_points} | {report_id} | {report_url_valid} | "
            "{parsed} | {indexed} | {rag_chunks} | {chat_report_ready} | {blocking_reason} |".format(
                **{**item, "blocking_reason": item.get("blocking_reason") or ""}
            )
        )
    ARTIFACT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="*", default=sorted(ALLOWLIST))
    parser.add_argument("--discover", action="store_true", help="discover and persist CNINFO reports")
    parser.add_argument("--prepare", action="store_true", help="download/parse/index existing latest reports")
    parser.add_argument("--history", action="store_true", help="fetch annual historical financial data")
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()

    symbols = [str(item).strip() for item in args.symbols if str(item).strip()]
    unexpected = sorted(set(symbols) - ALLOWLIST)
    if unexpected:
        raise SystemExit(f"symbols outside allowlist are not permitted: {unexpected}")
    if not args.discover and not args.prepare and not args.history:
        args.history = True

    stocks = []
    for symbol in symbols:
        stocks.append(await _readiness_for_symbol(symbol, args))

    by_symbol = {item["symbol"]: item for item in stocks}
    gate_stock = by_symbol.get("600519") or {}
    gate_passed = bool(
        gate_stock.get("historical_annual_points", 0) >= 3
        and gate_stock.get("latest_report_found")
        and gate_stock.get("report_url_valid")
        and gate_stock.get("parsed")
        and gate_stock.get("indexed")
        and gate_stock.get("rag_chunks", 0) > 0
        and gate_stock.get("chat_report_ready")
    )
    payload = {
        "phase": "6U-D1",
        "gate_passed": gate_passed,
        "symbols": symbols,
        "stocks": stocks,
        "artifact_policy": "sanitized: no local_path, no secrets, hosts only for URLs",
    }
    _write_artifacts(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if gate_passed else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
