from __future__ import annotations

from pathlib import Path

from app.models.company_v2_financial_evidence_fusion import FinancialEvidenceFusionRecord, FinancialEvidenceFusionSnapshot
from app.services.company_v2_financial_evidence_fusion_service import company_v2_financial_evidence_fusion_service
from app.services.company_v2_financial_fusion_cache import company_v2_financial_fusion_cache
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service


def test_warm_hit_returns_before_structured_or_official_recompute(tmp_path, monkeypatch):
    company_v2_financial_fusion_cache.clear()
    company_v2_financial_evidence_fusion_service.repository.clear()

    seed_path = tmp_path / "seed.json"
    seed_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        company_v2_report_rag_index_service,
        "status",
        lambda _report_id: {
            "repository_backend": "database",
            "persistent": True,
            "status": "indexed",
            "embedding_version": "company-v2-hash-keyword-v1",
            "index_generation": 1,
        },
    )

    cache_context = company_v2_financial_evidence_fusion_service._make_cache_context(  # noqa: SLF001
        symbol="600519",
        report_id=2,
        pdf_hash="hash",
        parse_version="parsed",
        seed_path=str(seed_path),
        selected_fields=["revenue"],
        embedding_version="company-v2-hash-keyword-v1",
    )
    snapshot = FinancialEvidenceFusionSnapshot(
        symbol="600519",
        report_id=2,
        report_year=2025,
        report_type="annual",
        fields_total=1,
        verified=1,
        normalized_match=0,
        likely_match=0,
        definition_mismatch=0,
        period_basis_mismatch=0,
        unit_mismatch=0,
        value_conflict=0,
        structured_field_missing=0,
        official_field_not_found=0,
        insufficient_evidence=0,
        not_applicable=0,
        failed=0,
        fields=[],
        source_mode="artifact_seed",
        selected_fields=["revenue"],
        cache_context=dict(cache_context),
        seed_path=str(seed_path),
    )
    record = FinancialEvidenceFusionRecord(
        id=1,
        market="CN",
        symbol="600519",
        report_id=2,
        report_year=2025,
        report_type="annual",
        module="profitability",
        field_name="revenue",
        provider_name="MBRevenue",
        provider_value=1,
        provider_unit="元",
        provider_definition="main_business_revenue",
        provider_period="2025-12-31",
        provider_value_basis="annual_cumulative",
        official_value=1,
        official_unit="元",
        official_definition="营业收入",
        official_period="2025-12-31",
        official_value_basis="annual_cumulative",
        official_page=1,
        official_chunk_id=1,
        official_excerpt="营业收入 1",
        normalized_provider_value=1,
        normalized_official_value=1,
        absolute_diff=0,
        relative_diff=0,
        tolerance=0.0,
        fusion_status="verified",
        confidence=1.0,
        source_trace_json={"official": {"source_url": "https://example.com"}},
    )
    company_v2_financial_evidence_fusion_service.repository.set(snapshot, [record])
    cache_payload = company_v2_financial_evidence_fusion_service._snapshot_to_json(snapshot, [record])  # noqa: SLF001
    company_v2_financial_fusion_cache.set(cache_context["cache_key"], cache_payload)

    monkeypatch.setattr(
        company_v2_financial_evidence_fusion_service,
        "_load_structured",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("structured load must not run on warm hit")),
    )

    result = company_v2_financial_evidence_fusion_service.run(
        market="CN",
        symbol="600519",
        report_id=2,
        report_year=2025,
        report_type="annual",
        fields=["revenue"],
        refresh=False,
        sidecar_path=Path(seed_path),
        source_url="https://static.cninfo.com.cn/finalpage/2026-04-01/test.PDF",
        pdf_hash="hash",
        parse_version="parsed",
        enforce_rollout=False,
    )

    assert result["cache_hit"] is True
    assert result["summary"]["verified"] == 1
    assert result["fields"][0]["field_name"] == "revenue"
