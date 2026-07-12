"""Phase 6T-J1: QA/retrieval/comparison paths share the factory repository singleton."""
from __future__ import annotations

from app.services import company_v2_report_comparison_answer_service as cmp_answer
from app.services import company_v2_report_comparison_retriever as cmp_retriever
from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
from app.services.company_v2_report_rag_index_service import (
    company_v2_report_rag_index_service,
    company_v2_report_rag_repository,
)
from app.services.company_v2_report_rag_retriever import CompanyV2ReportRagRetriever


def test_qa_paths_share_single_factory_repository():
    retriever = CompanyV2ReportRagRetriever()
    assert retriever.repository is company_v2_report_rag_repository
    assert company_v2_report_rag_index_service.repository is company_v2_report_rag_repository
    assert company_v2_report_rag_index_manager.repository is company_v2_report_rag_repository
    assert cmp_retriever.company_v2_report_rag_repository is company_v2_report_rag_repository
    assert cmp_answer.company_v2_report_rag_repository is company_v2_report_rag_repository


def test_status_exposes_backend_and_persistent():
    status = company_v2_report_rag_index_service.status(999999)
    assert "repository_backend" in status and "persistent" in status
    # unit-test context injects memory explicitly (conftest); production default is database
    assert status["repository_backend"] in {"memory", "database"}
    assert isinstance(status["persistent"], bool)
    assert status["persistent"] == (status["repository_backend"] == "database")
