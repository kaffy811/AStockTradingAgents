"""Phase 6T-J1: database failures raise structured errors — never memory fallback."""
from __future__ import annotations

import pytest

from app.services.company_v2_report_rag_db_repository import (
    CompanyV2RagRepositoryError,
    DatabaseCompanyV2ReportRagRepository,
)


def test_db_query_failure_raises_structured_error_no_fallback():
    repo = DatabaseCompanyV2ReportRagRepository(
        database_url="postgresql+asyncpg://invalid:invalid@127.0.0.1:1/na"
    )
    with pytest.raises(CompanyV2RagRepositoryError) as exc:
        repo.get_document(990002)
    assert exc.value.error_code in {"RAG_DB_QUERY_FAILED", "RAG_DB_INIT_FAILED"}
    # still a database repository — no silent downgrade to memory
    assert repo.backend == "database"
    assert repo.persistent is True


def test_error_message_does_not_leak_password():
    repo = DatabaseCompanyV2ReportRagRepository(
        database_url="postgresql+asyncpg://user:supersecretpw@127.0.0.1:1/na"
    )
    with pytest.raises(CompanyV2RagRepositoryError) as exc:
        repo.get_document(990002)
    assert "supersecretpw" not in str(exc.value)
