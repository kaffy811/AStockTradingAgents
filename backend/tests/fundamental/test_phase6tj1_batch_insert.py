"""Phase 6T-J1: chunk inserts are batched (never per-chunk commits)."""
from __future__ import annotations

import pytest

from app.services.company_v2_report_rag_db_repository import DatabaseCompanyV2ReportRagRepository
from tests.fundamental.phase6tj1_helpers import cleanup, embeddings_for, make_descriptor, make_drafts

pytestmark = pytest.mark.live_supabase

RID = 990006


def test_batch_insert_counts():
    repo = DatabaseCompanyV2ReportRagRepository(chunk_batch_size=2)
    try:
        drafts = make_drafts(RID, 5)
        repo.upsert_index(
            make_descriptor(RID),
            page_count=5,
            chunk_drafts=drafts,
            embeddings_by_hash=embeddings_for(drafts),
            status="indexed",
        )
        stats = repo.last_batch_stats
        assert stats["batches_total"] == 3  # ceil(5 / 2)
        assert stats["batches_success"] == 3
        assert stats["batches_failed"] == 0
        assert stats["persisted_chunk_count"] == 5
        assert repo.count_chunks(RID) == 5
    finally:
        cleanup([RID])
