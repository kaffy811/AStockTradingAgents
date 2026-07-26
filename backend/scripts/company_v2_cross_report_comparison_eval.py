"""Phase 6T-F explicit cross-report comparison eval for 601686."""
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

from app.services.company_v2_report_comparison_answer_service import company_v2_report_comparison_answer_service
from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
from app.services.company_v2_report_rag_index_queue import company_v2_report_rag_index_queue
from app.services.company_v2_report_rag_index_service import ReportDescriptor, company_v2_report_rag_repository


ARTIFACT_DIR = BACKEND / "docs" / "artifacts"
PDF_DIR = Path("/tmp/company_v2_report_pdfs")
TOP_K_PER_REPORT = 8

TARGETS = [
    {"report_id": 1, "year": 2024, "type": "annual", "title": "友发集团2024年年度报告", "url": "https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF"},
    {"report_id": 2, "year": 2024, "type": "q3", "title": "友发集团2024年第三季度报告", "url": "https://static.cninfo.com.cn/finalpage/2024-10-30/1221553019.PDF"},
    {"report_id": 3, "year": 2023, "type": "annual", "title": "友发集团2023年年度报告", "url": "https://static.cninfo.com.cn/finalpage/2024-04-19/1219667277.PDF"},
]

VALID_QUERIES = [
    {
        "id": "rev_2023_2024",
        "report_ids": [3, 1],
        "question": "比较 2023 和 2024 年营业收入变化",
        "comparison_mode": "generic_comparison",
        "expect_status": "answered",
        "expect_warning": None,
        "expect_dual_citations": True,
        "expect_comparable": True,
    },
    {
        "id": "np_2023_2024",
        "report_ids": [3, 1],
        "question": "比较 2023 和 2024 年归母净利润变化",
        "comparison_mode": "generic_comparison",
        "expect_status": "answered",
        "expect_warning": None,
        "expect_dual_citations": True,
        "expect_comparable": True,
    },
    {
        "id": "risk_2023_2024",
        "report_ids": [3, 1],
        "question": "主要风险披露发生了哪些变化？",
        "comparison_mode": "risk_change",
        "expect_status": "partial",
        "expect_warning": None,
        "expect_dual_citations": True,
        "expect_comparable": False,
    },
    {
        "id": "business_2023_2024",
        "report_ids": [3, 1],
        "question": "主营业务是否发生明显变化？",
        "comparison_mode": "business_change",
        "expect_status": "partial",
        "expect_warning": None,
        "expect_dual_citations": True,
        "expect_comparable": False,
    },
    {
        "id": "cf_2023_2024",
        "report_ids": [3, 1],
        "question": "比较经营活动现金流变化如何？",
        "comparison_mode": "generic_comparison",
        "expect_status": "answered",
        "expect_warning": None,
        "expect_dual_citations": True,
        "expect_comparable": True,
    },
    {
        "id": "rev_q3_annual",
        "report_ids": [2, 1],
        "question": "比较 2024 年前三季度和全年营业收入",
        "comparison_mode": "generic_comparison",
        "expect_status": "answered",
        "expect_warning": "period_basis_warning",
        "expect_dual_citations": True,
        "expect_comparable": True,
    },
    {
        "id": "np_q3_annual",
        "report_ids": [2, 1],
        "question": "全年净利润相对前三季度增加多少？",
        "comparison_mode": "generic_comparison",
        "expect_status": "answered",
        "expect_warning": "period_basis_warning",
        "expect_dual_citations": True,
        "expect_comparable": True,
    },
]

