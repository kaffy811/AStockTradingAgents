from __future__ import annotations

from .phase6te3_helpers import index_three_reports


def test_evidence_matrix_contains_report_specific_pages(tmp_path):
    from app.services.company_v2_report_comparison_evidence_builder import build_comparison_evidence_matrix
    from app.services.company_v2_report_comparison_retriever import company_v2_report_comparison_retriever

    index_three_reports(tmp_path)
    retrieval = company_v2_report_comparison_retriever.retrieve(
        symbol="601686",
        report_ids=[3, 1],
        question="比较 2023 和 2024 年营业收入变化",
        top_k_per_report=4,
    )
    matrix = build_comparison_evidence_matrix(
        selected_report_ids=[3, 1],
        per_report_results=retrieval["per_report_results"],
        question="比较 2023 和 2024 年营业收入变化",
    )

    revenue = matrix["topics"][0]
    assert revenue["topic"] == "营业收入"
    assert revenue["comparable"] is True
    assert {row["report_id"] for row in revenue["reports"]} == {1, 3}
    assert all(row["evidence_pages"] for row in revenue["reports"])
    assert revenue["reports"][0]["unit"] == "元"


def test_evidence_matrix_period_warning_for_q3_vs_annual(tmp_path):
    from app.services.company_v2_report_comparison_evidence_builder import build_comparison_evidence_matrix
    from app.services.company_v2_report_comparison_retriever import company_v2_report_comparison_retriever

    index_three_reports(tmp_path)
    retrieval = company_v2_report_comparison_retriever.retrieve(
        symbol="601686",
        report_ids=[2, 1],
        question="比较 2024 年前三季度和全年营业收入",
        top_k_per_report=4,
    )
    matrix = build_comparison_evidence_matrix(
        selected_report_ids=[2, 1],
        per_report_results=retrieval["per_report_results"],
        question="比较 2024 年前三季度和全年营业收入",
    )

    revenue = matrix["topics"][0]
    assert any(row["period_basis"] == "quarterly_cumulative" for row in revenue["reports"])

