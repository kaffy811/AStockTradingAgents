"""Grounded answer service for Company V2 report QA."""
from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Any

from app.services.company_v2_report_rag_prompt_builder import build_prompt, classify_question
from app.services.company_v2_report_rag_retriever import company_v2_report_rag_retriever


MAX_QUESTION_CHARS = 500
MIN_EVIDENCE_SCORE = 0.08


@dataclass(slots=True)
class RagAnswerResult:
    status: str
    report_id: int
    symbol: str | None
    report_year: int | None
    report_type: str | None
    question: str
    answer: str
    citations: list[dict[str, Any]]
    retrieval_mode: str
    confidence: float
    warnings: list[str]
    latency_ms: int


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。；;])|\n+", text or "")
    return [part.strip() for part in parts if part.strip()]


def _best_sentences(excerpt: str, question: str, limit: int = 3) -> list[str]:
    keywords = [
        "营业收入", "归属于上市公司股东的净利润", "净利润", "经营活动产生的现金流量净额",
        "现金流", "风险", "前五名客户", "销售额占比", "主营业务", "主要业务", "利润保证",
    ]
    active = [kw for kw in keywords if kw in question]
    if not active:
        active = [kw for kw in keywords if kw in excerpt]
    selected: list[str] = []
    for sentence in _sentences(excerpt):
        if "归属于上市公司股东" in question and "扣除" not in question and "扣除非经常性损益" in sentence:
            continue
        if any(kw in sentence for kw in active):
            selected.append(sentence)
        if len(selected) >= limit:
            break
    if not selected:
        selected = _sentences(excerpt)[:limit]
    return selected


def _make_citations(chunks: list[dict[str, Any]], question: str, limit: int = 3) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for chunk in chunks[:limit]:
        page = chunk["page_start"] if chunk["page_start"] == chunk["page_end"] else f"{chunk['page_start']}-{chunk['page_end']}"
        citations.append(
            {
                "page": page,
                "chunk_id": chunk["chunk_id"],
                "excerpt": "；".join(_best_sentences(chunk["text_excerpt"], question, limit=2))[:500],
                "source_url": chunk["source_url"],
            }
        )
    return citations


