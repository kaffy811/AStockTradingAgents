from __future__ import annotations

from pathlib import Path


_BACKEND_TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SIDECAR = _BACKEND_TESTS_ROOT / "fixtures" / "company_v2_report_1_e6a216071c389d92.pages.json"


def _fixture_sidecar() -> Path:
    assert FIXTURE_SIDECAR.exists(), f"missing test fixture sidecar: {FIXTURE_SIDECAR}"
    return FIXTURE_SIDECAR


def test_fusion_service_returns_expected_601686_mix():
    from app.services.company_v2_financial_evidence_fusion_service import company_v2_financial_evidence_fusion_service

    result = company_v2_financial_evidence_fusion_service.run(
        market="CN",
        symbol="601686",
        report_id=1,
        report_year=2024,
        report_type="annual",
        fields=[
            "revenue",
            "net_profit",
            "net_profit_parent",
            "operating_cashflow",
            "total_assets",
            "equity_parent",
            "eps_basic",
            "roe_weighted",
            "total_share",
            "float_share",
        ],
        refresh=True,
        sidecar_path=_fixture_sidecar(),
        source_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
    )

    statuses = {item["field_name"]: item["fusion_status"] for item in result["fields"]}
    assert result["summary"]["fields_total"] == 10
    assert statuses["revenue"] == "definition_mismatch"
    assert statuses["net_profit"] == "verified"
    assert statuses["net_profit_parent"] == "definition_mismatch"
    assert statuses["operating_cashflow"] == "structured_field_missing"
    assert statuses["total_assets"] == "structured_field_missing"
    assert statuses["equity_parent"] == "structured_field_missing"
    assert statuses["eps_basic"] == "structured_field_missing"
    assert statuses["roe_weighted"] == "definition_mismatch"
    assert statuses["total_share"] == "period_basis_mismatch"
    assert statuses["float_share"] == "insufficient_evidence"


def test_fusion_service_supports_normalized_match():
    from app.services.company_v2_financial_evidence_fusion_service import _fuse_field

    record = _fuse_field(
        symbol="601686",
        report_id=1,
        report_year=2024,
        report_type="annual",
        field_name="revenue",
        structured={
            "value": 12.5,
            "unit": "万元",
            "provider_definition": "revenue",
            "provider_period": "2024-12-31",
            "value_basis": "annual_cumulative",
            "provider_name": "MBRevenue",
            "source_trace": {"source": "synthetic"},
        },
        official_result={
            "status": "resolved",
            "retrieval_mode": "extractor",
            "candidate": {
                "value": 125000.0,
                "unit": "元",
                "definition": "营业收入",
                "period": "2024-12-31",
                "value_basis": "annual_cumulative",
                "page": 6,
                "chunk_id": None,
                "excerpt": "营业收入 125000.0 元",
                "score": 0.9,
            },
        },
    )

    assert record.fusion_status == "normalized_match"
    assert record.normalized_provider_value == 125000.0
    assert record.normalized_official_value == 125000.0
