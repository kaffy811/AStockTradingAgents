from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.chat_skills.base import SkillContext
from app.agents.chat_skills.report_comparison_skill import ReportComparisonSkill
from app.services.financial_metric_comparability import (
    financial_metric_comparability_service,
    metric_normalizer,
)
from app.services.company_chat_data_service import company_chat_data_service


def test_e1_3_2_ratio_0_07_normalizes_to_7_percent():
    item = {
        "field": "roe",
        "raw_value": 0.07,
        "source": "company_v2_history.dupont",
        "source_key": "dupont_roe",
        "period_end": "2025-12-31",
    }
    normalized = metric_normalizer.normalize(item, "roe")
    assert normalized["raw_unit"] == "ratio"
    assert normalized["normalized_value"] == pytest.approx(7.0)
    assert normalized["normalized_unit"] == "percent"
    assert normalized["validation_status"] in {"verified", "normalized"}


def test_e1_3_2_percent_7_stays_7_percent():
    item = {
        "field": "roe",
        "raw_value": 7,
        "unit": "%",
        "source": "official_report_field",
        "period_end": "2025-12-31",
    }
    normalized = metric_normalizer.normalize(item, "roe")
    assert normalized["raw_unit"] == "percent"
    assert normalized["normalized_value"] == pytest.approx(7.0)
    assert normalized["normalized_unit"] == "percent"


def test_e1_3_2_unknown_percent_unit_is_unverified():
    item = {
        "field": "roe",
        "raw_value": 0.07,
        "source": "external_unknown",
        "period_end": "2025-12-31",
    }
    normalized = metric_normalizer.normalize(item, "roe")
    assert normalized["validation_status"] == "unverified"
    assert "UNIT_UNKNOWN" in normalized["warnings"]


def test_e1_3_2_annual_vs_semiannual_revenue_not_comparable():
    left = metric_normalizer.normalize({
        "field": "revenue",
        "raw_value": 1688.38,
        "raw_unit": "亿元",
        "source": "official_report_field",
        "period_end": "2025-12-31",
    }, "revenue")
    right = metric_normalizer.normalize({
        "field": "revenue",
        "raw_value": 405.29,
        "raw_unit": "亿元",
        "source": "company_v2_history.profitability",
        "period_end": "2025-06-30",
        "period_type": "semi_annual",
    }, "revenue")
    result = financial_metric_comparability_service.compare(left, right)
    assert result["comparable"] is False
    assert "PERIOD_TYPE_MISMATCH" in result["reason_codes"]


def test_e1_3_2_point_in_time_assets_date_mismatch_not_comparable():
    left = metric_normalizer.normalize({
        "field": "total_assets",
        "raw_value": 1,
        "raw_unit": "亿元",
        "source": "official_report_field",
        "period_end": "2025-12-31",
    }, "total_assets")
    right = metric_normalizer.normalize({
        "field": "total_assets",
        "raw_value": 1,
        "raw_unit": "亿元",
        "source": "official_report_field",
        "period_end": "2025-09-30",
    }, "total_assets")
    result = financial_metric_comparability_service.compare(left, right)
    assert result["comparable"] is False
    assert "PERIOD_END_MISMATCH" in result["reason_codes"]


