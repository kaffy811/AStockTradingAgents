"""Phase 6T-J1: failed index transaction rolls back; old active generation survives."""
from __future__ import annotations

import pytest

from app.services.company_v2_report_rag_db_repository import CompanyV2RagRepositoryError
from tests.fundamental.phase6tj1_helpers import cleanup, db_repo, embeddings_for, make_descriptor, make_drafts

pytestmark = pytest.mark.live_supabase

RID = 990005


def test_rollback_leaves_no_partial_rows_and_preserves_old_active():
    repo = db_repo()
    try:
        # generation 1: healthy index
        drafts_ok = make_drafts(RID, 3)
        doc1 = repo.upsert_index(
            make_descriptor(RID, pdf_hash="c" * 64),
            page_count=3,
            chunk_drafts=drafts_ok,
            embeddings_by_hash=embeddings_for(drafts_ok),
            status="indexed",
        )
        assert doc1.index_generation == 1 and doc1.active_index is True

        # generation 2 attempt with an empty chunk → must roll back entirely
        drafts_bad = make_drafts(RID, 3, empty_at=1)
        with pytest.raises(CompanyV2RagRepositoryError) as exc:
            repo.upsert_index(
                make_descriptor(RID, pdf_hash="d" * 64),  # identity changed → new generation path
                page_count=3,
                chunk_drafts=drafts_bad,
                embeddings_by_hash=embeddings_for(drafts_bad),
                status="indexed",
            )
        assert exc.value.error_code in {"EMPTY_CHUNK", "RAG_DB_QUERY_FAILED"}

        # old generation still active, chunk count intact, no half-active gen 2
        fresh = db_repo()
        active = fresh.get_document(RID)
        assert active is not None
        assert active.index_generation == 1
        assert active.pdf_hash == "c" * 64
        assert fresh.count_chunks(RID) == 3
        history = fresh.list_history(RID)
        assert all(not (d.index_generation == 2 and d.active_index) for d in history)
    finally:
        cleanup([RID])
