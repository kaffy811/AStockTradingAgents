"""Phase 6T-J1: fusion/status paths resolve the factory repository (no private memory)."""
from __future__ import annotations

from app.core.config import settings
from app.services import company_v2_report_rag_repository_factory as factory
from app.services.company_v2_report_rag_index_service import (
    company_v2_report_rag_index_service,
    company_v2_report_rag_repository,
)


def test_fusion_reads_through_index_service_singleton():
    # The financial evidence fusion service resolves RAG data via
    # company_v2_report_rag_index_service (lazy import in _load path); assert the
    # service's repository is the factory singleton, so fusion can never read a
    # different (memory) store than the index writer.
    import inspect

    from app.services import company_v2_financial_evidence_fusion_service as fusion_module

    src = inspect.getsource(fusion_module)
    assert "company_v2_report_rag_index_service" in src
    assert company_v2_report_rag_index_service.repository is company_v2_report_rag_repository


def test_production_default_backend_is_database(monkeypatch):
    monkeypatch.setattr(settings, "company_v2_rag_repository_backend", "database")
    factory._singleton = None
    factory._singleton_backend = None
    status = factory.repository_status()
    assert status == {"repository_backend": "database", "persistent": True}
    factory._singleton = None
    factory._singleton_backend = None


def test_settings_field_default_is_database():
    assert type(settings).model_fields["company_v2_rag_repository_backend"].default == "database"
