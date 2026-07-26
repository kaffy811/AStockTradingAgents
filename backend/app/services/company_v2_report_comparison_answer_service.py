"""Deterministic answer service for explicit Company V2 cross-report comparison."""
from __future__ import annotations

import re
import time
from typing import Any

from app.services.company_v2_report_comparison_calculator import calculate_comparison_change
from app.services.company_v2_report_comparison_evidence_builder import (
    build_comparison_evidence_matrix,
    infer_comparison_mode,
)
from app.services.company_v2_report_comparison_prompt_builder import build_comparison_prompt
from app.services.company_v2_report_comparison_retriever import company_v2_report_comparison_retriever
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository


MAX_QUESTION_CHARS = 500


def _has_refusal_trigger(question: str) -> str | None:
    if re.search(r"明天.*(涨|跌)|明年|后年|未来.*增长|预测|目标价|买不买|值得买|投资建议|推荐", question):
        return "investment_advice_refused"
    return None


def _citation_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_id": row.get("report_id"),
        "report_year": row.get("report_year"),
        "report_type": row.get("report_type"),
        "page": row.get("evidence_pages")[0] if row.get("evidence_pages") else None,
        "excerpt": row.get("excerpt") or "",
    }


def _selected_reports_payload(selected_report_ids: list[int]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for report_id in selected_report_ids:
        doc = company_v2_report_rag_repository.get_document(report_id)
        if not doc:
            continue
        payload.append(
            {
                "report_id": doc.report_id,
                "report_year": doc.report_year,
                "report_type": doc.report_type,
                "report_title": doc.report_title,
                "chunk_count": doc.chunk_count,
                "indexed_at": doc.indexed_at,
                "status": doc.status,
                "active_index": doc.active_index,
            }
        )
    return payload


class CompanyV2ReportComparisonAnswerService:
    def answer(
        self,
        *,
        symbol: str,
        report_ids: list[int],
        question: str,
        comparison_mode: str = "generic_comparison",
        top_k_per_report: int = 4,
        answer_style: str = "concise",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        question = (question or "").strip()
        raw_report_ids = [int(report_id) for report_id in report_ids]
        if not (2 <= len(raw_report_ids) <= 4):
            return self._payload(
                status="failed",
                symbol=symbol,
                selected_report_ids=list(dict.fromkeys(raw_report_ids)),
                question=question,
                answer="比较模式必须显式选择 2 到 4 份报告。",
                comparison_items=[],
                citations=[],
                warnings=["REPORT_COUNT_OUT_OF_RANGE"],
                started=started,
            )
        unique_report_ids = list(dict.fromkeys(raw_report_ids))
        if len(unique_report_ids) != len(raw_report_ids):
            return self._payload(
                status="failed",
                symbol=symbol,
                selected_report_ids=unique_report_ids,
                question=question,
                answer="比较模式不允许重复的 report_id。",
                comparison_items=[],
                citations=[],
                warnings=["DUPLICATE_REPORT_ID"],
                started=started,
            )

        if len(question) > MAX_QUESTION_CHARS:
            return self._payload(
                status="failed",
                symbol=symbol,
                selected_report_ids=unique_report_ids,
                question=question[:MAX_QUESTION_CHARS],
                answer="问题过长，已拒绝处理。",
                comparison_items=[],
                citations=[],
                warnings=["QUESTION_TOO_LONG"],
                started=started,
            )

        refusal = _has_refusal_trigger(question)
        if refusal:
            return self._payload(
                status="insufficient_evidence",
                symbol=symbol,
                selected_report_ids=unique_report_ids,
                question=question,
                answer="该问题属于投资建议或未来预测，比较模式只回答选定报告中的原文事实，不提供买卖建议或预测。",
                comparison_items=[],
                citations=[],
                warnings=[refusal],
                started=started,
            )

        retrieval = company_v2_report_comparison_retriever.retrieve(
            symbol=symbol,
            report_ids=unique_report_ids,
            question=question,
            top_k_per_report=top_k_per_report,
        )
        if retrieval["unexpected_report_ids"]:
            return self._payload(
                status="failed",
                symbol=symbol,
                selected_report_ids=unique_report_ids,
                question=question,
                answer="检索结果包含未选报告，已中止比较。",
                comparison_items=[],
                citations=[],
                warnings=["cross_report_leakage_detected"],
                started=started,
            )

        evidence_matrix = build_comparison_evidence_matrix(
            selected_report_ids=unique_report_ids,
            per_report_results=retrieval["per_report_results"],
            question=question,
            comparison_mode=comparison_mode or infer_comparison_mode(question),
        )

        comparison_items: list[dict[str, Any]] = []
        citations: list[dict[str, Any]] = []
        warnings = list(retrieval.get("warnings") or []) + list(evidence_matrix.get("comparison_warnings") or [])
        for item in evidence_matrix["topics"]:
            change = calculate_comparison_change(item)
            comparison_items.append({**item, "change": change})
            for row in item.get("reports", []):
                if row.get("evidence_pages"):
                    citations.append(_citation_from_row(row))
            warnings.extend(change.get("warnings") or [])

        answer_parts: list[str] = []
        for item in comparison_items:
            change = item["change"]
            rows = item["reports"]
            report_bits = []
            for row in rows:
                page = row["evidence_pages"][0] if row.get("evidence_pages") else "?"
                report_bits.append(
                    f"{row.get('report_year')}年{row.get('report_type')}（第{page}页）"
                )
            if change.get("computed") and change.get("comparable"):
                value_part = f"{change['absolute_change']:.2f}"
                if change.get("percentage_change") is not None:
                    value_part += f"，变化率 {change['percentage_change']:.2f}%"
                answer_parts.append(
                    f"{item['topic']}：{'; '.join(report_bits)}。"
                    f"按所选报告口径比较，{change['previous'].get('value')} -> {change['latest'].get('value')}，"
                    f"绝对变化 {value_part}，单位 {change.get('change_unit') or '原文单位'}。"
                )
                if change.get("warnings"):
                    answer_parts.append("口径提示：" + "，".join(change["warnings"]))
            else:
                excerpts = []
                for row in rows:
                    excerpt = (row.get("excerpt") or "")[:80]
                    if excerpt:
                        excerpts.append(excerpt)
                answer_parts.append(
                    f"{item['topic']}：{'; '.join(report_bits)}。"
                    "已检索到分报告证据，但当前口径或证据不足以稳健计算变化。"
                    + (f" 证据摘要：{' | '.join(excerpts)}。" if excerpts else "")
                )

        if not answer_parts:
            return self._payload(
                status="insufficient_evidence",
                symbol=symbol,
                selected_report_ids=unique_report_ids,
                question=question,
                answer="未找到足够证据完成显式比较。",
                comparison_items=comparison_items,
                citations=citations,
                warnings=sorted(set(warnings + ["insufficient_evidence"])),
                started=started,
            )

        build_comparison_prompt(question, comparison_items)
        status = "answered" if all(item["change"].get("comparable") for item in comparison_items) else "partial"
        confidence = 0.95 if status == "answered" else 0.72
        return self._payload(
            status=status,
            symbol=symbol,
            selected_report_ids=unique_report_ids,
            question=question,
            answer="；".join(answer_parts),
            comparison_items=comparison_items,
            citations=citations,
            warnings=sorted(set(warnings)),
            started=started,
            confidence=confidence,
        )

    @staticmethod
    def _payload(
        *,
        status: str,
        symbol: str,
        selected_report_ids: list[int],
        question: str,
        answer: str,
        comparison_items: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        warnings: list[str],
        started: float,
        confidence: float = 0.0,
    ) -> dict[str, Any]:
        selected_reports = _selected_reports_payload(selected_report_ids)
        return {
            "status": status,
            "symbol": symbol,
            "selected_report_ids": selected_report_ids,
            "selected_reports": selected_reports,
            "question": question,
            "answer": answer,
            "comparison_items": comparison_items,
            "citations": citations,
            "cross_report_leakage_detected": False,
            "warnings": warnings,
            "confidence": confidence,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }


company_v2_report_comparison_answer_service = CompanyV2ReportComparisonAnswerService()
