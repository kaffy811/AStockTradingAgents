from __future__ import annotations

import json


def _pages():
    from app.services.company_v2_report_chunker import ReportPage

    return [
        ReportPage(1, "天津友发钢管集团股份有限公司2024年年度报告\n1 / 3\n第二节 公司简介和主要财务指标\n单位：元\n营业收入 60,000,000,000 元\n归属于上市公司股东的净利润 500,000,000 元"),
        ReportPage(2, "天津友发钢管集团股份有限公司2024年年度报告\n2 / 3\n第三节 管理层讨论与分析\n主营业务为焊接钢管研发、生产和销售。\n前五名客户销售额占比 12.34%。"),
        ReportPage(3, "天津友发钢管集团股份有限公司2024年年度报告\n3 / 3\n第六节 重要事项\n公司面临原材料价格波动风险、市场竞争风险。"),
    ]


def test_chunker_preserves_pages_units_and_report_scope():
    from app.services.company_v2_report_chunker import chunk_report_pages

    chunks = chunk_report_pages(
        report_id=1,
        pages=_pages(),
        metadata={"symbol": "601686", "report_year": 2024, "report_type": "annual", "source_url": "https://static.cninfo.com.cn/a.PDF", "parse_version": "v"},
        target_tokens=80,
        max_tokens=160,
        min_tokens=10,
    )

    assert chunks
    assert all(chunk.report_id == 1 for chunk in chunks)
    assert all(chunk.page_start >= 1 and chunk.page_end <= 3 for chunk in chunks)
    joined = "\n".join(chunk.text for chunk in chunks)
    assert "单位：元" in joined
    assert "60,000,000,000" in joined
    assert chunks[0].metadata_json["symbol"] == "601686"


def test_chunker_does_not_use_local_path_or_cross_report(tmp_path):
    from app.services.company_v2_report_chunker import load_pages_from_sidecar, chunk_report_pages

    sidecar = tmp_path / "report.pages.json"
    sidecar.write_text(json.dumps({"page_count": 1, "parse_status": "parsed", "text_pages": [{"page": 8, "text": "第二节 财务指标\n营业收入 1 亿元\n单位：亿元"}]}, ensure_ascii=False), encoding="utf-8")
    pages, parsed = load_pages_from_sidecar(sidecar)
    chunks = chunk_report_pages(
        report_id=88,
        pages=pages,
        metadata={"symbol": "000001", "report_year": 2024, "report_type": "annual", "source_url": "https://static.cninfo.com.cn/a.PDF", "parse_version": "v"},
        min_tokens=1,
    )

    assert parsed["parse_status"] == "parsed"
    assert chunks[0].page_start == 8
    assert chunks[0].metadata_json["symbol"] == "000001"
    assert "local_path" not in chunks[0].metadata_json


def test_chunker_splits_long_text_without_future_or_pdf_side_effects():
    from app.services.company_v2_report_chunker import ReportPage, chunk_report_pages

    long_text = "第三节 管理层讨论与分析\n" + "营业收入 净利润 现金流 单位：万元。 " * 1000
    chunks = chunk_report_pages(
        report_id=3,
        pages=[ReportPage(10, long_text)],
        metadata={"symbol": "601686", "report_year": 2024, "report_type": "annual", "source_url": "https://static.cninfo.com.cn/a.PDF", "parse_version": "v"},
        target_tokens=200,
        max_tokens=260,
        min_tokens=20,
    )

    assert len(chunks) > 1
    assert max(chunk.token_count for chunk in chunks) <= 360
    assert all(chunk.page_start == 10 for chunk in chunks)
