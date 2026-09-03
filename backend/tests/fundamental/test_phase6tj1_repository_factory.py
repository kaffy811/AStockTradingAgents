"""Phase 6T-J1: repository factory backend selection."""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import company_v2_report_rag_repository_factory as factory


def _reset():
    factory._singleton = None
    factory._singleton_backend = None


def test_factory_memory_backend(monkeypatch):
    monkeypatch.setattr(settings, "company_v2_rag_repository_backend", "memory")
    _reset()
    repo = factory.get_company_v2_report_rag_repository()
    assert repo.backend == "memory" and repo.persistent is False
    assert factory.repository_status() == {"repository_backend": "memory", "persistent": False}
    _reset()


def test_factory_database_backend(monkeypatch):
    monkeypatch.setattr(settings, "company_v2_rag_repository_backend", "database")
    _reset()
    repo = factory.get_company_v2_report_rag_repository()
    assert type(repo).__name__ == "DatabaseCompanyV2ReportRagRepository"
    assert factory.repository_status() == {"repository_backend": "database", "persistent": True}
    _reset()


def test_factory_invalid_backend_raises(monkeypatch):
    from app.services.company_v2_report_rag_db_repository import CompanyV2RagRepositoryError

    monkeypatch.setattr(settings, "company_v2_rag_repository_backend", "sqlite")
    _reset()
    with pytest.raises(CompanyV2RagRepositoryError) as exc:
        factory.get_company_v2_report_rag_repository()
    assert exc.value.error_code == "RAG_REPOSITORY_BACKEND_INVALID"
    _reset()


def test_factory_singleton_identity(monkeypatch):
    monkeypatch.setattr(settings, "company_v2_rag_repository_backend", "memory")
    _reset()
    assert factory.get_company_v2_report_rag_repository() is factory.get_company_v2_report_rag_repository()
    _reset()
