"""Phase 6T-J1: Company V2 RAG repository factory.

Selects the repository backend from ``COMPANY_V2_RAG_REPOSITORY_BACKEND``:
- ``database`` (production default): PostgreSQL persistence, persistent=True
- ``memory``: isolated unit tests only, persistent=False

Rules:
- No silent fallback: an invalid backend value or database initialization
  failure raises a structured error instead of degrading to memory.
- All production paths (index service, QA retrieval, comparison, fusion,
  status APIs) must obtain the repository through this factory singleton.
"""
from __future__ import annotations

import threading
from typing import Any

from app.core.config import settings

_VALID_BACKENDS = {"database", "memory"}
_singleton: Any = None
_singleton_backend: str | None = None
_lock = threading.Lock()


def get_company_v2_report_rag_repository() -> Any:
    """Return the process-wide repository singleton for the configured backend."""
    global _singleton, _singleton_backend
    backend = (settings.company_v2_rag_repository_backend or "database").strip().lower()
    if backend not in _VALID_BACKENDS:
        from app.services.company_v2_report_rag_db_repository import CompanyV2RagRepositoryError

        raise CompanyV2RagRepositoryError(
            "RAG_REPOSITORY_BACKEND_INVALID",
            f"COMPANY_V2_RAG_REPOSITORY_BACKEND={backend!r} (allowed: database, memory). No fallback performed.",
        )
    with _lock:
        if _singleton is not None and _singleton_backend == backend:
            return _singleton
        if backend == "memory":
            from app.services.company_v2_report_rag_index_service import CompanyV2ReportRagRepository

            _singleton = CompanyV2ReportRagRepository()
        else:
            from app.services.company_v2_report_rag_db_repository import DatabaseCompanyV2ReportRagRepository

            _singleton = DatabaseCompanyV2ReportRagRepository()
        _singleton_backend = backend
        return _singleton


def repository_status() -> dict[str, Any]:
    repo = get_company_v2_report_rag_repository()
    return {
        "repository_backend": getattr(repo, "backend", "memory"),
        "persistent": bool(getattr(repo, "persistent", False)),
    }
