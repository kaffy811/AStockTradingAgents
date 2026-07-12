"""Phase 6T-C3: AI verification semantic calibration tests."""
from __future__ import annotations


def _guard(fields):
    from app.services.company_v2_ai_verification_guardrail import apply_ai_verification_guardrail

    return apply_ai_verification_guardrail(
        {"fields": fields, "human_review_queue": [], "non_blocking_findings": []},
        report_year=2024,
        report_type="annual",
    )


def test_missing_structured_field_is_not_conflict():
    result = _guard({
        "operating_cashflow": {
            "status": "not_found",
            "official_value": 139.0,
            "structured_value": None,
            "confidence": 1.0,
            "evidence_page": 14,
            "evidence_excerpt": "经营活动产生的现金流量净额 139",
        }
    })
    field = result["fields"]["operating_cashflow"]
    assert field["status"] == "structured_field_missing"
    assert result["summary_counts"]["true_conflict_count"] == 0
    assert result["human_review_queue"] == []
    assert result["non_blocking_findings"]


def test_insufficient_evidence_is_not_conflict():
    result = _guard({
        "revenue": {
            "status": "insufficient_evidence",
            "official_value": None,
            "structured_value": 100.0,
            "confidence": 0.0,
            "evidence_page": 5,
            "evidence_excerpt": "营业收入表头不完整",
        }
    })
    assert result["fields"]["revenue"]["status"] == "insufficient_evidence"
    assert result["verification_status"] == "insufficient_evidence"
    assert result["summary_counts"]["true_conflict_count"] == 0


def test_definition_mismatch_is_not_conflict():
    result = _guard({
        "net_profit_parent": {
            "status": "mismatch",
            "official_value": 424.0,
            "structured_value": 482.0,
            "confidence": 1.0,
            "evidence_page": 6,
            "evidence_excerpt": "归属于上市公司股东的净利润 424",
            "reason": "结构化值为净利润（含少数股东）482，而归母净利润应为424。",
        }
    })
    assert result["fields"]["net_profit_parent"]["status"] == "definition_mismatch"
    assert result["summary_counts"]["true_conflict_count"] == 0
    assert result["human_review_queue"][0]["status"] == "definition_mismatch"


def test_annual_vs_current_share_capital_is_period_basis_mismatch():
    result = _guard({
        "total_share": {
            "status": "verified",
            "official_value": 100.0,
            "structured_value": 101.0,
            "confidence": 1.0,
            "evidence_page": 22,
            "evidence_excerpt": "2024年12月12日总股本 101",
            "structured_period": "current",
            "reason": "当前股本与年末股本时点不同",
        }
    })
    assert result["fields"]["total_share"]["status"] == "period_basis_mismatch"
    assert result["summary_counts"]["true_conflict_count"] == 0
    assert result["human_review_queue"] == []


def test_true_same_period_same_definition_difference_is_conflict():
    result = _guard({
        "revenue": {
            "status": "verified",
            "official_value": 120.0,
            "structured_value": 100.0,
            "confidence": 1.0,
            "evidence_page": 6,
            "evidence_excerpt": "营业收入 120",
            "structured_period": "2024-12-31",
            "field_definition_match": {"status": "matched", "canonical_name": "营业收入"},
        }
    })
    assert result["fields"]["revenue"]["status"] == "conflict"
    assert result["verification_status"] == "conflict"
    assert result["summary_counts"]["true_conflict_count"] == 1


def test_aggregate_conflict_requires_true_conflict_count():
    result = _guard({
        "revenue": {
            "status": "mismatch",
            "official_value": 120.0,
            "structured_value": 100.0,
            "confidence": 1.0,
            "evidence_page": 6,
            "evidence_excerpt": "营业收入 120",
            "reason": "结构化值为主营业务收入100，而年报披露营业收入为120。",
        },
        "net_profit": {
            "status": "verified",
            "official_value": 10.0,
            "structured_value": 10.0,
            "confidence": 1.0,
            "evidence_page": 7,
            "evidence_excerpt": "净利润 10",
        },
    })
    assert result["fields"]["revenue"]["status"] == "definition_mismatch"
    assert result["summary_counts"]["true_conflict_count"] == 0
    assert result["verification_status"] == "needs_human_review"


def test_non_blocking_findings_do_not_all_enter_human_review_queue():
    result = _guard({
        "total_assets": {
            "status": "not_found",
            "official_value": 260.0,
            "structured_value": None,
            "confidence": 1.0,
            "evidence_page": 107,
            "evidence_excerpt": "资产总计 260",
        },
        "float_share": {
            "status": "insufficient_evidence",
            "official_value": None,
            "structured_value": 100.0,
            "confidence": 0.0,
            "evidence_page": None,
            "evidence_excerpt": "",
        },
    })
    assert len(result["human_review_queue"]) == 0
    assert len(result["non_blocking_findings"]) >= 1


def test_net_profit_and_net_profit_parent_remain_distinct():
    from app.services.company_v2_financial_field_definition_registry import build_field_definition_match

    match = build_field_definition_match(
        "net_profit_parent",
        {"reason": "结构化字段为净利润（含少数股东），不是归母净利润"},
    )
    assert match["status"] == "definition_mismatch"


def test_roe_and_weighted_roe_remain_distinct():
    from app.services.company_v2_financial_field_definition_registry import build_field_definition_match

    match = build_field_definition_match("roe_weighted", {"structured_field_name": "roe"})
    assert match["status"] == "definition_mismatch"


def test_no_local_path_or_full_pdf_text():
    from app.services.company_v2_ai_verification_response import sanitize_ai_verification_payload

    payload = sanitize_ai_verification_payload({
        "local_path": "/tmp/secret.pdf",
        "fields": {"revenue": {"evidence_excerpt": "营业收入 100"}},
        "text_pages": [{"page": 1, "text": "full text"}],
    })
    text = str(payload)
    assert "local_path" not in text
    assert "/tmp/secret.pdf" not in text
    assert "text_pages" not in payload


def test_no_investment_advice_wording():
    result = _guard({
        "revenue": {
            "status": "verified",
            "official_value": 100.0,
            "structured_value": 100.0,
            "confidence": 1.0,
            "evidence_page": 1,
            "evidence_excerpt": "营业收入 100",
        }
    })
    text = str(result)
    for word in ["买入", "卖出", "目标价", "保证上涨"]:
        assert word not in text
