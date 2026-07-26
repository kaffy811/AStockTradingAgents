"""Phase 6T-J1: document row persists identity/version/generation metadata."""
from __future__ import annotations

import pytest

from tests.fundamental.phase6tj1_helpers import cleanup, db_repo, embeddings_for, make_descriptor, make_drafts

pytestmark = pytest.mark.live_supabase

RID = 990003


def test_document_fields_persisted():
    repo = db_repo()
    try:
        drafts = make_drafts(RID, 3)
        repo.upsert_index(
            make_descriptor(RID, pdf_hash="b" * 64),
            page_count=3,
            chunk_drafts=drafts,
            embeddings_by_hash=embeddings_for(drafts),
            status="indexed",
        )
        # read back through a FRESH repository (new engine/session)
        fresh = db_repo()
        doc = fresh.get_document(RID)
        assert doc is not None
        assert doc.report_id == RID
        assert doc.symbol == "990519"
        assert doc.market == "CN"
        assert doc.report_year == 2025
        assert doc.report_type == "annual"
        assert doc.pdf_hash == "b" * 64
        assert doc.parse_version == "company-v2-pages-v1"
        assert doc.embedding_model == "company-v2-hash-keyword"
        assert doc.embedding_version == "company-v2-hash-keyword-v1"
        assert doc.index_generation == 1
        assert doc.active_index is True
        assert doc.status == "indexed"
        assert doc.indexed_at is not None
        assert doc.created_at and doc.updated_at
    finally:
        cleanup([RID])
