from __future__ import annotations

from .phase6te3_helpers import index_three_reports


def test_comparison_refuses_future_prediction_and_investment_advice(tmp_path):
    from app.services.company_v2_report_comparison_answer_service import company_v2_report_comparison_answer_service

    index_three_reports(tmp_path)
    result = company_v2_report_comparison_answer_service.answer(
        symbol="601686",
        report_ids=[3, 1],
        question="明年收入会增长多少，哪个年份更值得买？",
        comparison_mode="generic_comparison",
        top_k_per_report=4,
    )

    assert result["status"] == "insufficient_evidence"
    assert "investment_advice_refused" in result["warnings"]
    assert result["cross_report_leakage_detected"] is False


def test_comparison_ignores_unselected_reports_and_keeps_isolation(tmp_path):
    from app.services.company_v2_report_comparison_answer_service import company_v2_report_comparison_answer_service

    index_three_reports(tmp_path)
    result = company_v2_report_comparison_answer_service.answer(
        symbol="601686",
        report_ids=[3, 1],
        question="比较 2023 和 2024 年营业收入变化",
        comparison_mode="generic_comparison",
        top_k_per_report=4,
    )

    assert result["selected_report_ids"] == [3, 1]
    assert all(cite["report_id"] in {1, 3} for cite in result["citations"])
    assert result["cross_report_leakage_detected"] is False

