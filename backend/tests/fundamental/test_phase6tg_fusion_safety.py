from __future__ import annotations

from pathlib import Path


_BACKEND_TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SIDECAR = _BACKEND_TESTS_ROOT / "fixtures" / "company_v2_report_1_e6a216071c389d92.pages.json"


def _fixture_sidecar() -> Path:
    assert FIXTURE_SIDECAR.exists(), f"missing test fixture sidecar: {FIXTURE_SIDECAR}"
    return FIXTURE_SIDECAR


def test_fusion_output_has_source_trace_and_no_advice():
    from app.services.company_v2_financial_evidence_fusion_service import company_v2_financial_evidence_fusion_service

    result = company_v2_financial_evidence_fusion_service.run(
        market="CN",
        symbol="601686",
        report_id=1,
        report_year=2024,
        report_type="annual",
        fields=["revenue", "net_profit", "total_share"],
        refresh=True,
        sidecar_path=_fixture_sidecar(),
        source_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
    )
    text = str(result)
    for word in ["买入", "卖出", "目标价", "投资建议"]:
        assert word not in text
    assert all(item["source_trace_json"]["structured"] for item in result["fields"])
    assert all(item["source_trace_json"]["official"] for item in result["fields"])


def test_fusion_conflict_is_strict_and_synthetic():
    from app.services.company_v2_financial_evidence_fusion_service import _fuse_field

    record = _fuse_field(
        symbol="601686",
        report_id=1,
        report_year=2024,
        report_type="annual",
        field_name="net_profit",
        structured={
            "value": 100.0,
            "unit": "CNY",
            "provider_definition": "net_profit",
            "provider_period": "2024-12-31",
            "value_basis": "annual_cumulative",
            "provider_name": "netProfit",
            "source_trace": {"source": "synthetic"},
        },
        official_result={
            "status": "resolved",
            "retrieval_mode": "extractor",
            "candidate": {
                "value": 200.0,
                "unit": "CNY",
                "definition": "净利润",
                "period": "2024-12-31",
                "value_basis": "annual_cumulative",
                "page": 6,
                "chunk_id": None,
                "excerpt": "净利润 200.0",
                "score": 0.95,
            },
        },
    )
    assert record.fusion_status == "value_conflict"