@pytest.mark.asyncio
async def test_e1_3_2_non_null_mismatched_metrics_not_counted(monkeypatch):
    entities = [
        {"market": "CN", "symbol": "600519", "name": "贵州茅台", "short_name": "贵州茅台"},
        {"market": "CN", "symbol": "000858", "name": "五粮液", "short_name": "五粮液"},
    ]

    class _Selection:
        ok = True
        report_year = 2025
        title = "2025年年度报告"
        ts_code = "000000.SZ"

        def __init__(self, report_id):
            self.report_id = report_id

        def metadata(self):
            return {"report_id": self.report_id, "report_year": 2025, "title": self.title}

    async def _entities(message, context):
        return entities, {
            "comparison_parser_output": {"dimensions": ["revenue"], "entities": entities},
            "context_before": {"entities": [entities[0]]},
        }

    selections = [_Selection(2), _Selection(56)]

    async def _select(**kwargs):
        return selections.pop(0)

    async def _fields(db, *, selection, query):
        return {}, []

    async def _fallback(input_entities, **kwargs):
        return {
            "status": "partial_success",
            "entities": input_entities,
            "domains": [
                {
                    "entity": input_entities[0],
                    "company_profile": {"name": "贵州茅台"},
                    "availability": {"financial_history": "available"},
                    "financial_fields": {
                        "revenue": metric_normalizer.normalize({
                            "field": "revenue",
                            "raw_value": 1688.38,
                            "raw_unit": "亿元",
                            "period_end": "2025-12-31",
                            "source": "official_report_field",
                            "evidence_id": "left",
                        }, "revenue")
                    },
                },
                {
                    "entity": input_entities[1],
                    "company_profile": {"name": "五粮液"},
                    "availability": {"financial_history": "available"},
                    "financial_fields": {
                        "revenue": metric_normalizer.normalize({
                            "field": "revenue",
                            "raw_value": 405.29,
                            "raw_unit": "亿元",
                            "period_end": "2025-06-30",
                            "period_type": "semi_annual",
                            "source": "company_v2_history.profitability",
                            "evidence_id": "right",
                        }, "revenue")
                    },
                },
            ],
            "comparison_rows": [],
            "availability": {},
            "comparison_summary": {},
            "warnings": [],
        }

    import app.agents.chat_skills.report_comparison_skill as module

    async def _resolve(*args, **kwargs):
        return {"entities": [], "ambiguity": False, "candidates": []}

    monkeypatch.setattr(module, "_build_comparison_entities", _entities)
    monkeypatch.setattr(module.security_entity_resolver, "resolve", _resolve)
    monkeypatch.setattr(module, "resolve_report_selection", _select)
    monkeypatch.setattr(module, "_structured_fields_for_report", _fields)
    monkeypatch.setattr(module.company_chat_data_service, "compare_from_company_data", _fallback)

    context = SkillContext(db=SimpleNamespace(), user_id="u1", memory_context=SimpleNamespace(active_entities=[]), metadata={"raw_query": "那它和五粮液相比呢"})
    result = await ReportComparisonSkill().run("那它和五粮液相比呢", context)
    summary = result.data["comparison_summary"]
    assert summary["candidate_common_count"] == 1
    assert summary["verified_common_count"] == 0
    assert summary["common_metric_count"] == 0
    assert summary["excluded_metrics"][0]["metric"] == "revenue"
    assert "2025年中报口径" in result.answer
    assert "暂时无法形成可靠的年度横向比较" in result.answer
    assert "盈利能力更强" not in result.answer


@pytest.mark.asyncio
async def test_e1_3_3_annual_request_does_not_return_latest_semiannual(monkeypatch):
    async def _history(*args, **kwargs):
        return {
            "generated_at": "2026-07-17",
            "stock_basic": {"name": "测试公司"},
            "modules": {
                "profitability": {
                    "period_type": "quarterly",
                    "latest": {"period": "2025-06-30", "revenue": 405.29, "report_period_type": "semi_annual"},
                    "history": [{"period": "2025-06-30", "revenue": 405.29, "report_period_type": "semi_annual"}],
                }
            },
        }

    import app.services.company_chat_data_service as svc

    monkeypatch.setattr(svc.stock_data_service, "get_quote_optional", lambda *a, **k: None)
    monkeypatch.setattr(svc, "build_company_history_dashboard", _history)
    result = await company_chat_data_service.get_financial_metrics(
        {"market": "CN", "symbol": "000858", "name": "测试公司"},
        ["revenue"],
        target_period_type="annual",
        target_report_year=2025,
        allow_fallback=False,
    )
    assert "revenue" not in result["financial_fields"]
    assert result["unavailable_metrics"]["revenue"]["selection_reason"] == "no_target_period_match"


@pytest.mark.asyncio
async def test_e1_3_3_latest_snapshot_may_return_interim_with_period(monkeypatch):
    async def _history(*args, **kwargs):
        return {
            "generated_at": "2026-07-17",
            "stock_basic": {"name": "测试公司"},
            "modules": {
                "profitability": {
                    "period_type": "quarterly",
                    "latest": {"period": "2025-06-30", "revenue": 405.29, "report_period_type": "semi_annual"},
                    "history": [{"period": "2025-06-30", "revenue": 405.29, "report_period_type": "semi_annual"}],
                }
            },
        }

    import app.services.company_chat_data_service as svc

    monkeypatch.setattr(svc.stock_data_service, "get_quote_optional", lambda *a, **k: None)
    monkeypatch.setattr(svc, "build_company_history_dashboard", _history)
    result = await company_chat_data_service.get_financial_metrics(
        {"market": "CN", "symbol": "000858", "name": "测试公司"},
        ["revenue"],
        target_period_type=None,
        target_report_year=None,
        allow_fallback=True,
    )
    item = result["financial_fields"]["revenue"]
    assert item["period_end"] == "2025-06-30"
    assert item["period_type"] == "semi_annual"
    assert item["selection_reason"] == "latest_available_unverified"
    assert item["validation_status"] == "unverified"
