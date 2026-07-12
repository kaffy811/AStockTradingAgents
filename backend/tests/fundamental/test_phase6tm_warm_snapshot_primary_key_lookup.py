from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service
from scripts import company_v2_financial_fusion_phase6tk_profile as profile_module


def test_profile_symbol_does_not_prefetch_rag_status(monkeypatch, tmp_path):
    doc = SimpleNamespace(
        id=2,
        report_year=2025,
        report_type="annual",
        local_path=str(tmp_path / "report_2.pdf"),
        pdf_url="https://static.cninfo.com.cn/finalpage/2026-04-01/test.PDF",
        source_url="https://static.cninfo.com.cn/finalpage/2026-04-01/test.PDF",
        file_sha256="sha-test",
        parse_status="parsed",
    )
    sidecar = tmp_path / "report_2.pages.json"
    sidecar.write_text('{"page_count": 1, "text_pages": []}', encoding="utf-8")
    async def _latest_annual(_symbol):
        return doc

    monkeypatch.setattr(profile_module, "_latest_annual", _latest_annual)
    monkeypatch.setattr(profile_module, "_sidecar", lambda _doc: sidecar)
    monkeypatch.setattr(
        profile_module.company_v2_financial_evidence_fusion_service,
        "run",
        lambda **_kwargs: {
            "ok": True,
            "cache_hit": True,
            "summary": {},
            "timings": {
                "eligibility_latency_ms": 0.0,
                "cache_lookup_latency_ms": 0.0,
                "retrieval_latency_ms": 0.0,
                "resolver_latency_ms": 0.0,
                "alignment_latency_ms": 0.0,
                "persistence_latency_ms": 0.0,
                "total_latency_ms": 0.0,
            },
        },
    )
    monkeypatch.setattr(
        company_v2_report_rag_index_service,
        "status",
        lambda _report_id: (_ for _ in ()).throw(AssertionError("rag status should not be prefetched")),
    )

    result = asyncio.run(profile_module.profile_symbol("600519", refresh=False))

    assert result["ok"] is True
    assert result["cache_hit"] is True
