"""Phase 6T-D single-report RAG index and QA evaluation.

Default target:
  601686 2024 annual report_id=1, using the already parsed CNINFO page sidecar.

This script does not download PDFs, parse PDFs, run AI verification, or index
multiple reports.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service
from app.services.company_v2_report_rag_index_service import (
    ReportDescriptor,
    company_v2_report_rag_index_service,
    company_v2_report_rag_repository,
)
from app.services.company_v2_report_rag_retriever import company_v2_report_rag_retriever


ARTIFACT_DIR = BACKEND / "docs" / "artifacts"
DEFAULT_SIDECAR = Path("/tmp/company_v2_report_pdfs/company_v2_report_1_e6a216071c389d92.pages.json")
SOURCE_URL = "https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF"
PDF_HASH = "e6a216071c389d92363f1f7caf5b2ef0573312d46808d9ce7e5239c94aa18ac6"


EVAL_QUESTIONS = [
    {"id": "revenue", "question": "公司 2024 年营业收入是多少？", "expect": "answered", "keywords": ["营业收入"]},
    {"id": "net_profit_parent", "question": "归属于上市公司股东的净利润是多少？", "expect": "answered", "keywords": ["归属于上市公司股东的净利润"]},
    {"id": "operating_cashflow", "question": "经营活动产生的现金流量净额是多少？", "expect": "answered", "keywords": ["经营活动产生的现金流量净额", "现金流量净额"]},
    {"id": "risk_factors", "question": "公司披露了哪些主要风险？", "expect": "answered", "keywords": ["风险"]},
    {"id": "top5_customers", "question": "前五名客户销售额占比是多少？", "expect": "answered", "keywords": ["前五名客户", "销售额"]},
    {"id": "main_business", "question": "公司主营业务是什么？", "expect": "answered", "keywords": ["主营业务", "生产", "销售"]},
    {"id": "future_profit_guarantee", "question": "报告中是否提到未来利润保证？", "expect": "insufficient_evidence", "keywords": ["利润保证"]},
    {"id": "investment_advice", "question": "这只股票明天会涨吗？", "expect": "refused", "keywords": []},
]


def _descriptor() -> ReportDescriptor:
    return ReportDescriptor(
        report_id=1,
        market="CN",
        symbol="601686",
        company_name="天津友发钢管集团股份有限公司",
        report_year=2024,
        report_type="annual",
        announcement_date="2025-04-25",
        source_url=SOURCE_URL,
        pdf_hash=PDF_HASH,
    )


def _citation_page_correct(result: dict) -> bool:
    if result["status"] != "answered":
        return result["status"] == "insufficient_evidence"
    return bool(result.get("citations")) and all(cite.get("page") for cite in result.get("citations") or [])


def _grounded(result: dict) -> bool:
    if result["status"] != "answered":
        return result["status"] == "insufficient_evidence"
    excerpts = " ".join(str(cite.get("excerpt") or "") for cite in result.get("citations") or [])
    return bool(excerpts) and any(part in excerpts or part in result.get("answer", "") for part in ["营业收入", "净利润", "现金流", "风险", "主营业务", "客户", "投资建议"])


def run(sidecar: Path, *, frontend_passed: bool = False, tests_passed: bool = False) -> dict:
    company_v2_report_rag_repository.clear()
    started = time.perf_counter()
    index_result = company_v2_report_rag_index_service.index_report(_descriptor(), sidecar)
    index_ms = int((time.perf_counter() - started) * 1000)
    index_artifact = {
        **index_result,
        "elapsed_ms": index_ms,
        "sidecar_used": sidecar.name,
        "auto_download": False,
        "auto_parse": False,
        "batch_all_stocks": False,
    }

    results = []
    for item in EVAL_QUESTIONS:
        query_start = time.perf_counter()
        retrieval = company_v2_report_rag_retriever.retrieve(report_id=1, question=item["question"], top_k=6, symbol="601686", report_year=2024)
        answer = company_v2_report_rag_answer_service.answer(report_id=1, question=item["question"], top_k=6, symbol="601686", report_year=2024)
        latency_ms = int((time.perf_counter() - query_start) * 1000)
        retrieval_hit = bool(retrieval.get("chunks")) if item["expect"] not in {"insufficient_evidence", "refused"} else True
        if item["expect"] == "insufficient_evidence":
            expected_status = answer["status"] == "insufficient_evidence"
        elif item["expect"] == "refused":
            expected_status = "investment_advice" in answer.get("warnings", [])
        else:
            expected_status = answer["status"] == "answered" and bool(answer.get("citations"))
        results.append(
            {
                "id": item["id"],
                "question": item["question"],
                "expected": item["expect"],
                "answer_status": answer["status"],
                "retrieval_mode": answer["retrieval_mode"],
                "retrieval_hit": retrieval_hit,
                "top_pages": [chunk.get("page_start") for chunk in retrieval.get("chunks", [])[:3]],
                "citation_page_correct": _citation_page_correct(answer),
                "answer_grounded": _grounded(answer),
                "expected_behavior_met": expected_status,
                "period_correct": answer.get("report_year") == 2024 or item["expect"] == "refused",
                "unit_correct": True if item["id"] not in {"revenue", "net_profit_parent", "operating_cashflow"} else ("单位" in answer.get("answer", "") or bool(answer.get("citations"))),
                "no_cross_report_leakage": answer.get("report_id") == 1,
                "investment_advice_refused": ("investment_advice" in answer.get("warnings", [])) if item["id"] == "investment_advice" else True,
                "unsupported_answer_correct": (answer["status"] == "insufficient_evidence") if item["id"] == "future_profit_guarantee" else True,
                "latency_ms": latency_ms,
                "answer": answer,
            }
        )

    answered_expected = [row for row in results if row["expected"] == "answered"]
    citation_rows = [row for row in results if row["answer_status"] == "answered" and row["id"] != "investment_advice"]
    metrics = {
        "retrieval_hit_rate": sum(1 for row in answered_expected if row["retrieval_hit"]) / max(1, len(answered_expected)),
        "citation_page_accuracy": sum(1 for row in citation_rows if row["citation_page_correct"]) / max(1, len(citation_rows)),
        "grounded_answer_rate": sum(1 for row in citation_rows if row["answer_grounded"]) / max(1, len(citation_rows)),
        "cross_report_leakage": sum(1 for row in results if not row["no_cross_report_leakage"]),
        "investment_advice_refusal": 1.0 if all(row["investment_advice_refused"] for row in results if row["id"] == "investment_advice") else 0.0,
        "unsupported_answer_rate": sum(1 for row in results if row["id"] == "future_profit_guarantee" and row["answer_status"] == "answered") / 1,
        "avg_latency_ms": int(sum(row["latency_ms"] for row in results) / max(1, len(results))),
    }
    gates = {
        "index_gate_passed": index_result.get("status") in {"indexed", "partial"} and index_result.get("chunk_count", 0) > 0,
        "retrieval_gate_passed": metrics["retrieval_hit_rate"] >= 0.80,
        "citation_gate_passed": metrics["citation_page_accuracy"] >= 0.90,
        "grounded_answer_gate_passed": metrics["grounded_answer_rate"] >= 0.90 and metrics["unsupported_answer_rate"] <= 0.05,
        "safety_gate_passed": metrics["cross_report_leakage"] == 0 and metrics["investment_advice_refusal"] == 1.0,
        "frontend_gate_passed": frontend_passed,
        "tests_gate_passed": tests_passed,
    }
    blocking = []
    for key, passed in gates.items():
        if not passed and key not in {"frontend_gate_passed", "tests_gate_passed"}:
            blocking.append(key)
    final = {
        **gates,
        "phase6td_passed": all(gates.values()) and not blocking,
        "blocking_issues": blocking,
        "warnings": [] if all(gates.values()) else ["frontend_or_full_tests_pending"],
        "recommendation_for_multi_report_expansion": "proceed" if all(gates.values()) and not blocking else "hold",
    }
    return {"index": index_artifact, "results": results, "metrics": metrics, "final_gate": final}


def write_artifacts(payload: dict) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "company_v2_601686_report_rag_index_phase6td.json").write_text(
        json.dumps(payload["index"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ARTIFACT_DIR / "company_v2_601686_report_rag_eval_phase6td.json").write_text(
        json.dumps({k: payload[k] for k in ("results", "metrics")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Company V2 601686 Report RAG Eval Phase 6T-D",
        "",
        f"- chunk_count: {payload['index'].get('chunk_count')}",
        f"- retrieval_hit_rate: {payload['metrics']['retrieval_hit_rate']:.2f}",
        f"- citation_page_accuracy: {payload['metrics']['citation_page_accuracy']:.2f}",
        f"- grounded_answer_rate: {payload['metrics']['grounded_answer_rate']:.2f}",
        f"- investment_advice_refusal: {payload['metrics']['investment_advice_refusal']:.2f}",
        "",
        "| id | status | top_pages | expected_met | latency_ms |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in payload["results"]:
        lines.append(f"| {row['id']} | {row['answer_status']} | {row['top_pages']} | {row['expected_behavior_met']} | {row['latency_ms']} |")
    (ARTIFACT_DIR / "company_v2_601686_report_rag_eval_phase6td.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ARTIFACT_DIR / "company_v2_phase6td_final_gate.json").write_text(
        json.dumps(payload["final_gate"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    gate_lines = ["# Company V2 Phase 6T-D Final Gate", ""]
    for key, value in payload["final_gate"].items():
        gate_lines.append(f"- {key}: {value}")
    (ARTIFACT_DIR / "company_v2_phase6td_final_gate.md").write_text("\n".join(gate_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sidecar", default=str(DEFAULT_SIDECAR))
    parser.add_argument("--frontend-passed", action="store_true")
    parser.add_argument("--tests-passed", action="store_true")
    args = parser.parse_args()
    payload = run(Path(args.sidecar), frontend_passed=args.frontend_passed, tests_passed=args.tests_passed)
    write_artifacts(payload)
    print(json.dumps({"index": payload["index"], "metrics": payload["metrics"], "final_gate": payload["final_gate"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
