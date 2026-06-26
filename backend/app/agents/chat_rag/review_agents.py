"""
chat_rag/review_agents.py — Phase C11 RAG Review Agents.

Three rule-based review agents + coordinator:
  SourceReviewAgent      — checks source attribution
  FreshnessReviewAgent   — checks data timeliness
  ConsistencyReviewAgent — checks cross-source consistency
  RAGReviewCoordinator   — aggregates all reviews

All agents are rule-based (no LLM). Review result enters audit metadata.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta

from app.agents.chat_rag.base import RAGDocument, RAGResult

log = logging.getLogger(__name__)

_NOW = None  # Injected at review time for testability


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceReviewAgent:
    """
    Checks that documents have proper source attribution.
    Penalises external content without a named source.
    """

    def review(self, result: RAGResult) -> dict:
        missing_sources: list[str] = []
        warnings: list[str] = []
        score = 1.0

        for doc in result.documents:
            if not doc.source:
                missing_sources.append(doc.doc_id)
                score -= 0.15
                if doc.external_content:
                    warnings.append(f"外部内容 {doc.doc_id!r} 缺少来源信息，已降低可信度")
            elif doc.external_content and doc.source in ("", "unknown"):
                warnings.append(f"文档 {doc.doc_id!r} 来源字段为空")
                score -= 0.10

        if not result.documents:
            warnings.append("未检索到任何文档")
            score = 0.3

        return {
            "source_score": max(0.0, round(score, 2)),
            "missing_sources": missing_sources,
            "warnings": warnings,
        }


class FreshnessReviewAgent:
    """
    Checks timeliness of documents.
    News older than 7 days or reports older than 30 days get penalised.
    """

    _NEWS_STALE_DAYS = 7
    _REPORT_STALE_DAYS = 30

    def review(self, result: RAGResult, now: datetime | None = None) -> dict:
        now = now or _utcnow()
        stale_docs: list[str] = []
        warnings: list[str] = []
        score = 1.0
        missing_ts = 0

        for doc in result.documents:
            if not doc.published_at:
                missing_ts += 1
                continue
            try:
                ts_str = doc.published_at.replace("Z", "+00:00")
                if "+" not in ts_str and "T" in ts_str:
                    ts_str += "+00:00"
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_days = (now - ts).days

                if doc.source_type == "news" and age_days > self._NEWS_STALE_DAYS:
                    stale_docs.append(doc.doc_id)
                    score -= 0.10
                    warnings.append(f"新闻 {doc.doc_id!r} 已超过 {self._NEWS_STALE_DAYS} 天（{age_days}天前）")
                elif doc.source_type == "report" and age_days > self._REPORT_STALE_DAYS:
                    stale_docs.append(doc.doc_id)
                    score -= 0.05
                    warnings.append(f"报告 {doc.doc_id!r} 已超过 {self._REPORT_STALE_DAYS} 天（{age_days}天前）")
            except (ValueError, TypeError):
                missing_ts += 1

        if missing_ts > 0:
            score -= 0.05 * missing_ts
            warnings.append(f"{missing_ts} 个文档缺少时间信息")

        if not result.documents:
            score = 0.3

        return {
            "freshness_score": max(0.0, round(score, 2)),
            "stale_documents": stale_docs,
            "warnings": warnings,
        }


class ConsistencyReviewAgent:
    """
    Checks cross-source consistency.
    Detects conflicting stock names/symbols, uncertain conclusions presented as facts.
    """

    _FORBIDDEN_CERTAINTY = re.compile(
        r"必涨|必跌|稳赚|一定会|肯定会|百分之百|无悬念",
        re.IGNORECASE,
    )

    def review(self, result: RAGResult) -> dict:
        conflicts: list[str] = []
        warnings: list[str] = []
        score = 1.0

        # Check stock symbol consistency
        symbols_seen: dict[str, set[str]] = {}  # name → set of symbols
        for doc in result.documents:
            if doc.symbol and doc.title:
                name = doc.title[:10]
                symbols_seen.setdefault(name, set()).add(doc.symbol)
        for name, syms in symbols_seen.items():
            if len(syms) > 1:
                conflicts.append(f"文档集合中 '{name}' 对应多个代码：{syms}")
                score -= 0.15
                warnings.append(f"检测到股票名称/代码不一致：{syms}")

        # Check for overly certain language in summaries
        for doc in result.documents:
            if self._FORBIDDEN_CERTAINTY.search(doc.summary or ""):
                conflicts.append(f"文档 {doc.doc_id!r} 包含不可验证的确定性结论")
                score -= 0.10
                warnings.append(f"文档 {doc.doc_id!r} 使用了确定性结论表达，请核实")

        # Check external vs internal conflict on same topic
        external_docs = [d for d in result.documents if d.external_content]
        internal_docs = [d for d in result.documents if d.internal_content]
        if external_docs and internal_docs:
            ext_symbols = {d.symbol for d in external_docs if d.symbol}
            int_symbols = {d.symbol for d in internal_docs if d.symbol}
            if ext_symbols and int_symbols and not ext_symbols.intersection(int_symbols):
                warnings.append("外部新闻与内部报告涉及不同股票，请注意来源混用")
                score -= 0.05

        if not result.documents:
            score = 0.3

        return {
            "consistency_score": max(0.0, round(score, 2)),
            "conflicts": conflicts,
            "warnings": warnings,
        }


class RAGReviewCoordinator:
    """
    Runs all three review agents and produces aggregate confidence rating.
    """

    def __init__(self) -> None:
        self._source = SourceReviewAgent()
        self._freshness = FreshnessReviewAgent()
        self._consistency = ConsistencyReviewAgent()

    def review(self, result: RAGResult) -> dict:
        """
        Aggregate review. Updates result.review_result and result.reviewed in-place.
        Returns the review dict.
        """
        source_r = self._source.review(result)
        freshness_r = self._freshness.review(result)
        consistency_r = self._consistency.review(result)

        avg = (
            source_r["source_score"]
            + freshness_r["freshness_score"]
            + consistency_r["consistency_score"]
        ) / 3.0

        if avg >= 0.75:
            confidence = "high"
        elif avg >= 0.50:
            confidence = "medium"
        else:
            confidence = "low"

        approved = avg >= 0.40 and len(result.documents) > 0

        all_warnings = (
            source_r["warnings"]
            + freshness_r["warnings"]
            + consistency_r["warnings"]
        )

        review_result = {
            "overall_confidence": confidence,
            "overall_score": round(avg, 2),
            "source_score": source_r["source_score"],
            "freshness_score": freshness_r["freshness_score"],
            "consistency_score": consistency_r["consistency_score"],
            "missing_sources": source_r["missing_sources"],
            "stale_documents": freshness_r["stale_documents"],
            "conflicts": consistency_r["conflicts"],
            "warnings": all_warnings[:10],  # cap warning list
            "approved_for_answer": approved,
            "doc_count": len(result.documents),
        }

        result.reviewed = True
        result.review_result = review_result
        return review_result

    def format_for_answer(self, result: RAGResult) -> str:
        """
        Generate a 'Resource & Credibility' section for inclusion in Skill answers.
        Only included when RAG retrieval succeeded and has documents.
        """
        if not result.ok or not result.documents or not result.reviewed:
            return ""

        rr = result.review_result or {}
        confidence = rr.get("overall_confidence", "medium")
        warnings = rr.get("warnings", [])

        confidence_label = {
            "high": "高（来源充足，数据较新）",
            "medium": "中（部分数据较旧或来源不完整）",
            "low": "低（数据不足或来源缺失）",
        }.get(confidence, "中")

        lines = [
            "\n\n### 资料来源与可信度",
            f"本次参考了 {result.source_summary()}。资料审查结果为 **{confidence_label}**。",
        ]

        if confidence == "low":
            lines.append("⚠️ 资料不足或来源不完整，以上分析仅供参考，建议获取更多信息后再做判断。")

        if warnings:
            first_warning = warnings[0]
            lines.append(f"_限制说明：{first_warning}_")

        return "\n".join(lines)
