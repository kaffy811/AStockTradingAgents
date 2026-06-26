"""
chat_rag — Phase C11 Lightweight RAG + Review Agents.

Provides internal-data retrieval and rule-based review for Chat Copilot.
No external vector DB, no new dependencies — uses existing tool registry.
"""
from app.agents.chat_rag.base import RAGDocument, RAGResult
from app.agents.chat_rag.retriever import retrieve_context
from app.agents.chat_rag.review_agents import RAGReviewCoordinator

__all__ = ["RAGDocument", "RAGResult", "retrieve_context", "RAGReviewCoordinator"]
