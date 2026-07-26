"""Phase 6T-J1: identical index identity is reused — no duplicate rows."""
from __future__ import annotations

import pytest

from tests.fundamental.phase6tj1_helpers import cleanup, db_repo, embeddings_for, make_descriptor, make_drafts

pytestmark = pytest.mark.live_supabase

RID = 990009


def test_same_identity_reuses_generation_without_duplicates():
    repo = db_repo()
    try:
        drafts = make_drafts(RID, 3)
        kwargs = dict(
            page_count=3,
            chunk_drafts=drafts,
            embeddings_by_hash=embeddings_for(drafts),
            status="indexed",
        )
        doc1 = repo.upsert_index(make_descriptor(RID), **kwargs)
        doc2 = repo.upsert_index(make_descriptor(RID), **kwargs)  # identical identity

        assert doc2.id == doc1.id
        assert doc2.index_generation == doc1.index_generation == 1
        assert repo.last_batch_stats.get("duplicate_index_avoided") is True
        assert repo.last_batch_stats.get("persisted_chunk_count") == 0  # nothing re-inserted

        fresh = db_repo()
        assert fresh.count_chunks(RID) == 3
        assert len(fresh.list_history(RID)) == 1  # no extra generation rows
    finally:
        cleanup([RID])
