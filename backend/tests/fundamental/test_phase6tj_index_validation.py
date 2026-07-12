from __future__ import annotations

import asyncio

from .phase6te3_helpers import descriptor, sidecar


def test_index_uses_sidecar_and_is_idempotent(tmp_path, monkeypatch):
    from app.services.company_v2_report_embedding_service import company_v2_report_embedding_service
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository

    company_v2_report_rag_repository.clear()
    monkeypatch.setattr(company_v2_report_embedding_service, "embed_batch", lambda texts, existing_hashes=None: ([
        type("E", (), {"text_hash": "h1", "embedding": [0.1, 0.2]}),
        type("E", (), {"text_hash": "h2", "embedding": [0.3, 0.4]}),
    ], 0))

    desc = descriptor(1, 2024, "annual", "友发集团2024年年度报告")
    result = company_v2_report_rag_index_manager.create_index(desc, sidecar(tmp_path, 1, 2024, "annual"))
    repeat = company_v2_report_rag_index_manager.create_index(desc, sidecar(tmp_path, 1, 2024, "annual"))

    assert result["ok"] is True
    assert result["chunk_count"] >= 1
    assert repeat["rag_document_id"] == result["rag_document_id"]
    assert company_v2_report_rag_index_manager.repository.get_document(1).status in {"indexed", "partial"}