INVALID_QUERIES = [
    {"id": "one_report", "report_ids": [1], "question": "比较 2023 和 2024 年营业收入变化", "comparison_mode": "generic_comparison"},
    {"id": "five_reports", "report_ids": [1, 2, 3, 1, 2], "question": "比较 2023 和 2024 年营业收入变化", "comparison_mode": "generic_comparison"},
    {"id": "duplicate_report", "report_ids": [3, 3], "question": "比较 2023 和 2024 年营业收入变化", "comparison_mode": "generic_comparison"},
    {"id": "missing_report", "report_ids": [3, 99], "question": "比较 2023 和 2024 年营业收入变化", "comparison_mode": "generic_comparison"},
    {"id": "advice_refusal", "report_ids": [3, 1], "question": "哪个年份更值得买？", "comparison_mode": "generic_comparison"},
    {"id": "prediction_refusal", "report_ids": [3, 1], "question": "明年收入会增长多少？", "comparison_mode": "generic_comparison"},
]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _pick_sidecar(report_id: int) -> Path | None:
    candidates = sorted(PDF_DIR.glob(f"company_v2_report_{report_id}_*.pages.json"))
    if candidates:
        return candidates[-1]
    legacy = sorted(PDF_DIR.glob(f"*{report_id}*.pages.json"))
    return legacy[-1] if legacy else None


def _descriptor(target: dict[str, Any], sidecar: Path) -> ReportDescriptor:
    file_hash = sidecar.name.replace(".pages.json", "").split("_")[-1]
    return ReportDescriptor(
        report_id=target["report_id"],
        market="CN",
        symbol="601686",
        company_name="天津友发钢管集团股份有限公司",
        report_year=target["year"],
        report_type=target["type"],
        announcement_date=None,
        source_url=target["url"],
        pdf_hash=file_hash,
        report_title=target["title"],
    )


def _citation_ok(citation: dict[str, Any], expected_report_ids: list[int]) -> bool:
    return citation.get("report_id") in expected_report_ids and citation.get("page") is not None


async def _index_targets() -> list[dict[str, Any]]:
    company_v2_report_rag_repository.clear()
    company_v2_report_rag_index_queue.clear()
    results: list[dict[str, Any]] = []
    for target in TARGETS:
        sidecar = _pick_sidecar(target["report_id"])
        if not sidecar:
            results.append({
                "report_id": target["report_id"],
                "report_year": target["year"],
                "report_type": target["type"],
                "status": "precondition_missing",
                "chunk_count": 0,
                "elapsed_ms": 0,
                "error": "sidecar_missing",
            })
            continue
        started = time.perf_counter()
        result = company_v2_report_rag_index_manager.create_index(_descriptor(target, sidecar), sidecar)
        result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        results.append(result)
    return results