class CompanyV2ReportRagAnswerService:
    def answer(
        self,
        *,
        report_id: int,
        question: str,
        top_k: int = 6,
        language: str = "zh",
        answer_style: str = "concise",
        symbol: str | None = None,
        report_year: int | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        question = (question or "").strip()
        if len(question) > MAX_QUESTION_CHARS:
            return self._error(report_id, question[:MAX_QUESTION_CHARS], "QUESTION_TOO_LONG", started)

        classification = classify_question(question)
        doc = company_v2_report_rag_retriever.repository.get_document(report_id)
        doc_symbol = doc.symbol if doc else symbol
        doc_year = doc.report_year if doc else report_year
        doc_type = doc.report_type if doc else None

        if classification.refused:
            reason = classification.reason or "out_of_scope"
            answer = "该问题超出单份公告原文问答范围。可以询问报告中披露的事实、财务指标、风险因素或业务描述；我不能提供投资建议、目标价或未来涨跌预测。"
            return self._payload(
                status="insufficient_evidence" if reason != "investment_advice" else "answered",
                report_id=report_id,
                symbol=doc_symbol,
                report_year=doc_year,
                report_type=doc_type,
                question=question,
                answer=answer,
                citations=[],
                retrieval_mode="guardrail",
                confidence=1.0,
                warnings=[reason],
                started=started,
                selected_report_id=report_id,
                retrieved_report_ids=[],
                cross_report_leakage_detected=False,
            )

        mentioned_years = {int(year) for year in re.findall(r"(20\d{2})\s*年?", question)}
        if doc_year and mentioned_years and int(doc_year) not in mentioned_years:
            return self._payload(
                status="insufficient_evidence",
                report_id=report_id,
                symbol=doc_symbol,
                report_year=doc_year,
                report_type=doc_type,
                question=question,
                answer=f"当前选中的是 {doc_year} 年 {doc_type or 'report'}，问题涉及 {sorted(mentioned_years)}，不能跨报告或跨年度补齐。",
                citations=[],
                retrieval_mode="guardrail",
                confidence=1.0,
                warnings=["wrong_year_for_selected_report"],
                started=started,
                selected_report_id=report_id,
                retrieved_report_ids=[],
                cross_report_leakage_detected=False,
            )
        if doc_type in {"q1", "q3", "quarterly"} and re.search(r"全年|年度|年报", question):
            return self._payload(
                status="insufficient_evidence",
                report_id=report_id,
                symbol=doc_symbol,
                report_year=doc_year,
                report_type=doc_type,
                question=question,
                answer="当前选中的是季度报告，不能自动检索年度报告补齐全年问题。",
                citations=[],
                retrieval_mode="guardrail",
                confidence=1.0,
                warnings=["annual_question_on_quarterly_report"],
                started=started,
                selected_report_id=report_id,
                retrieved_report_ids=[],
                cross_report_leakage_detected=False,
            )

        retrieval = company_v2_report_rag_retriever.retrieve(
            report_id=report_id,
            question=question,
            top_k=top_k,
            symbol=symbol,
            report_year=report_year,
        )
        if retrieval.get("error_code"):
            return self._payload(
                status="failed" if retrieval["error_code"] != "REPORT_NOT_INDEXED" else "insufficient_evidence",
                report_id=report_id,
                symbol=doc_symbol,
                report_year=doc_year,
                report_type=doc_type,
                question=question,
                answer="当前报告问答索引不可用，无法提供有页码证据的回答。",
                citations=[],
                retrieval_mode=retrieval.get("retrieval_mode") or "unavailable",
                confidence=0.0,
                warnings=[retrieval["error_code"]],
                started=started,
                selected_report_id=retrieval.get("selected_report_id") or report_id,
                retrieved_report_ids=retrieval.get("retrieved_report_ids") or [],
                cross_report_leakage_detected=bool(retrieval.get("cross_report_leakage_detected")),
            )

        chunks = retrieval.get("chunks") or []
        retrieved_report_ids = sorted({int(chunk.get("report_id")) for chunk in chunks if chunk.get("report_id") is not None})
        if any(rid != int(report_id) for rid in retrieved_report_ids):
            return self._payload(
                status="failed",
                report_id=report_id,
                symbol=doc_symbol,
                report_year=doc_year,
                report_type=doc_type,
                question=question,
                answer="检索结果出现跨报告泄漏，已中止回答。",
                citations=[],
                retrieval_mode=retrieval.get("retrieval_mode") or "hybrid",
                confidence=0.0,
                warnings=["cross_report_leakage_detected"],
                started=started,
                selected_report_id=report_id,
                retrieved_report_ids=retrieved_report_ids,
                cross_report_leakage_detected=True,
            )
        best_score = chunks[0]["score"] if chunks else 0.0
        if not chunks or best_score < MIN_EVIDENCE_SCORE:
            return self._payload(
                status="insufficient_evidence",
                report_id=report_id,
                symbol=doc_symbol,
                report_year=doc_year,
                report_type=doc_type,
                question=question,
                answer="未在所选报告的已检索页码中找到足够证据，无法回答该问题。",
                citations=[],
                retrieval_mode=retrieval.get("retrieval_mode") or "hybrid",
                confidence=round(best_score, 4),
                warnings=["insufficient_evidence"],
                started=started,
                selected_report_id=retrieval.get("selected_report_id") or report_id,
                retrieved_report_ids=retrieved_report_ids,
                cross_report_leakage_detected=bool(retrieval.get("cross_report_leakage_detected")),
            )

        if "未来利润保证" in question or "利润保证" in question:
            evidence_text = "\n".join(chunk["text_excerpt"] for chunk in chunks)
            if not re.search(r"未来利润保证|利润保证|业绩承诺|盈利预测承诺", evidence_text):
                return self._payload(
                    status="insufficient_evidence",
                    report_id=report_id,
                    symbol=doc_symbol,
                    report_year=doc_year,
                    report_type=doc_type,
                    question=question,
                    answer="未在所选报告检索片段中找到“未来利润保证”或同义披露的明确证据。",
                    citations=[],
                    retrieval_mode=retrieval.get("retrieval_mode") or "hybrid",
                    confidence=round(best_score, 4),
                    warnings=["insufficient_evidence"],
                    started=started,
                    selected_report_id=retrieval.get("selected_report_id") or report_id,
                    retrieved_report_ids=retrieved_report_ids,
                    cross_report_leakage_detected=bool(retrieval.get("cross_report_leakage_detected")),
                )

        citations = _make_citations(chunks, question)
        answer_sentences = _best_sentences(chunks[0]["text_excerpt"], question, limit=3)
        prefix = "根据所选报告披露，"
        if classification.category == "risk_factor":
            prefix = "根据所选报告的风险相关披露，"
        elif classification.category == "business_segment":
            prefix = "根据所选报告的业务相关披露，"
        answer = prefix + "；".join(answer_sentences)
        if citations:
            pages = "、".join(str(cite["page"]) for cite in citations[:2])
            answer += f"（见第 {pages} 页）。"
        if "单位" not in answer and re.search(r"万元|亿元|元", chunks[0]["text_excerpt"]):
            answer += " 请以引用页原文单位为准，未在回答中自行换算。"

        build_prompt(question, chunks[: min(3, len(chunks))])  # Keeps prompt contract explicit without invoking an LLM.
        return self._payload(
            status="answered",
            report_id=report_id,
            symbol=doc_symbol,
            report_year=doc_year,
            report_type=doc_type,
            question=question,
            answer=answer[:1200],
            citations=citations,
            retrieval_mode=retrieval.get("retrieval_mode") or "hybrid",
            confidence=round(min(0.98, best_score), 4),
            warnings=[],
            started=started,
            selected_report_id=retrieval.get("selected_report_id") or report_id,
            retrieved_report_ids=retrieved_report_ids,
            cross_report_leakage_detected=bool(retrieval.get("cross_report_leakage_detected")),
        )

    def _error(self, report_id: int, question: str, error_code: str, started: float) -> dict[str, Any]:
        return self._payload(
            status="failed",
            report_id=report_id,
            symbol=None,
            report_year=None,
            report_type=None,
            question=question,
            answer="请求不符合报告问答约束。",
            citations=[],
            retrieval_mode="guardrail",
            confidence=0.0,
            warnings=[error_code],
            started=started,
            selected_report_id=report_id,
            retrieved_report_ids=[],
            cross_report_leakage_detected=False,
        )

    @staticmethod
    def _payload(
        *,
        status: str,
        report_id: int,
        symbol: str | None,
        report_year: int | None,
        report_type: str | None,
        question: str,
        answer: str,
        citations: list[dict[str, Any]],
        retrieval_mode: str,
        confidence: float,
        warnings: list[str],
        started: float,
        selected_report_id: int | None = None,
        retrieved_report_ids: list[int] | None = None,
        cross_report_leakage_detected: bool = False,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "report_id": report_id,
            "symbol": symbol,
            "report_year": report_year,
            "report_type": report_type,
            "question": question,
            "answer": answer,
            "citations": citations,
            "retrieval_mode": retrieval_mode,
            "confidence": confidence,
            "warnings": warnings,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "selected_report_id": selected_report_id if selected_report_id is not None else report_id,
            "retrieved_report_ids": retrieved_report_ids or [],
            "cross_report_leakage_detected": cross_report_leakage_detected,
        }


company_v2_report_rag_answer_service = CompanyV2ReportRagAnswerService()
