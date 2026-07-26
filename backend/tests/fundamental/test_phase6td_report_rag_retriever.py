from __future__ import annotations

import json


def _indexed_repo(tmp_path):
    from app.services.company_v2_report_rag_index_service import CompanyV2ReportRagIndexService, CompanyV2ReportRagRepository, ReportDescriptor

    sidecar = tmp_path / "report.pages.json"
    sidecar.write_text(
        json.dumps(
            {
                "page_count": 3,
                "parse_status": "parsed",
                "warnings": [],
                "text_pages": [
                    {"page": 12, "text": "第二节 公司简介和主要财务指标\n单位：元\n营业收入 600 亿元\n归属于上市公司股东的净利润 5 亿元"},
                    {"page": 30, "text": "第三节 管理层讨论与分析\n主营业务为焊接钢管研发、生产和销售。"},
                    {"page": 55, "text": "第六节 重要事项\n公司面临原材料价格波动风险、市场竞争风险。"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    repo = CompanyV2ReportRagRepository()
    service = CompanyV2ReportRagIndexService(repo)
    service.index_report(
        ReportDescriptor(1, "CN", "601686", "友发集团", 2024, "annual", "2025-04-25", "https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF", "hash"),
        sidecar,
    )
    return repo


def test_retriever_strong_filters_report_symbol_year(tmp_path):
    from app.services.company_v2_report_rag_retriever import CompanyV2ReportRagRetriever

    retriever = CompanyV2ReportRagRetriever(_indexed_repo(tmp_path))

    ok = retriever.retrieve(report_id=1, question="营业收入是多少？", symbol="601686", report_year=2024)
    assert ok["retrieval_mode"] == "hybrid"
    assert ok["chunks"]
    assert all(chunk["report_id"] == 1 for chunk in ok["chunks"])
    assert all(chunk["symbol"] == "601686" for chunk in ok["chunks"])

    blocked = retriever.retrieve(report_id=1, question="营业收入是多少？", symbol="600519", report_year=2024)
    assert blocked["error_code"] == "REPORT_SYMBOL_MISMATCH"


def test_retriever_top_k_cap_and_no_cross_report_leakage(tmp_path):
    from app.services.company_v2_report_rag_retriever import CompanyV2ReportRagRetriever, MAX_TOP_K

    retriever = CompanyV2ReportRagRetriever(_indexed_repo(tmp_path))
    result = retriever.retrieve(report_id=1, question="风险 主营业务 营业收入 净利润", top_k=99)

    assert result["top_k"] == MAX_TOP_K
    assert len(result["chunks"]) <= MAX_TOP_K
    assert "local_path" not in json.dumps(result, ensure_ascii=False)


def test_retriever_fallback_when_report_not_indexed(tmp_path):
    from app.services.company_v2_report_rag_index_service import CompanyV2ReportRagRepository
    from app.services.company_v2_report_rag_retriever import CompanyV2ReportRagRetriever

    result = CompanyV2ReportRagRetriever(CompanyV2ReportRagRepository()).retrieve(report_id=99, question="营业收入")
    assert result["error_code"] == "REPORT_NOT_INDEXED"
    assert result["chunks"] == []
