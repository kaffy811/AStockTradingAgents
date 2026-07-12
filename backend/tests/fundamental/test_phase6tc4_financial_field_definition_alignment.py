"""Phase 6T-C4: financial field definition alignment tests."""
from __future__ import annotations


def _guard(fields):
    from app.services.company_v2_ai_verification_guardrail import apply_ai_verification_guardrail

    return apply_ai_verification_guardrail(
        {"fields": fields, "human_review_queue": [], "non_blocking_findings": []},
        report_year=2024,
        report_type="annual",
    )


def _field(
    field: str,
    *,
    provider_definition: str,
    matched_label: str,
    official_value: float = 100.0,
    structured_value: float = 100.0,
):
    from app.services.company_v2_financial_field_definition_registry import build_field_definition_match

    return {
        field: {
            "status": "verified",
            "official_value": official_value,
            "structured_value": structured_value,
            "confidence": 1.0,
            "evidence_page": 6,
            "evidence_excerpt": matched_label or "官方字段 100",
            "structured_period": "2024-12-31",
            "provider_definition": provider_definition,
            "matched_label": matched_label,
            "field_definition_match": build_field_definition_match(field, {
                "provider_definition": provider_definition,
                "matched_label": matched_label,
            }),
        }
    }


def test_revenue_and_total_operating_revenue_not_equal():
    result = _guard(_field("revenue", provider_definition="total_operating_revenue", matched_label="营业总收入"))
    assert result["fields"]["revenue"]["status"] == "definition_mismatch"
    assert result["summary_counts"]["true_conflict_count"] == 0


def test_revenue_and_main_business_revenue_not_equal():
    result = _guard(_field("revenue", provider_definition="main_business_revenue", matched_label="主营业务收入"))
    assert result["fields"]["revenue"]["status"] == "definition_mismatch"
    assert result["fields"]["revenue"]["field_definition_match"]["match_type"] == "incompatible"


def test_net_profit_and_net_profit_parent_not_equal():
    result = _guard(_field("net_profit_parent", provider_definition="net_profit", matched_label="净利润"))
    assert result["fields"]["net_profit_parent"]["status"] == "definition_mismatch"


def test_net_profit_parent_and_excl_nonrecurring_not_equal():
    result = _guard(_field(
        "net_profit_parent",
        provider_definition="net_profit_parent_excl_nonrecurring",
        matched_label="扣非归母净利润",
    ))
    assert result["fields"]["net_profit_parent"]["status"] == "definition_mismatch"


def test_unknown_roe_not_strongly_verified_as_weighted_roe():
    result = _guard(_field("roe_weighted", provider_definition="unknown_roe", matched_label="roeAvg"))
    assert result["fields"]["roe_weighted"]["status"] == "definition_mismatch"
    assert result["summary_counts"]["true_conflict_count"] == 0


def test_exact_definition_can_be_verified():
    result = _guard(_field("revenue", provider_definition="revenue", matched_label="营业收入"))
    assert result["fields"]["revenue"]["status"] == "verified"
    assert result["summary_counts"]["verified_count"] == 1


def test_incompatible_definition_remains_definition_mismatch():
    result = _guard(_field(
        "roe_weighted",
        provider_definition="roe_diluted",
        matched_label="摊薄净资产收益率",
        official_value=0.065,
        structured_value=0.065,
    ))
    assert result["fields"]["roe_weighted"]["status"] == "definition_mismatch"


def test_definition_mismatch_does_not_create_true_conflict():
    result = _guard(_field(
        "revenue",
        provider_definition="main_business_revenue",
        matched_label="主营业务收入",
        official_value=120.0,
        structured_value=100.0,
    ))
    assert result["verification_status"] == "needs_human_review"
    assert result["summary_counts"]["true_conflict_count"] == 0


def test_no_investment_advice_wording():
    result = _guard(_field("net_profit", provider_definition="net_profit", matched_label="净利润"))
    text = str(result)
    for word in ["买入", "卖出", "目标价", "保证上涨"]:
        assert word not in text
