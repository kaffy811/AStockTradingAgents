"""Phase 6T-J1: a brand-new repository/session/engine reads persisted index."""
from __future__ import annotations

import pytest

from tests.fundamental.phase6tj1_helpers import cleanup, db_repo, embeddings_for, make_descriptor, make_drafts

pytestmark = pytest.mark.live_supabase

RID = 990007


def test_restart_read_from_fresh_engine():
    writer = db_repo()
    try:
        drafts = make_drafts(RID, 3)
        writer.upsert_index(
            make_descriptor(RID),
            page_count=3,
            chunk_drafts=drafts,
            embeddings_by_hash=embeddings_for(drafts),
            status="indexed",
        )
        # brand-new repository == new engine + new sessions (restart semantics)
        reader = db_repo()
        assert reader is not writer
        doc = reader.get_document(RID)
        assert doc is not None
        assert doc.chunk_count == 3
        assert len(doc.chunks) == 3
        assert reader.count_chunks(RID) == 3
        assert doc.chunks[0].embedding == [0.1, 0.2, 0.3]
    finally:
        cleanup([RID])
