"""Phase 6T-J1: database repository core CRUD round-trip."""
from __future__ import annotations

import pytest

from tests.fundamental.phase6tj1_helpers import cleanup, db_repo, embeddings_for, make_descriptor, make_drafts

pytestmark = pytest.mark.live_supabase

RID = 990001


def test_db_repository_roundtrip():
    repo = db_repo()
    assert repo.backend == "database" and repo.persistent is True
    try:
        drafts = make_drafts(RID)
        doc = repo.upsert_index(
            make_descriptor(RID),
            page_count=5,
            chunk_drafts=drafts,
            embeddings_by_hash=embeddings_for(drafts),
            status="indexed",
        )
        assert doc.report_id == RID
        assert doc.status == "indexed"
        assert doc.active_index is True
        assert doc.index_generation == 1
        assert len(doc.chunks) == 5

        active = repo.get_document(RID)
        assert active is not None and active.id == doc.id
        assert repo.get_any_document(RID) is not None
        assert repo.count_chunks(RID) == 5
        history = repo.list_history(RID)
        assert len(history) == 1

        listed = repo.list_documents("990519")
        assert any(d.report_id == RID for d in listed)

        stale = repo.mark_stale(RID, "test_stale")
        assert stale is not None and stale.status == "stale"
        deleted = repo.soft_delete(RID)
        assert deleted is not None and deleted.deleted_at is not None
        assert repo.get_document(RID) is None
    finally:
        cleanup([RID])
