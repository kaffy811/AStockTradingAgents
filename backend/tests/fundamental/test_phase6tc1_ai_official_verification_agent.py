"""
Phase 6T-C1: AI-assisted official verification agent minimal safety tests.
"""
from __future__ import annotations


def test_evidence_retriever_finds_revenue_excerpt():
    from app.services.company_v2_pdf_evidence_retriever import retrieve_candidate_excerpts

    pages = [{"page": 12, "text": "主要会计数据：营业收入 1,234.56 万元，净利润 12 万元。"}]
    result = retrieve_candidate_excerpts(pages, ["revenue"])
    assert result["revenue"]
    assert result["revenue"][0]["page"] == 12
    assert "营业收入" in result["revenue"][0]["text"]


def test_evidence_excerpt_size_limited():
    from app.services.company_v2_pdf_evidence_retriever import retrieve_candidate_excerpts

    pages = [{"page": 1, "text": "x" * 3000 + "营业收入 100 万元" + "y" * 3000}]
    result = retrieve_candidate_excerpts(pages, ["revenue"])
    assert len(result["revenue"]) == 1
    assert len(result["revenue"][0]["text"]) <= 1500


def test_evidence_retriever_limits_top_three_per_field():
    from app.services.company_v2_pdf_evidence_retriever import retrieve_candidate_excerpts

    pages = [{"page": page, "text": f"营业收入 {page} 元。"} for page in range(1, 6)]
    result = retrieve_candidate_excerpts(pages, ["revenue"])
    assert len(result["revenue"]) == 3


def test_missing_evidence_cannot_be_verified():
    from app.services.company_v2_ai_official_verification_agent import verify_with_ai

    result = verify_with_ai(
        {"report_id": 1, "source": "cninfo"},
        [{"page": 1, "text": "没有目标字段。"}],
        {"modules": {"profitability": {"history": [{"period": "2024-12-31", "revenue": 100.0}]}}},
        ["revenue"],
        2024,
        "annual",
        llm_client=None,
    )
    assert result["verification_status"] == "insufficient_evidence"
    assert result["fields"]["revenue"]["status"] == "official_field_not_found"
    assert result["fields"]["revenue"]["needs_human_review"] is False


def test_low_confidence_enters_human_review_queue():
    from app.services.company_v2_ai_verification_guardrail import apply_ai_verification_guardrail

    result = apply_ai_verification_guardrail(
        {
            "fields": {
                "revenue": {
                    "status": "verified",
                    "official_value": 100.0,
                    "structured_value": 100.0,
                    "confidence": 0.6,
                    "evidence_page": 3,
                    "evidence_excerpt": "营业收入 100 元",
                }
            },
            "human_review_queue": [],
        },
        report_year=2024,
        report_type="annual",
    )
    assert result["fields"]["revenue"]["status"] == "likely_match"
    assert result["fields"]["revenue"]["needs_human_review"] is True
    assert result["human_review_queue"]


def test_unit_scale_suspected_detected():
    from app.services.company_v2_ai_verification_guardrail import apply_ai_verification_guardrail

    result = apply_ai_verification_guardrail(
        {
            "fields": {
                "revenue": {
                    "status": "verified",
                    "official_value": 10_000.0,
                    "structured_value": 1.0,
                    "confidence": 0.95,
                    "evidence_page": 3,
                    "evidence_excerpt": "营业收入 1 万元",
                }
            }
        },
        report_year=2024,
        report_type="annual",
    )
    assert "revenue: UNIT_SCALE_SUSPECTED" in result["warnings"]
    assert result["fields"]["revenue"]["needs_human_review"] is True
    assert result["fields"]["revenue"]["status"] == "unit_scale_suspected"


def test_period_mismatch_blocks_verified():
    from app.services.company_v2_ai_verification_guardrail import apply_ai_verification_guardrail

    result = apply_ai_verification_guardrail(
        {
            "fields": {
                "revenue": {
                    "status": "verified",
                    "official_value": 100.0,
                    "structured_value": 100.0,
                    "confidence": 0.95,
                    "evidence_page": 3,
                    "evidence_excerpt": "营业收入 100 元",
                    "report_year": 2025,
                    "report_type": "annual",
                }
            }
        },
        report_year=2024,
        report_type="annual",
    )
    assert result["fields"]["revenue"]["status"] == "period_basis_mismatch"
    assert result["fields"]["revenue"]["needs_human_review"] is False


def test_ai_verify_payload_has_no_local_path_or_full_pdf_text():
    from app.services.company_v2_ai_official_verification_agent import verify_with_ai

    long_text = "营业收入 100 元。" + "x" * 5000
    result = verify_with_ai(
        {"report_id": 1, "local_path": "/tmp/secret.pdf", "source": "cninfo"},
        [{"page": 1, "text": long_text}],
        {"modules": {"profitability": {"history": [{"period": "2024-12-31", "revenue": 100.0}]}}},
        ["revenue"],
        2024,
        "annual",
        llm_client=None,
    )
    text = str(result)
    assert "local_path" not in text
    assert "/tmp/secret.pdf" not in text
    assert len(result["fields"]["revenue"]["evidence_excerpt"]) <= 1500
    assert "x" * 2000 not in text


def test_ai_verify_route_error_payload_shape_and_sanitizer():
    from app.services.company_v2_ai_verification_response import (
        build_ai_verify_error_payload,
        sanitize_ai_verification_payload,
    )

    error_payload = build_ai_verify_error_payload(
        request_id="req-1",
        report_id=1,
        report_year=2024,
        report_type="annual",
        error_code="REPORT_NOT_PARSED",
    )
    assert error_payload["request_id"] == "req-1"
    assert error_payload["report_id"] == 1
    assert error_payload["report_year"] == 2024
    assert error_payload["report_type"] == "annual"
    assert error_payload["ai_verification_status"] == "insufficient_evidence"
    assert error_payload["fields"] == {}
    assert error_payload["human_review_queue"] == []
    assert error_payload["warnings"] == []

    long_text = "营业收入 100 元。" + "x" * 5000
    sanitized = sanitize_ai_verification_payload({
        "local_path": "/tmp/secret.pdf",
        "fields": {"revenue": {"evidence_excerpt": long_text}},
        "text_pages": [{"page": 1, "text": long_text}],
    })
    assert "local_path" not in str(sanitized)
    assert "/tmp/secret.pdf" not in str(sanitized)
    assert "text_pages" not in sanitized
    assert len(sanitized["fields"]["revenue"]["evidence_excerpt"]) <= 1500
    assert "x" * 2000 not in str(sanitized)


def test_no_buy_sell_target_price_wording():
    from app.services.company_v2_ai_official_verification_agent import verify_with_ai

    result = verify_with_ai(
        {"report_id": 1, "source": "cninfo"},
        [{"page": 1, "text": "营业收入 100 元。"}],
        {"modules": {"profitability": {"history": [{"period": "2024-12-31", "revenue": 100.0}]}}},
        ["revenue"],
        2024,
        "annual",
        llm_client=None,
    )
    text = str(result)
    for word in ["买入", "卖出", "目标价", "保证上涨"]:
        assert word not in text
