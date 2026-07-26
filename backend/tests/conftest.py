from __future__ import annotations

import os

import pytest

# Phase 6T-J1: unit tests explicitly inject the in-memory RAG repository so the
# suite never writes the production company_v2_report_rag_* tables. Persistence
# tests construct DatabaseCompanyV2ReportRagRepository explicitly with isolated
# report_ids and clean up after themselves.
os.environ.setdefault("COMPANY_V2_RAG_REPOSITORY_BACKEND", "memory")

os.environ["CORS_ORIGINS"] = (
    "["
    '"http://localhost:3000",'
    '"http://localhost:3001",'
    '"http://localhost:3002",'
    '"http://localhost:5173",'
    '"http://localhost:5174",'
    '"http://127.0.0.1:3000",'
    '"http://127.0.0.1:3001",'
    '"http://127.0.0.1:3002",'
    '"http://127.0.0.1:5173",'
    '"http://127.0.0.1:5174"'
    "]"
)


_EXTERNAL_MARKERS = {"integration_live", "live_external", "live_supabase", "soak"}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Default test run is local-only.

    Live Supabase/RAG/worker tests are useful, but they must not make
    `pytest -q` depend on external DNS or wait for network timeouts.
    """
    mark_expr = str(config.option.markexpr or "").strip()
    selected_external = any(name in mark_expr for name in _EXTERNAL_MARKERS)
    skip_external = pytest.mark.skip(reason="requires live external services; run with -m integration_live or -m live_external or -m soak")

    for item in items:
        if item.get_closest_marker("live_supabase"):
            item.add_marker(pytest.mark.integration_live)
            item.add_marker(pytest.mark.live_external)
        if item.get_closest_marker("soak"):
            item.add_marker(pytest.mark.integration_live)
        if not selected_external and any(item.get_closest_marker(name) for name in _EXTERNAL_MARKERS):
            item.add_marker(skip_external)
