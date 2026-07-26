"""Phase 6T-J1: an independent Python process reads the persisted index (DB-only)."""
from __future__ import annotations

import pytest
import json
import os
import subprocess
import sys
from pathlib import Path

from tests.fundamental.phase6tj1_helpers import cleanup, db_repo, embeddings_for, make_descriptor, make_drafts

pytestmark = pytest.mark.live_supabase

RID = 990008
BACKEND_ROOT = Path(__file__).resolve().parents[2]

_CHILD = """
import json
from app.services.company_v2_report_rag_repository_factory import (
    get_company_v2_report_rag_repository, repository_status)
status = repository_status()
repo = get_company_v2_report_rag_repository()
doc = repo.get_document({rid})
print(json.dumps({{
    "backend": status["repository_backend"],
    "persistent": status["persistent"],
    "found": doc is not None,
    "chunks": repo.count_chunks({rid}),
}}))
"""


def test_independent_process_reads_persisted_index():
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
        env = {**os.environ, "COMPANY_V2_RAG_REPOSITORY_BACKEND": "database"}
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD.format(rid=RID)],
            cwd=str(BACKEND_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr[-500:]
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        assert payload == {"backend": "database", "persistent": True, "found": True, "chunks": 3}
    finally:
        cleanup([RID])
