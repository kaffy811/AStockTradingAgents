from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.chat_skills.base import SkillContext
from app.agents.chat_skills.report_comparison_skill import ReportComparisonSkill
from app.services.company_chat_data_service import company_chat_data_service


@pytest.mark.asyncio
async def test_company_snapshot_available_while_market_history_unavailable(monkeypatch):
    def _quote(market: str, symbol: str):
        return {"price": 73.9, "change_pct": 0.11, "turnover_rate": 1.26, "market_cap": 2868510000000}

    async def _history(*args, **kwargs):
        return {
            "generated_at": "2026-07-17",
            "stock_basic": {"name": "五粮液", "industry": "白酒"},
            "modules": {
                "profitability": {
                    "latest": {"period": "2025-12-31", "revenue": 1_000_000_000, "parent_net_profit": 200_000_000, "roe": 22.5},
                    "history": [{"period": "2025-12-31", "revenue": 1_000_000_000}],
                }
            },
        }

    import app.services.company_chat_data_service as svc

    monkeypatch.setattr(svc.stock_data_service, "get_quote_optional", _quote)
    monkeypatch.setattr(svc, "build_company_history_dashboard", _history)

    result = await company_chat_data_service.get_company_domains({"market": "CN", "symbol": "000858", "name": "五粮液"})
    assert result["availability"]["quote_snapshot"] == "available"
    assert result["availability"]["company_profile"] == "available"
    assert result["availability"]["financial_snapshot"] == "available"
    assert result["availability"]["market_history"] == "unavailable"
    assert result["financial_fields"]["revenue"]["normalized_value"] == 1_000_000_000


@pytest.mark.asyncio
async def test_comparison_uses_company_cached_data_when_report_db_unavailable(monkeypatch):
    entities = [
        {"market": "CN", "symbol": "600519", "name": "贵州茅台", "short_name": "贵州茅台"},
        {"market": "CN", "symbol": "000858", "name": "五粮液", "short_name": "五粮液"},
    ]

    async def _entities(message, context):
        return entities, {
            "comparison_parser_output": {"dimensions": ["revenue"], "entities": entities},
            "context_before": {"entities": [entities[0]]},
        }

    async def _boom(**kwargs):
        raise TimeoutError("rag database unavailable")

    async def _fallback(input_entities, **kwargs):
        return {
            "status": "partial_success",
            "entities": input_entities,
            "comparison_rows": [
                {
                    "field": "revenue",
                    "label": "营业收入",
                    "values": [
                        {"normalized_value": 100, "unit": "", "period_end": "2025-12-31", "source": "company_v2_history.profitability", "evidence_id": "a"},
                        {"normalized_value": 80, "unit": "", "period_end": "2025-12-31", "source": "company_v2_history.profitability", "evidence_id": "b"},
                    ],
                    "evidence_ids": ["a", "b"],
                }
            ],
            "availability": {
                "600519": {"financial_snapshot": "available", "market_history": "unavailable"},
                "000858": {"financial_snapshot": "available", "market_history": "unavailable"},
            },
            "warnings": [{"error_code": "RAG_DATABASE_UNAVAILABLE"}],
        }

    import app.agents.chat_skills.report_comparison_skill as module

    async def _resolve(*args, **kwargs):
        return {"entities": [], "ambiguity": False, "candidates": []}

    monkeypatch.setattr(module, "_build_comparison_entities", _entities)
    monkeypatch.setattr(module.security_entity_resolver, "resolve", _resolve)
    monkeypatch.setattr(module, "resolve_report_selection", _boom)
    monkeypatch.setattr(module.company_chat_data_service, "compare_from_company_data", _fallback)

    context = SkillContext(
        db=SimpleNamespace(),
        user_id="u1",
        memory_context=SimpleNamespace(active_entities=[]),
        metadata={"raw_query": "那它和五粮液相比呢"},
    )
    result = await ReportComparisonSkill().run("那它和五粮液相比呢", context)
    assert result.data["status"] == "partial_success"
    assert result.data["error_code"] == "RAG_DATABASE_UNAVAILABLE"
    assert "五粮液没有数据" not in result.answer
    assert "报告原文核验暂不可用" in result.answer
    assert "营业收入" in result.answer


@pytest.mark.asyncio
async def test_e1_3_1_right_company_fallback_supplies_metrics_when_rag_unavailable(monkeypatch):
    entities = [
        {"market": "CN", "symbol": "600519", "name": "贵州茅台", "short_name": "贵州茅台"},
        {"market": "CN", "symbol": "000858", "name": "五 粮 液", "short_name": "五 粮 液"},
    ]

    class _Selection:
        def __init__(self, report_id, symbol, title):
            self.ok = True
            self.report_id = report_id
            self.report_year = 2025
            self.title = title
            self.ts_code = f"{symbol}.SZ"

        def metadata(self):
            return {
                "report_id": self.report_id,
                "report_year": self.report_year,
                "title": self.title,
            }

    async def _entities(message, context):
        return entities, {
            "comparison_parser_output": {"dimensions": ["revenue"], "entities": entities},
            "context_before": {"entities": [entities[0]]},
        }

    selections = [
        _Selection(2, "600519", "贵州茅台2025年年度报告"),
        _Selection(56, "000858", "五 粮 液：2025年年度报告"),
    ]

    async def _select(**kwargs):
        return selections.pop(0)

    async def _fields(db, *, selection, query):
        if selection.report_id == 2:
            return {
                "revenue": {
                    "normalized_value": 100,
                    "unit": "",
                    "period_end": "2025-12-31",
                    "source_chunk_id": "left_revenue",
                },
                "parent_net_profit": {
                    "normalized_value": 40,
                    "unit": "",
                    "period_end": "2025-12-31",
                    "source_chunk_id": "left_profit",
                },
            }, [{"chunk_id": "left"}]
        return {}, []

    async def _fallback(input_entities, **kwargs):
        return {
            "status": "partial_success",
            "entities": input_entities,
            "domains": [
                {"entity": input_entities[0], "financial_fields": {}, "company_profile": {}, "availability": {}},
                {
                    "entity": input_entities[1],
                    "company_profile": {"name": "五粮液"},
                    "availability": {"financial_history": "available"},
                    "financial_fields": {
                        "revenue": {
                            "normalized_value": 80,
                            "unit": "",
                            "period_end": "2025-12-31",
                            "source": "company_v2_history.profitability",
                            "evidence_id": "right_revenue",
                        },
                        "parent_net_profit": {
                            "normalized_value": 30,
                            "unit": "",
                            "period_end": "2025-12-31",
                            "source": "company_v2_history.profitability",
                            "evidence_id": "right_profit",
                        },
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
    assert result.data["status"] == "partial_success"
    assert result.data["comparison_summary"]["common_metric_count"] == 2
    assert result.data["comparison_summary"]["requested_metric_count"] == 7
    assert "五 粮 液" not in result.answer
    assert "五粮液：2025年年度报告" in result.answer
    assert "结构化字段对齐：7 项" not in str(result.tool_events)
    assert "五粮液没有数据" not in result.answer
