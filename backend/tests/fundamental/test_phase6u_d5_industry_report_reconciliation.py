from __future__ import annotations

import pytest


def test_phase6u_d5_bank_profile_excludes_generic_na_fields_from_coverage():
    from app.services.company_v2_industry_metric_applicability import (
        apply_applicability_to_coverage,
        build_module_applicability,
        infer_accounting_type,
    )

    profile = infer_accounting_type("银行", "000001")
    assert profile == "bank"
    applicability = build_module_applicability(
        "solvency",
        ["current_ratio", "quick_ratio", "cash_ratio", "debt_ratio"],
        profile,
    )
    assert set(applicability["not_applicable_fields"]) == {"current_ratio", "quick_ratio", "cash_ratio"}
    adjusted = apply_applicability_to_coverage(
        {
            "required_field_list": ["current_ratio", "quick_ratio", "cash_ratio", "debt_ratio"],
            "filled_field_list": ["debt_ratio"],
            "missing_field_map": {"current_ratio": "missing", "quick_ratio": "missing", "cash_ratio": "missing"},
        },
        applicability,
    )
    assert adjusted["required_fields"] == 1
    assert adjusted["filled_fields"] == 1
    assert adjusted["coverage_pct"] == 100.0
    assert adjusted["not_applicable_count"] == 3


def test_phase6u_d5_bank_recommended_metrics_are_declared_without_fake_values():
    from app.services.company_v2_industry_metric_applicability import get_industry_metric_profile

    profile = get_industry_metric_profile("bank")
    assert "net_interest_margin" in profile["recommended_metrics"]
    assert "non_performing_loan_ratio" in profile["recommended_metrics"]
    assert "inventory_turnover" in profile["not_applicable_rules"]


def test_phase6u_d5_roe_outlier_is_flagged_not_deleted():
    from app.datasource.history_financial_provider import _build_module_history_from_rows

    result = _build_module_history_from_rows(
        "profitability",
        [
            {"stat_date": "2021-12-31", "roe_avg": 0.08},
            {"stat_date": "2022-12-31", "roe_avg": 0.09},
            {"stat_date": "2023-12-31", "roe_avg": 11.0},
            {"stat_date": "2024-12-31", "roe_avg": 0.10},
        ],
        ts_code="601186.SH",
        start_year=2021,
        end_year=2024,
        period="annual",
        data_success=True,
    )
    assert len(result["history"]) == 4
    spike = result["history"][2]
    assert spike["roe"] == pytest.approx(11.0)
    assert any(w["code"] == "OUTLIER_REQUIRES_REVIEW" for w in spike["warnings"])
    assert result["chart_contract"]["connect_nulls"] is False


def test_phase6u_d5_report_financial_table_extractor_revenue_profit_provenance():
    from app.services.report_financial_table_extractor_tool import report_financial_table_extractor_tool

    text = """
    主要会计数据和财务指标
    2025年年度报告
    营业收入 1,746.45 亿元 上年同期 1,506.00 亿元 同比 15.97%
    归属于上市公司股东的净利润 862.28 亿元 上年同期 747.34 亿元 同比 15.38%
    经营活动产生的现金流量净额 615.22 亿元
    """
    result = report_financial_table_extractor_tool.extract_from_chunks(
        report_id=2,
        report_year=2025,
        source_document_id=2,
        chunks=[{"chunk_id": 10, "page_start": 8, "section_title": "主要会计数据和财务指标", "content": text}],
    )
    revenue = result["fields"]["revenue"]
    profit = result["fields"]["parent_net_profit"]
    assert revenue["normalized_value"] == pytest.approx(1746.45 * 1e8)
    assert profit["normalized_value"] == pytest.approx(862.28 * 1e8)
    assert revenue["source_chunk_id"] == 10
    assert revenue["table_name"] == "主要会计数据和财务指标"
    assert revenue["period_end"] == "2025-12-31"


def test_phase6u_d5_reconciliation_official_report_wins_and_flags_conflict():
    from app.services.financial_field_reconciliation_tool import financial_field_reconciliation_tool

    result = financial_field_reconciliation_tool.reconcile(
        symbol="600519.SH",
        period_end="2025-12-31",
        field="revenue",
        candidates=[
            {"field": "revenue", "normalized_value": 100.0, "unit": "元", "period_end": "2025-12-31", "source_type": "baostock_verified"},
            {"field": "revenue", "normalized_value": 120.0, "unit": "元", "period_end": "2025-12-31", "source_type": "official_report_table"},
        ],
    )
    assert result["canonical_value"] == 120.0
    assert result["source_type"] == "official_report_table"
    assert result["conflict"] is True
    assert "FIELD_CONFLICT" in result["warnings"]


def test_phase6u_d5_report_answer_guard_detects_placeholders_and_bad_tables():
    from app.agent.report_chat_copilot_agent import _answer_consistency_issues

    answer = "| 指标 | 本期 |\n| --- | --- |\n| 营收 | （营收数据需通过工具获取，此处不自行估算） | 多余 |\n\n工具仅返回新闻标题"
    issues = _answer_consistency_issues(answer, source_chunks_count=3)
    assert "PLACEHOLDER_LEAK" in issues
    assert "NEWS_ONLY_CONTRADICTION" in issues
    assert "MARKDOWN_TABLE_MISALIGNED" in issues


def test_phase6u_d5_financial_sanitizer_preserves_report_evidence_numbers():
    from app.agents.financial_safety_postprocessor import sanitize_financial_answer

    text = "营业收入约为1746.45亿元，归母净利润约为862.28亿元。"
    out = sanitize_financial_answer(
        text,
        context={
            "report_answer_owner": "report_explanation_skill",
            "verified_financial_data": True,
            "source_chunks_count": 4,
            "verified_news_detail": True,
        },
    )
    assert "需通过工具获取" not in out
    assert "工具仅返回新闻标题" not in out
    assert "1746.45亿元" in out


def test_phase6u_d5_central_planner_trace_routes_financial_report_to_agent():
    from app.agents.central_planning_agent import CentralPlanningAgent
    from app.agents.intent_decision_agent import IntentDecision

    plan = CentralPlanningAgent().create_plan(
        "贵州茅台最新财报表现如何？",
        IntentDecision(intent="direct_answer", need_agent=False, need_confirmation=False, target_entities=["贵州茅台"]),
    )
    dispatch = plan.get_agent_dispatch_event()
    planning = plan.get_phase_event("planning")
    assert "ReportChatCopilotAgent" in dispatch["content"]
    assert "无需调用专业 Agent" not in planning["content"]

