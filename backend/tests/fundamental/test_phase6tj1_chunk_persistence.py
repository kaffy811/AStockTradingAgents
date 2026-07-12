"""Phase 6T-J1: chunk rows persist text/pages/hash/embedding/version metadata."""
from __future__ import annotations

import pytest

from tests.fundamental.phase6tj1_helpers import cleanup, db_repo, embeddings_for, make_descriptor, make_drafts

pytestmark = pytest.mark.live_supabase

RID = 990004


def test_chunk_fields_persisted():
    repo = db_repo()
    try:
        drafts = make_drafts(RID, 4)
        repo.upsert_index(
            make_descriptor(RID),
            page_count=4,
            chunk_drafts=drafts,
            embeddings_by_hash=embeddings_for(drafts),
            status="indexed",
        )
        doc = db_repo().get_document(RID)
        assert doc is not None and len(doc.chunks) == 4
        for i, chunk in enumerate(sorted(doc.chunks, key=lambda c: c.chunk_index)):
            assert chunk.report_id == RID
            assert chunk.rag_document_id == doc.id
            assert chunk.chunk_index == i
            assert 1 <= chunk.page_start <= 4 and chunk.page_start <= chunk.page_end <= 4
            assert chunk.text.strip()
            assert chunk.text_hash
            assert chunk.embedding == [0.1, 0.2, 0.3]  # JSON round-trip
            meta = chunk.metadata_json
            assert meta["chunking_version"] == "company-v2-pages-v1"
            assert meta["embedding_model"] == "company-v2-hash-keyword"
            assert meta["embedding_version"] == "company-v2-hash-keyword-v1"
            assert meta["index_generation"] == 1
    finally:
        cleanup([RID])
