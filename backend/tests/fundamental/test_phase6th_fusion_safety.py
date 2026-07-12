from __future__ import annotations

from pathlib import Path


_BACKEND_TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SIDECAR = _BACKEND_TESTS_ROOT / "fixtures" / "company_v2_report_1_e6a216071c389d92.pages.json"


def _fixture_sidecar() -> Path:
    assert FIXTURE_SIDECAR.exists(), f"missing test fixture sidecar: {FIXTURE_SIDECAR}"
    return FIXTURE_SIDECAR


def test_fusion_service_does_not_emit_local_path_or_investment_advice():
    from app.services.company_v2_financial_evidence_fusion_service import company_v2_financial_evidence_fusion_service

    result = company_v2_financial_evidence_fusion_service.run(
        market="CN",
        symbol="601686",
        report_id=1,
        report_year=2024,
        report_type="annual",
        fields=["net_profit"],
        refresh=True,
        sidecar_path=_fixture_sidecar(),
        source_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
    )
    payload = str(result)
    assert "local_path" not in payload
    assert "投资建议" not in payload
