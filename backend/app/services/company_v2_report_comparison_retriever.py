"""Explicit cross-report retriever for Company V2 comparison mode."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.company_v2_report_comparison_evidence_builder import detect_topics, topic_query
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository
from app.services.company_v2_report_rag_retriever import company_v2_report_rag_retriever


@dataclass(slots=True)
class ComparisonReportContext:
    report_id: int
    report_year: int | None
    report_type: str | None
    status: str


class CompanyV2ReportComparisonRetriever:
    def retrieve(
        self,
        *,
        symbol: str,
        report_ids: list[int],
        question: str,
        top_k_per_report: int = 4,
    ) -> dict[str, Any]:
        selected_report_ids = list(dict.fromkeys(int(report_id) for report_id in report_ids))
        per_report_results: list[dict[str, Any]] = []
        unexpected_report_ids: list[int] = []
        warnings: list[str] = []
        topics = detect_topics(question)

        for report_id in selected_report_ids:
            doc = company_v2_report_rag_repository.get_document(report_id)
            if not doc or doc.symbol != symbol:
                unexpected_report_ids.append(report_id)
                continue
            collected: list[dict[str, Any]] = []
            retrieval_modes: list[str] = []
            for topic in topics:
                result = company_v2_report_rag_retriever.retrieve(
                    report_id=report_id,
                    question=topic_query(topic, question, doc.report_year, doc.report_type),
                    top_k=top_k_per_report,
                    symbol=symbol,
                    report_year=doc.report_year,
                )
                if result.get("error_code"):
                    warnings.append(result["error_code"])
                    continue
                retrieval_modes.append(result.get("retrieval_mode") or "hybrid")
                collected.extend(result.get("chunks") or [])
            deduped: list[dict[str, Any]] = []
            seen_chunk_ids: set[int] = set()
            for chunk in collected:
                chunk_id = int(chunk.get("chunk_id") or 0)
                if chunk_id and chunk_id in seen_chunk_ids:
                    continue
                if chunk_id:
                    seen_chunk_ids.add(chunk_id)
                deduped.append(chunk)
            per_report_results.append(
                {
                    "report_id": report_id,
                    "report_year": doc.report_year,
                    "report_type": doc.report_type,
                    "status": doc.status,
                    "chunks": deduped,
                    "retrieval_mode": "hybrid" if "hybrid" in retrieval_modes else (retrieval_modes[0] if retrieval_modes else "keyword"),
                    "selected_report_id": report_id,
                    "retrieved_report_ids": [report_id] if deduped else [],
                    "cross_report_leakage_detected": False,
                }
            )

        leakage = bool(unexpected_report_ids) or any(item["cross_report_leakage_detected"] for item in per_report_results)
        return {
            "selected_report_ids": selected_report_ids,
            "per_report_results": per_report_results,
            "unexpected_report_ids": sorted(set(unexpected_report_ids)),
            "cross_report_leakage_detected": leakage,
            "warnings": warnings,
        }


company_v2_report_comparison_retriever = CompanyV2ReportComparisonRetriever()
