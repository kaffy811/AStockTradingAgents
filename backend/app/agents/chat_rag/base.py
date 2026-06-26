"""
chat_rag/base.py — Phase C11 RAG data structures.

RAGDocument: a single retrieved piece of context with source metadata.
RAGResult: the full retrieval + review result returned to a Skill.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RAGDocument:
    """A single retrieved context document."""
    doc_id: str
    source_type: str          # news | report | industry | watchlist | memory
    title: str
    summary: str
    source: str | None = None
    published_at: str | None = None
    url: str | None = None
    market: str | None = None
    symbol: str | None = None
    confidence: float | None = None
    # Content origin flags (used by review agents)
    external_content: bool = False   # news / external web content
    internal_content: bool = False   # reports, watchlist, industry from our DB
    metadata: dict = field(default_factory=dict)


@dataclass
class RAGResult:
    """Full retrieval result including optional review outcome."""
    ok: bool
    query: str
    documents: list[RAGDocument] = field(default_factory=list)
    reviewed: bool = False
    review_result: dict | None = None
    error: str | None = None

    @property
    def news_docs(self) -> list[RAGDocument]:
        return [d for d in self.documents if d.source_type == "news"]

    @property
    def report_docs(self) -> list[RAGDocument]:
        return [d for d in self.documents if d.source_type == "report"]

    @property
    def industry_docs(self) -> list[RAGDocument]:
        return [d for d in self.documents if d.source_type == "industry"]

    @property
    def overall_confidence(self) -> str:
        """Convenience: 'high' | 'medium' | 'low' from review_result."""
        if self.review_result:
            return self.review_result.get("overall_confidence", "medium")
        return "medium"

    @property
    def approved(self) -> bool:
        if self.review_result:
            return bool(self.review_result.get("approved_for_answer", True))
        return True

    def source_summary(self) -> str:
        """Human-readable source summary for inclusion in answers."""
        parts = []
        n_news = len(self.news_docs)
        n_reports = len(self.report_docs)
        n_industry = len(self.industry_docs)
        if n_news:
            parts.append(f"{n_news} 条新闻")
        if n_reports:
            parts.append(f"{n_reports} 份历史报告")
        if n_industry:
            parts.append(f"{n_industry} 条行业数据")
        return "、".join(parts) if parts else "内部数据"
