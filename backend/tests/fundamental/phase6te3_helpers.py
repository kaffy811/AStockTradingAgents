from __future__ import annotations

import json


def descriptor(report_id: int, year: int, report_type: str, title: str):
    from app.services.company_v2_report_rag_index_service import ReportDescriptor

    return ReportDescriptor(
        report_id=report_id,
        market="CN",
        symbol="601686",
        company_name="友发集团",
        report_year=year,
        report_type=report_type,
        announcement_date=f"{year + 1}-04-25" if report_type == "annual" else f"{year}-10-25",
        source_url="https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF",
        pdf_hash=f"hash-{report_id}-{year}-{report_type}",
        report_title=title,
    )


def sidecar(tmp_path, report_id: int, year: int, report_type: str):
    if year == 2024 and report_type == "annual":
        pages = [
            {"page": 6, "text": "第二节 公司简介和主要财务指标\n单位：元\n2024年 营业收入 54,822,111,649.52 元\n归属于上市公司股东的净利润 424,777,342.95 元\n" + "主要会计数据 " * 80},
            {"page": 55, "text": "第六节 重要事项\n公司披露的主要风险包括信用风险、流动性风险、汇率风险。\n" + "风险因素 " * 80},
        ]
    elif year == 2024 and report_type == "q3":
        pages = [
            {"page": 3, "text": "2024年第三季度报告\n单位：元\n前三季度营业收入 40,070,365,000.00 元\n归属于上市公司股东的净利润 100,454,098.23 元\n" + "三季度主要财务数据 " * 80},
            {"page": 5, "text": "经营活动产生的现金流量净额 1,893,199,946.67 元，本期经营现金流同比改善。\n" + "现金流情况 " * 80},
        ]
    else:
        pages = [
            {"page": 6, "text": "2023年年度报告\n单位：元\n营业收入 60,918,218,181.36 元\n归属于上市公司股东的净利润 569,870,421.14 元\n" + "2023主要会计数据 " * 80},
            {"page": 30, "text": "公司主营业务为焊接钢管研发、生产和销售，主要产品包括直缝焊管、镀锌管、方矩管。\n" + "主营业务 " * 80},
        ]
    path = tmp_path / f"report_{report_id}.pages.json"
    path.write_text(json.dumps({"page_count": len(pages), "parse_status": "parsed", "warnings": [], "text_pages": pages}, ensure_ascii=False), encoding="utf-8")
    return path


def index_three_reports(tmp_path):
    from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
    from app.services.company_v2_report_rag_index_queue import company_v2_report_rag_index_queue
    from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository

    company_v2_report_rag_repository.clear()
    company_v2_report_rag_index_queue.clear()
    reports = [
        (1, 2024, "annual", "友发集团2024年年度报告"),
        (2, 2024, "q3", "友发集团2024年第三季度报告"),
        (3, 2023, "annual", "友发集团2023年年度报告"),
    ]
    results = []
    for report_id, year, report_type, title in reports:
        results.append(company_v2_report_rag_index_manager.create_index(descriptor(report_id, year, report_type, title), sidecar(tmp_path, report_id, year, report_type)))
    return results