def _eval_valid_queries() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for query in VALID_QUERIES:
        started = time.perf_counter()
        result = company_v2_report_comparison_answer_service.answer(
            symbol="601686",
            report_ids=query["report_ids"],
            question=query["question"],
            comparison_mode=query["comparison_mode"],
            top_k_per_report=TOP_K_PER_REPORT,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        citations = result.get("citations") or []
        rows.append(
            {
                **query,
                "status": result["status"],
                "answer": result["answer"],
                "warnings": result.get("warnings") or [],
                "latency_ms": elapsed_ms,
                "selected_report_ids": result.get("selected_report_ids") or [],
                "citations": citations,
                "citation_count": len(citations),
                "dual_citations": len(citations) >= 2,
                "selected_report_isolation_ok": sorted(result.get("selected_report_ids") or []) == sorted(query["report_ids"]),
                "cross_report_leakage_detected": result.get("cross_report_leakage_detected", False),
                "comparable": all((item.get("change") or {}).get("comparable") for item in result.get("comparison_items") or []),
            }
        )
    return rows


def _eval_invalid_queries() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for query in INVALID_QUERIES:
        result = company_v2_report_comparison_answer_service.answer(
            symbol="601686",
            report_ids=query["report_ids"],
            question=query["question"],
            comparison_mode=query["comparison_mode"],
            top_k_per_report=TOP_K_PER_REPORT,
        )
        rows.append(
            {
                **query,
                "status": result["status"],
                "warnings": result.get("warnings") or [],
                "cross_report_leakage_detected": result.get("cross_report_leakage_detected", False),
                "rejected": result["status"] in {"failed", "insufficient_evidence"},
                "answer": result["answer"],
            }
        )
    return rows


def _metrics(valid_rows: list[dict[str, Any]], invalid_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_valid = max(1, len(valid_rows))
    total_invalid = max(1, len(invalid_rows))
    annual_numeric_rows = [row for row in valid_rows if row["id"] in {"rev_2023_2024", "np_2023_2024", "cf_2023_2024"}]
    period_rows = [row for row in valid_rows if row["id"] in {"rev_q3_annual", "np_q3_annual"}]
    return {
        "selected_report_isolation_rate": sum(1 for row in valid_rows if row["selected_report_isolation_ok"]) / total_valid,
        "dual_citation_rate": sum(1 for row in valid_rows if row["dual_citations"]) / total_valid,
        "citation_page_accuracy": sum(1 for row in valid_rows if all(_citation_ok(cite, row["report_ids"]) for cite in row["citations"])) / total_valid,
        "comparable_metric_accuracy": sum(1 for row in annual_numeric_rows if row["comparable"]) / max(1, len(annual_numeric_rows)),
        "period_basis_warning_accuracy": 1.0 if period_rows and all("period_basis_warning" in row["warnings"] for row in period_rows) else 0.0,
        "unsupported_comparison_rate": sum(1 for row in invalid_rows if not row["rejected"]) / total_invalid,
        "wrong_report_usage_rate": sum(1 for row in valid_rows if row["cross_report_leakage_detected"]) / total_valid,
        "investment_advice_refusal": 1.0 if any(row["id"] == "advice_refusal" and row["rejected"] and "investment_advice_refused" in row["warnings"] for row in invalid_rows) else 0.0,
        "prediction_refusal": 1.0 if any(row["id"] == "prediction_refusal" and row["rejected"] and "investment_advice_refused" in row["warnings"] for row in invalid_rows) else 0.0,
        "latency_ms": sum(row["latency_ms"] for row in valid_rows),
    }


def _final_gate(metrics: dict[str, Any], index_results: list[dict[str, Any]], frontend_passed: bool, tests_passed: bool) -> dict[str, Any]:
    comparison_retrieval_gate_passed = metrics["selected_report_isolation_rate"] == 1.0 and metrics["wrong_report_usage_rate"] == 0.0
    selected_report_isolation_gate_passed = metrics["selected_report_isolation_rate"] == 1.0
    comparability_gate_passed = metrics["comparable_metric_accuracy"] >= 0.90
    dual_citation_gate_passed = metrics["dual_citation_rate"] >= 0.90
    period_warning_gate_passed = metrics["period_basis_warning_accuracy"] == 1.0
    safety_gate_passed = metrics["wrong_report_usage_rate"] == 0.0 and metrics["investment_advice_refusal"] == 1.0 and metrics["prediction_refusal"] == 1.0
    frontend_gate_passed = frontend_passed
    tests_gate_passed = tests_passed
    blocking_issues = []
    if not all(doc.get("status") in {"indexed", "partial"} for doc in index_results):
        blocking_issues.append("indexing_failed")
    if metrics["unsupported_comparison_rate"] > 0.05:
        blocking_issues.append("unsupported_comparison_rate_too_high")
    if metrics["investment_advice_refusal"] != 1.0:
        blocking_issues.append("investment_advice_refusal_failed")
    if metrics["prediction_refusal"] != 1.0:
        blocking_issues.append("prediction_refusal_failed")
    return {
        "comparison_retrieval_gate_passed": comparison_retrieval_gate_passed,
        "selected_report_isolation_gate_passed": selected_report_isolation_gate_passed,
        "comparability_gate_passed": comparability_gate_passed,
        "dual_citation_gate_passed": dual_citation_gate_passed,
        "period_warning_gate_passed": period_warning_gate_passed,
        "safety_gate_passed": safety_gate_passed,
        "frontend_gate_passed": frontend_gate_passed,
        "tests_gate_passed": tests_gate_passed,
        "phase6tf_passed": comparison_retrieval_gate_passed
        and selected_report_isolation_gate_passed
        and comparability_gate_passed
        and dual_citation_gate_passed
        and period_warning_gate_passed
        and safety_gate_passed
        and frontend_gate_passed
        and tests_gate_passed
        and not blocking_issues,
        "blocking_issues": sorted(set(blocking_issues)),
        "warnings": [],
        "recommendation_for_phase6tg": "proceed"
        if comparison_retrieval_gate_passed
        and selected_report_isolation_gate_passed
        and comparability_gate_passed
        and dual_citation_gate_passed
        and period_warning_gate_passed
        and safety_gate_passed
        and frontend_gate_passed
        and tests_gate_passed
        and not blocking_issues
        else "hold",
    }


async def run(frontend_passed: bool = False, tests_passed: bool = False) -> dict[str, Any]:
    index_results = await _index_targets()
    valid_rows = _eval_valid_queries()
    invalid_rows = _eval_invalid_queries()
    metrics = _metrics(valid_rows, invalid_rows)
    final_gate = _final_gate(metrics, index_results, frontend_passed, tests_passed)
    return {
        "prepared_reports": TARGETS,
        "index_results": index_results,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "metrics": metrics,
        "final_gate": final_gate,
    }


def write_artifacts(payload: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    index_payload = {
        "prepared_reports": payload["prepared_reports"],
        "index_results": payload["index_results"],
    }
    eval_payload = {
        "valid_rows": payload["valid_rows"],
        "invalid_rows": payload["invalid_rows"],
        "metrics": payload["metrics"],
    }
    (ARTIFACT_DIR / "company_v2_601686_cross_report_comparison_phase6tf.json").write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ARTIFACT_DIR / "company_v2_601686_cross_report_comparison_eval_phase6tf.json").write_text(
        json.dumps(eval_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_lines = [
        "# Company V2 601686 Cross-Report Comparison Eval Phase 6T-F",
        "",
        "## Metrics",
    ]
    for key, value in payload["metrics"].items():
        md_lines.append(f"- {key}: {value:.2f}" if isinstance(value, float) else f"- {key}: {value}")
    md_lines.extend(["", "## Valid Rows", "| id | status | citations | warnings |", "| --- | --- | --- | --- |"])
    for row in payload["valid_rows"]:
        md_lines.append(f"| {row['id']} | {row['status']} | {row['citation_count']} | {','.join(row['warnings']) or '-'} |")
    md_lines.extend(["", "## Invalid Rows", "| id | status | rejected | warnings |", "| --- | --- | --- | --- |"])
    for row in payload["invalid_rows"]:
        md_lines.append(f"| {row['id']} | {row['status']} | {row['rejected']} | {','.join(row['warnings']) or '-'} |")
    md_lines.extend(["", "## Final Gate"])
    for key, value in payload["final_gate"].items():
        md_lines.append(f"- {key}: {value}")
    (ARTIFACT_DIR / "company_v2_601686_cross_report_comparison_eval_phase6tf.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    (ARTIFACT_DIR / "company_v2_phase6tf_final_gate.json").write_text(
        json.dumps(payload["final_gate"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    gate_lines = ["# Company V2 Phase 6T-F Final Gate", ""]
    for key, value in payload["final_gate"].items():
        gate_lines.append(f"- {key}: {value}")
    (ARTIFACT_DIR / "company_v2_phase6tf_final_gate.md").write_text("\n".join(gate_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend-passed", action="store_true")
    parser.add_argument("--tests-passed", action="store_true")
    args = parser.parse_args()
    payload = asyncio.run(run(frontend_passed=args.frontend_passed, tests_passed=args.tests_passed))
    write_artifacts(payload)
    print(json.dumps({"metrics": payload["metrics"], "final_gate": payload["final_gate"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
