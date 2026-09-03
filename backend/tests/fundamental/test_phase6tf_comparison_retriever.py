from __future__ import annotations

from .phase6te3_helpers import index_three_reports


def test_comparison_retriever_uses_only_selected_reports(tmp_path):
    from app.services.company_v2_report_comparison_retriever import company_v2_report_comparison_retriever

    index_three_reports(tmp_path)
    result = company_v2_report_comparison_retriever.retrieve(
        symbol="601686",
        report_ids=[3, 1],
        question="比较 2023 和 2024 年营业收入变化",
        top_k_per_report=4,
    )

    assert result["selected_report_ids"] == [3, 1]
    assert result["unexpected_report_ids"] == []
    assert result["cross_report_leakage_detected"] is False
    assert {item["report_id"] for item in result["per_report_results"]} == {1, 3}
    for item in result["per_report_results"]:
        assert item["retrieved_report_ids"] == [item["report_id"]]
        assert item["chunks"]


def test_comparison_retriever_topics_stay_report_scoped(tmp_path):
    from app.services.company_v2_report_comparison_retriever import company_v2_report_comparison_retriever

    index_three_reports(tmp_path)
    result = company_v2_report_comparison_retriever.retrieve(
        symbol="601686",
        report_ids=[2, 1],
        question="比较 2024 年前三季度和全年营业收入及主要风险变化",
        top_k_per_report=4,
    )

    assert result["selected_report_ids"] == [2, 1]
    assert result["cross_report_leakage_detected"] is False
    assert len(result["per_report_results"]) == 2
    assert all(item["report_id"] in {1, 2} for item in result["per_report_results"])

