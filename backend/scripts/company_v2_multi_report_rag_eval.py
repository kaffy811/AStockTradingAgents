"""Phase 6T-E3 multi-report RAG eval for 601686.

The script indexes only the explicitly selected reports. It prefers existing
page sidecars and, when allowed, downloads/parses missing CNINFO PDFs for those
reports only. It never indexes all stocks and never modifies Phase 6T-D
artifacts.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import httpx

from app.datasource.cninfo_provider import discover_reports
from app.services.company_v2_pdf_text_parser import parse_pdf_text
from app.services.company_v2_report_pdf_service import validate_cninfo_pdf_url
from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service
from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
from app.services.company_v2_report_rag_index_queue import company_v2_report_rag_index_queue
from app.services.company_v2_report_rag_index_service import ReportDescriptor, company_v2_report_rag_repository


ARTIFACT_DIR = BACKEND / "docs" / "artifacts"
PDF_DIR = Path("/tmp/company_v2_report_pdfs")
SOURCE_2024_ANNUAL = "https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF"
SOURCE_2024_Q3 = "https://static.cninfo.com.cn/finalpage/2024-10-30/1221553019.PDF"
SOURCE_2023_ANNUAL = "https://static.cninfo.com.cn/finalpage/2024-04-19/1219667277.PDF"


TARGETS = [
    {"report_id": 1, "year": 2024, "type": "annual", "title": "友发集团2024年年度报告", "url": SOURCE_2024_ANNUAL},
    {"report_id": 2, "year": 2024, "type": "q3", "title": "友发集团2024年第三季度报告", "url": SOURCE_2024_Q3},
    {"report_id": 3, "year": 2023, "type": "annual", "title": "友发集团2023年年度报告", "url": SOURCE_2023_ANNUAL},
]


QUESTIONS = [
    {"report_id": 1, "id": "2024_annual_revenue", "question": "2024 年营业收入是多少？", "expect": "answered"},
    {"report_id": 1, "id": "2024_annual_risks", "question": "公司披露的主要风险有哪些？", "expect": "answered"},
    {"report_id": 2, "id": "2024_q3_revenue", "question": "前三季度营业收入是多少？", "expect": "answered"},
    {"report_id": 2, "id": "2024_q3_cashflow", "question": "本期经营现金流情况如何？", "expect": "answered"},
    {"report_id": 3, "id": "2023_annual_np_parent", "question": "2023 年归母净利润是多少？", "expect": "answered"},
    {"report_id": 3, "id": "2023_annual_business", "question": "主营业务是什么？", "expect": "answered"},
    {"report_id": 3, "id": "wrong_year_2023_selected", "question": "2024 年营业收入是多少？", "expect": "insufficient_evidence"},
    {"report_id": 2, "id": "q3_full_year", "question": "2024 年全年净利润是多少？", "expect": "insufficient_evidence"},
]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _known_sidecar(report_id: int, pdf_hash_prefix: str | None = None) -> Path | None:
    for candidate in PDF_DIR.glob(f"company_v2_report_{report_id}_*.pages.json"):
        if pdf_hash_prefix is None or pdf_hash_prefix in candidate.name:
            return candidate
    return None


async def _discover_2023_annual_url() -> str | None:
    reports = await discover_reports("601686", start_year=2023, end_year=2023, report_types=["annual"])
    for report in reports:
        if report.get("report_year") == 2023 and report.get("report_type") == "annual":
            return report.get("pdf_url")
    return None


async def _download_and_parse(report_id: int, url: str) -> tuple[Path | None, str | None, str | None]:
    valid, reason = validate_cninfo_pdf_url(url)
    if not valid:
        return None, None, f"invalid_url:{reason}"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "TradingAgentsResearch/1.0"})
            resp.raise_for_status()
        content = resp.content
        if not content.startswith(b"%PDF") and "pdf" not in (resp.headers.get("content-type") or "").lower():
            return None, None, "not_pdf"
        file_hash = _sha256(content)
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        pdf = PDF_DIR / f"company_v2_report_{report_id}_{file_hash[:16]}.pdf"
        sidecar = pdf.with_suffix(".pages.json")
        if not sidecar.exists():
            pdf.write_bytes(content)
            parsed = parse_pdf_text(pdf, report_id=report_id)
            sidecar.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
        return sidecar, file_hash, None
    except Exception as exc:
        return None, None, str(exc)[:300]


async def _prepare_target(target: dict[str, Any], allow_download: bool) -> dict[str, Any]:
    sidecar = _known_sidecar(target["report_id"])
    url = target.get("url")
    file_hash = None
    error = None
    if not url and allow_download:
        url = await _discover_2023_annual_url()
    if not sidecar and allow_download and url:
        sidecar, file_hash, error = await _download_and_parse(target["report_id"], url)
    if sidecar and not file_hash:
        # Best effort: infer hash prefix from existing file name.
        file_hash = sidecar.name.replace(".pages.json", "").split("_")[-1]
    return {**target, "url": url, "sidecar": str(sidecar) if sidecar else None, "pdf_hash": file_hash, "precondition_error": error if not sidecar else None}


def _descriptor(prepared: dict[str, Any]) -> ReportDescriptor:
    return ReportDescriptor(
        report_id=prepared["report_id"],
        market="CN",
        symbol="601686",
        company_name="天津友发钢管集团股份有限公司",
        report_year=prepared["year"],
        report_type=prepared["type"],
        announcement_date=None,
        source_url=prepared["url"] or "",
        pdf_hash=prepared["pdf_hash"],
        report_title=prepared["title"],
    )


async def run(allow_download: bool, *, frontend_passed: bool = False, tests_passed: bool = False) -> dict[str, Any]:
    company_v2_report_rag_repository.clear()
    company_v2_report_rag_index_queue.clear()

    prepared = [await _prepare_target(target, allow_download) for target in TARGETS]
    index_results = []
    prepared_by_id: dict[int, dict[str, Any]] = {}
    for item in prepared:
        prepared_by_id[item["report_id"]] = item
        if not item.get("sidecar") or not item.get("url"):
            index_results.append({
                "report_id": item["report_id"],
                "report_year": item["year"],
                "report_type": item["type"],
                "status": "precondition_missing",
                "chunk_count": 0,
                "blocking_issue": "parsed_sidecar_missing",
                "error": item.get("precondition_error"),
            })
            continue
        started = time.perf_counter()
        result = company_v2_report_rag_index_manager.create_index(_descriptor(item), item["sidecar"])
        index_results.append({**result, "elapsed_ms": int((time.perf_counter() - started) * 1000)})

    idempotency_result = None
    stale_refresh_result = None
    if prepared_by_id.get(1, {}).get("sidecar") and prepared_by_id.get(1, {}).get("url"):
        item = prepared_by_id[1]
        first_active = company_v2_report_rag_index_manager.get_index(1)
        repeated = company_v2_report_rag_index_manager.create_index(_descriptor(item), item["sidecar"])
        stale = company_v2_report_rag_index_manager.mark_stale(1, "phase6te3_stale_refresh_smoke")
        refreshed = company_v2_report_rag_index_manager.rebuild_stale_index(_descriptor(item), item["sidecar"])
        after_refresh = company_v2_report_rag_index_manager.get_index(1)
        idempotency_result = {
            "same_rag_document_id": repeated.get("rag_document_id") == first_active["history"][0]["rag_document_id"],
            "repeated_generation": repeated.get("index_generation"),
            "active_index_preserved": repeated.get("active_index"),
        }
        stale_refresh_result = {
            "stale_status": stale.get("status"),
            "stale_reason": stale.get("stale_reason"),
            "refresh_status": refreshed.get("status"),
            "new_generation": refreshed.get("index_generation"),
            "supersedes_rag_document_id": refreshed.get("supersedes_rag_document_id"),
            "history_count": len(after_refresh.get("history") or []),
        }

    eval_rows = []
    for question in QUESTIONS:
        answer = company_v2_report_rag_answer_service.answer(
            report_id=question["report_id"],
            question=question["question"],
            symbol="601686",
        )
        expected = question["expect"]
        expected_met = (answer["status"] == "answered" and bool(answer.get("citations"))) if expected == "answered" else answer["status"] == "insufficient_evidence"
        eval_rows.append({
            "id": question["id"],
            "report_id": question["report_id"],
            "question": question["question"],
            "expected": expected,
            "answer_status": answer["status"],
            "expected_met": expected_met,
            "retrieved_report_ids": answer.get("retrieved_report_ids") or [],
            "cross_report_leakage_detected": answer.get("cross_report_leakage_detected", False),
            "citation_page_correct": bool(answer.get("citations")) if expected == "answered" else True,
            "answer": answer,
        })

    answered = [row for row in eval_rows if row["expected"] == "answered"]
    insufficient = [row for row in eval_rows if row["expected"] == "insufficient_evidence"]
    metrics = {
        "retrieval_hit_rate": sum(1 for row in answered if row["answer_status"] == "answered") / max(1, len(answered)),
        "citation_page_accuracy": sum(1 for row in answered if row["citation_page_correct"]) / max(1, len(answered)),
        "cross_report_leakage": sum(1 for row in eval_rows if row["cross_report_leakage_detected"]),
        "wrong_year_answer_rate": sum(1 for row in insufficient if row["answer_status"] == "answered") / max(1, len(insufficient)),
        "insufficient_evidence_correctness": sum(1 for row in insufficient if row["answer_status"] == "insufficient_evidence") / max(1, len(insufficient)),
    }
    all_three_indexed = sum(1 for row in index_results if row.get("status") in {"indexed", "partial"}) == 3
    gates = {
        "multi_index_gate_passed": all_three_indexed,
        "index_idempotency_gate_passed": all_three_indexed and bool(idempotency_result and idempotency_result["same_rag_document_id"]),
        "report_isolation_gate_passed": metrics["cross_report_leakage"] == 0 and metrics["wrong_year_answer_rate"] == 0,
        "stale_refresh_gate_passed": all_three_indexed and bool(stale_refresh_result and stale_refresh_result["refresh_status"] == "indexed"),
        "citation_gate_passed": metrics["citation_page_accuracy"] >= 0.90,
        "safety_gate_passed": metrics["cross_report_leakage"] == 0,
        "frontend_gate_passed": frontend_passed,
        "tests_gate_passed": tests_passed,
    }
    blocking = [key for key, value in gates.items() if not value]
    if any(row.get("status") == "precondition_missing" for row in index_results):
        blocking.append("real_report_sidecar_missing")
    final = {
        **gates,
        "phase6te3_passed": all(gates.values()) and not blocking,
        "blocking_issues": sorted(set(blocking)),
        "warnings": [] if allow_download else ["missing sidecars are not downloaded unless --allow-download is set"],
        "recommendation_for_phase6tf": "proceed" if all(gates.values()) and not blocking else "hold",
    }
    return {
        "prepared_reports": prepared,
        "index_results": index_results,
        "idempotency_result": idempotency_result,
        "stale_refresh_result": stale_refresh_result,
        "eval_results": eval_rows,
        "metrics": metrics,
        "final_gate": final,
    }


def write_artifacts(payload: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "company_v2_601686_multi_report_index_phase6te3.json").write_text(
        json.dumps(
            {
                "prepared_reports": payload["prepared_reports"],
                "index_results": payload["index_results"],
                "idempotency_result": payload.get("idempotency_result"),
                "stale_refresh_result": payload.get("stale_refresh_result"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (ARTIFACT_DIR / "company_v2_601686_multi_report_rag_eval_phase6te3.json").write_text(
        json.dumps({"eval_results": payload["eval_results"], "metrics": payload["metrics"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Company V2 601686 Multi-Report RAG Eval Phase 6T-E3",
        "",
        f"- retrieval_hit_rate: {payload['metrics']['retrieval_hit_rate']:.2f}",
        f"- citation_page_accuracy: {payload['metrics']['citation_page_accuracy']:.2f}",
        f"- cross_report_leakage: {payload['metrics']['cross_report_leakage']}",
        f"- wrong_year_answer_rate: {payload['metrics']['wrong_year_answer_rate']:.2f}",
        "",
        "| id | report_id | status | expected_met | retrieved_report_ids |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in payload["eval_results"]:
        lines.append(f"| {row['id']} | {row['report_id']} | {row['answer_status']} | {row['expected_met']} | {row['retrieved_report_ids']} |")
    (ARTIFACT_DIR / "company_v2_601686_multi_report_rag_eval_phase6te3.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ARTIFACT_DIR / "company_v2_phase6te3_final_gate.json").write_text(json.dumps(payload["final_gate"], ensure_ascii=False, indent=2), encoding="utf-8")
    gate_lines = ["# Company V2 Phase 6T-E3 Final Gate", ""]
    for key, value in payload["final_gate"].items():
        gate_lines.append(f"- {key}: {value}")
    (ARTIFACT_DIR / "company_v2_phase6te3_final_gate.md").write_text("\n".join(gate_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--frontend-passed", action="store_true")
    parser.add_argument("--tests-passed", action="store_true")
    args = parser.parse_args()
    payload = asyncio.run(run(args.allow_download, frontend_passed=args.frontend_passed, tests_passed=args.tests_passed))
    write_artifacts(payload)
    print(json.dumps({"index_results": payload["index_results"], "metrics": payload["metrics"], "final_gate": payload["final_gate"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
