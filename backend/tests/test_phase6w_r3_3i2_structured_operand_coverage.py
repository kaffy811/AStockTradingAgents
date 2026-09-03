from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.report_derived_fact_service import build_report_derived_facts
from app.services.report_local_structured_operand_supplement import (
    bind_supplement_evidence_ids,
    supplement_report_local_operands,
)


TEXT = (
    "七、近三年主要会计数据 单位：元 币种：人民币 主要会计数据 2024年 2023年 "
    "营业收入 170,899,152,276.34 147,693,604,994.14 "
    "归属于上市公司股东的净 利润 86,228,146,421.62 74,734,071,550.75"
)


class _Scalar:
    def __init__(self, values): self.values = list(values)
    def first(self): return self.values[0] if self.values else None
    def all(self): return self.values


class _Result:
    def __init__(self, values): self.values = values
    def scalars(self): return _Scalar(self.values)


class _Db:
    def __init__(self, text=TEXT):
        self.calls = 0
        self.doc = SimpleNamespace(id=7, source_url="https://static.cninfo.com.cn/report.pdf")
        self.chunk = SimpleNamespace(id=4, chunk_index=3, page_start=5, page_end=6,
                                     section_title="近三年主要会计数据", text=text)
    async def execute(self, _stmt):
        self.calls += 1
        return _Result([self.doc] if self.calls == 1 else [self.chunk])


async def _supplement(*, text=TEXT, question="2024年贵州茅台净利率如何？",
                      period="2024-12-31", structured=None):
    return await supplement_report_local_operands(
        db=_Db(text), question=question, report_id=1, report_year=2024,
        selected_period=period, structured=structured or {"fields": {}, "field_count": 0},
    )


@pytest.mark.asyncio
async def test_empty_structured_fields_are_supplemented_then_emit_net_margin():
    structured, chunks, audit = await _supplement()
    evidence_map = {"E1": chunks[0]}
    bind_supplement_evidence_ids(structured, evidence_map)
    facts = build_report_derived_facts(
        question="净利率", report_id=1, report_year=2024, chunks=chunks,
        evidence_map=evidence_map, structured_financial_data=structured,
    )
    assert audit["supplemented"] == ["revenue", "parent_net_profit"]
    assert structured["field_count"] == 2
    assert all(item["provenance_complete"] for item in structured["fields"].values())
    assert facts[0]["display_result"] == "50.46%"
    assert facts[0]["evidence_ids"] == ["E1"]


@pytest.mark.asyncio
async def test_missing_revenue_or_profit_does_not_supplement_or_emit():
    structured, chunks, audit = await _supplement(text="单位：元 币种：人民币 2024年 营业收入 10 9")
    assert chunks == [] and audit["supplemented"] == []
    assert build_report_derived_facts(question="净利率", report_id=1, report_year=2024,
                                      chunks=[], evidence_map={}, structured_financial_data=structured) == []


@pytest.mark.asyncio
async def test_different_selected_period_is_rejected():
    structured, chunks, audit = await _supplement(period="2023-12-31")
    assert chunks == [] and audit["reason"] == "selected_period_mismatch"
    assert structured["fields"] == {}


@pytest.mark.asyncio
async def test_incompatible_or_missing_unit_is_rejected():
    _, chunks, audit = await _supplement(text=TEXT.replace("单位：元", "单位：万元"))
    assert chunks == [] and audit["reason"] == "complete_same_period_unit_evidence_not_found"


@pytest.mark.asyncio
async def test_unbound_request_local_evidence_rejects_derived_fact():
    structured, chunks, _ = await _supplement()
    bind_supplement_evidence_ids(structured, {})
    facts = build_report_derived_facts(question="净利率", report_id=1, report_year=2024,
                                       chunks=chunks, evidence_map={}, structured_financial_data=structured)
    assert facts == []


@pytest.mark.asyncio
async def test_existing_operands_do_not_trigger_supplement():
    existing = {"fields": {"revenue": {}, "parent_net_profit": {}}, "field_count": 2}
    structured, chunks, audit = await _supplement(structured=existing)
    assert chunks == [] and audit["reason"] == "operands_present"
    assert structured is existing


@pytest.mark.asyncio
async def test_unrequested_ordinary_report_question_is_unchanged():
    structured, chunks, audit = await _supplement(question="2024年经营现金流表现如何？")
    assert chunks == [] and audit["reason"] == "metric_not_requested"
    assert structured["fields"] == {}
