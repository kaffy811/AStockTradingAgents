"""Phase 6T-J1: identity change creates a new generation and stales the old one."""
from __future__ import annotations

import pytest

from tests.fundamental.phase6tj1_helpers import cleanup, db_repo, embeddings_for, make_descriptor, make_drafts

pytestmark = pytest.mark.live_supabase

RID = 990010


def test_pdf_hash_change_switches_generation_and_keeps_audit_history():
    repo = db_repo()
    try:
        drafts = make_drafts(RID, 3)
        kwargs = dict(
            page_count=3,
            chunk_drafts=drafts,
            embeddings_by_hash=embeddings_for(drafts),
            status="indexed",
        )
        doc1 = repo.upsert_index(make_descriptor(RID, pdf_hash="e" * 64), **kwargs)
        doc2 = repo.upsert_index(make_descriptor(RID, pdf_hash="f" * 64), **kwargs)

        assert doc2.id != doc1.id
        assert doc2.index_generation == 2
        assert doc2.supersedes_rag_document_id == doc1.id
        assert doc2.active_index is True

        fresh = db_repo()
        active = fresh.get_document(RID)
        assert active.id == doc2.id and active.pdf_hash == "f" * 64

        history = fresh.list_history(RID)
        assert len(history) == 2  # old generation preserved for audit, not deleted
        old = next(d for d in history if d.index_generation == 1)
        assert old.active_index is False
        assert old.status == "stale"
        assert old.stale_reason
    finally:
        cleanup([RID])
