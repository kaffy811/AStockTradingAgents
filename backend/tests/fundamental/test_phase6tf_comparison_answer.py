from __future__ import annotations

from .phase6te3_helpers import index_three_reports


def test_comparison_answer_contains_dual_citations_and_report_labels(tmp_path):
    from app.services.company_v2_report_comparison_answer_service import company_v2_report_comparison_answer_service

    index_three_reports(tmp_path)
    result = company_v2_report_comparison_answer_service.answer(
        symbol="601686",
        report_ids=[3, 1],
        question="比较 2023 和 2024 年营业收入变化",
        comparison_mode="generic_comparison",
        top_k_per_report=4,
    )

    assert result["status"] == "answered"
    assert result["selected_report_ids"] == [3, 1]
    assert result["cross_report_leakage_detected"] is False
    assert len(result["citations"]) >= 2
    assert any(cite["report_year"] == 2023 for cite in result["citations"])
    assert any(cite["report_year"] == 2024 for cite in result["citations"])
    assert "2023年annual" in result["answer"]
    assert "2024年annual" in result["answer"]


def test_comparison_answer_marks_period_warning_for_q3_vs_annual(tmp_path):
    from app.services.company_v2_report_comparison_answer_service import company_v2_report_comparison_answer_service

    index_three_reports(tmp_path)
    result = company_v2_report_comparison_answer_service.answer(
        symbol="601686",
        report_ids=[2, 1],
        question="比较 2024 年前三季度和全年营业收入",
        comparison_mode="generic_comparison",
        top_k_per_report=4,
    )

    assert result["status"] in {"answered", "partial"}
    assert "period_basis_warning" in result["warnings"]
    assert any(cite["report_type"] == "q3" for cite in result["citations"])


def test_comparison_answer_refuses_investment_advice_and_prediction(tmp_path):
    from app.services.company_v2_report_comparison_answer_service import company_v2_report_comparison_answer_service

    index_three_reports(tmp_path)
    result = company_v2_report_comparison_answer_service.answer(
        symbol="601686",
        report_ids=[3, 1],
        question="哪个年份更值得买，明年收入会增长多少？",
        comparison_mode="generic_comparison",
        top_k_per_report=4,
    )

    assert result["status"] == "insufficient_evidence"
    assert "investment_advice_refused" in result["warnings"]

