from __future__ import annotations

from .phase6te3_helpers import index_three_reports


def test_query_selected_report_only(tmp_path):
    from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service
    from app.services.company_v2_report_rag_retriever import company_v2_report_rag_retriever

    index_three_reports(tmp_path)
    annual = company_v2_report_rag_retriever.retrieve(report_id=1, question="2024年营业收入是多少？", symbol="601686", report_year=2024)
    q3 = company_v2_report_rag_retriever.retrieve(report_id=2, question="前三季度营业收入是多少？", symbol="601686", report_year=2024)
    y2023 = company_v2_report_rag_retriever.retrieve(report_id=3, question="2023年归母净利润是多少？", symbol="601686", report_year=2023)

    assert annual["retrieved_report_ids"] == [1]
    assert q3["retrieved_report_ids"] == [2]
    assert y2023["retrieved_report_ids"] == [3]
    assert not annual["cross_report_leakage_detected"]

    answer = company_v2_report_rag_answer_service.answer(report_id=1, question="2024年营业收入是多少？", symbol="601686", report_year=2024)
    assert answer["selected_report_id"] == 1
    assert answer["retrieved_report_ids"] == [1]
    assert answer["cross_report_leakage_detected"] is False


def test_wrong_year_query_does_not_fallback_to_other_report(tmp_path):
    from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service

    index_three_reports(tmp_path)
    result = company_v2_report_rag_answer_service.answer(report_id=3, question="2024年营业收入是多少？", symbol="601686", report_year=2023)

    assert result["status"] == "insufficient_evidence"
    assert "wrong_year_for_selected_report" in result["warnings"]
    assert result["retrieved_report_ids"] == []


def test_quarterly_full_year_question_does_not_use_annual_report(tmp_path):
    from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service

    index_three_reports(tmp_path)
    result = company_v2_report_rag_answer_service.answer(report_id=2, question="2024年全年净利润是多少？", symbol="601686", report_year=2024)

    assert result["status"] == "insufficient_evidence"
    assert "annual_question_on_quarterly_report" in result["warnings"]
    assert result["retrieved_report_ids"] == []


def test_investment_advice_refused_with_no_report_leakage(tmp_path):
    from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service

    index_three_reports(tmp_path)
    result = company_v2_report_rag_answer_service.answer(report_id=2, question="这只股票明天会涨吗？", symbol="601686", report_year=2024)

    assert "investment_advice" in result["warnings"]
    assert result["cross_report_leakage_detected"] is False
