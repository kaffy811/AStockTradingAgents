from __future__ import annotations

import json


def _index_global(tmp_path):
    from app.services.company_v2_report_rag_index_service import (
        ReportDescriptor,
        company_v2_report_rag_index_service,
        company_v2_report_rag_repository,
    )

    company_v2_report_rag_repository.clear()
    sidecar = tmp_path / "report.pages.json"
    sidecar.write_text(
        json.dumps(
            {
                "page_count": 4,
                "parse_status": "parsed",
                "warnings": [],
                "text_pages": [
                    {"page": 12, "text": "第二节 公司简介和主要财务指标\n单位：元\n营业收入 600 亿元\n归属于上市公司股东的净利润 5 亿元"},
                    {"page": 18, "text": "经营活动产生的现金流量净额为 3 亿元，单位：元。"},
                    {"page": 30, "text": "第三节 管理层讨论与分析\n主营业务为焊接钢管研发、生产和销售。"},
                    {"page": 55, "text": "第六节 重要事项\n公司面临原材料价格波动风险、市场竞争风险。"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return company_v2_report_rag_index_service.index_report(
        ReportDescriptor(1, "CN", "601686", "友发集团", 2024, "annual", "2025-04-25", "https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF", "hash"),
        sidecar,
    )


def test_answer_requires_citation_and_is_grounded(tmp_path):
    from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service

    _index_global(tmp_path)
    result = company_v2_report_rag_answer_service.answer(report_id=1, question="公司 2024 年营业收入是多少？", symbol="601686", report_year=2024)

    assert result["status"] == "answered"
    assert result["citations"]
    assert result["citations"][0]["page"]
    assert "营业收入" in result["answer"]
    assert "local_path" not in json.dumps(result, ensure_ascii=False)


def test_answer_insufficient_evidence_for_missing_profit_guarantee(tmp_path):
    from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service

    _index_global(tmp_path)
    result = company_v2_report_rag_answer_service.answer(report_id=1, question="报告中是否提到未来利润保证？", symbol="601686", report_year=2024)

    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []


def test_answer_refuses_investment_advice(tmp_path):
    from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service

    _index_global(tmp_path)
    result = company_v2_report_rag_answer_service.answer(report_id=1, question="这只股票明天会涨吗？", symbol="601686", report_year=2024)

    assert result["status"] == "answered"
    assert "投资建议" in result["answer"] or "未来涨跌预测" in result["answer"]
    assert "investment_advice" in result["warnings"]


def test_answer_question_length_limit(tmp_path):
    from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service

    _index_global(tmp_path)
    result = company_v2_report_rag_answer_service.answer(report_id=1, question="问" * 501, symbol="601686", report_year=2024)

    assert result["status"] == "failed"
    assert "QUESTION_TOO_LONG" in result["warnings"]
