from __future__ import annotations

from pathlib import Path


_BACKEND_TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SIDECAR = _BACKEND_TESTS_ROOT / "fixtures" / "company_v2_report_1_e6a216071c389d92.pages.json"


def _fixture_sidecar() -> Path:
    assert FIXTURE_SIDECAR.exists(), f"missing test fixture sidecar: {FIXTURE_SIDECAR}"
    return FIXTURE_SIDECAR


def test_resolver_finds_report_citations():
    from app.services.company_v2_official_financial_evidence_resolver import resolve_official_financial_evidence

    result = resolve_official_financial_evidence(
        symbol="601686",
        report_id=1,
        field_name="revenue",
        provider_definition="main_business_revenue",
        provider_period="2024-12-31",
        provider_value_basis="annual_cumulative",
        report_year=2024,
        report_type="annual",
        sidecar_path=_fixture_sidecar(),
        source_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
    )
    assert result["status"] == "resolved"
    assert result["candidate"]["page"] == 6
    assert "营业收入" in result["candidate"]["excerpt"]


def test_resolver_prefers_explicit_date_for_share_count():
    from app.services.company_v2_official_financial_evidence_resolver import resolve_official_financial_evidence

    result = resolve_official_financial_evidence(
        symbol="601686",
        report_id=1,
        field_name="total_share",
        provider_definition="total_share",
        provider_period="2024-12-31",
        provider_value_basis="point_in_time",
        report_year=2024,
        report_type="annual",
        sidecar_path=_fixture_sidecar(),
        source_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
    )
    assert result["candidate"]["period"] == "2024-12-12"
    assert result["candidate"]["page"] == 54
