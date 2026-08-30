from __future__ import annotations

from copy import deepcopy

from app.agents.specialist_analysis_utils import validate_numeric_claims
from app.services.report_derived_fact_service import (
    build_report_derived_facts,
    compile_derived_fact_validation_corpus,
    derived_fact_usage,
)


def _chunks() -> list[dict]:
    return [
        {
            "chunk_id": 4,
            "content": (
                "单位：元 2024年 2023年 营业收入 170,899,152,276.34 147,693,604,994.14 "
                "归属于上市公司股东的净 利润 86,228,146,421.62 74,734,071,550.75 "
                "总资产 298,944,579,918.70 272,699,660,092.25"
            ),
        },
        {
            "chunk_id": 10,
            "content": (
                "单位：元 投资活动产生的现金流量净额 -1,785,202,630.71 -9,724,414,015.16 "
                "筹资活动产生的现金流量净额 -71,067,506,484.81 -58,889,101,991.94"
            ),
        },
    ]


def _map(chunks: list[dict]) -> dict[str, dict]:
    return {"E1": chunks[0], "E2": chunks[1]}


def _build(question: str, *, structured_financial_data: dict | None = None) -> list[dict]:
    chunks = _chunks()
    return build_report_derived_facts(
        question=question,
        report_id=1,
        report_year=2024,
        chunks=chunks,
        evidence_map=_map(chunks),
        structured_financial_data=structured_financial_data,
    )


def test_net_margin_ratio_is_deterministic_and_numeric_valid():
    facts = _build("2024年贵州茅台净利率如何？")
    fact = facts[0]
    assert fact["operation"] == "ratio"
    assert fact["display_result"] == "50.46%"
    assert {item["metric"] for item in fact["operands"]} == {"net_profit", "revenue"}
    assert validate_numeric_claims("按年报披露数据计算，净利率为50.46%。", compile_derived_fact_validation_corpus(facts))["valid"]


def test_structured_financial_fields_can_generate_net_margin():
    structured = {
        "report_id": 1,
        "report_year": 2024,
        "fields": {
            "revenue": {
                "field": "revenue",
                "report_id": 1,
                "source_chunk_id": 4,
                "normalized_value": 170899152276.34,
                "unit": "元",
                "period_end": "2024-12-31",
            },
            "parent_net_profit": {
                "field": "parent_net_profit",
                "report_id": 1,
                "source_chunk_id": 4,
                "normalized_value": 86228146421.62,
                "unit": "元",
                "period_end": "2024-12-31",
            },
        },
        "extraction_method": "regex_table_text",
    }
    facts = _build("2024年贵州茅台净利率如何？", structured_financial_data=structured)
    assert facts[0]["display_result"] == "50.46%"
    assert facts[0]["operands"][0]["evidence_ids"] == ["E1"]
    assert validate_numeric_claims("按年报披露数据计算，净利率为50.46%。", compile_derived_fact_validation_corpus(facts))["valid"]


def test_investing_and_financing_differences_are_valid():
    investing = _build("2024年贵州茅台投资现金流变化如何？")
    financing = _build("2024年贵州茅台筹资现金流变化如何？")
    assert investing[0]["display_result"] == "7,939,211,384.45"
    assert financing[0]["display_result"] == "-12,178,404,492.87"
    assert validate_numeric_claims("变化额为7,939,211,384.45元。", compile_derived_fact_validation_corpus(investing))["valid"]
    assert validate_numeric_claims("变化额为-12,178,404,492.87元。", compile_derived_fact_validation_corpus(financing))["valid"]


def test_asset_difference_and_growth_are_valid():
    facts = _build("2024年贵州茅台资产与负债变化如何？")
    assert [item["operation"] for item in facts] == ["difference", "percentage_change"]
    assert facts[0]["display_result"] == "26,244,919,826.45"
    assert facts[1]["display_result"] == "9.62%"
    corpus = compile_derived_fact_validation_corpus(facts)
    assert validate_numeric_claims("资产增加26,244,919,826.45元，增长9.62%。", corpus)["valid"]


def test_model_invented_and_prior_reconstruction_remain_rejected():
    facts = _build("2024年贵州茅台净利率如何？")
    corpus = compile_derived_fact_validation_corpus(facts)
    assert not validate_numeric_claims("净利率为49.52%。", corpus)["valid"]
    assert not validate_numeric_claims("推算2023年收入约1,505.65亿元。", corpus)["valid"]


def test_period_or_unit_mismatch_cannot_be_calculated():
    chunks = _chunks()
    facts = _build("2024年贵州茅台净利率如何？")
    assert facts
    altered = deepcopy(chunks)
    altered[0]["content"] = "营业收入 170,899,152,276.34 147,693,604,994.14"
    # No directly evidenced net-profit operand means no ratio.
    assert build_report_derived_facts(question="净利率", report_id=1, report_year=2024, chunks=altered, evidence_map=_map(altered)) == []
    mismatched = deepcopy(chunks)
    mismatched[0]["report_year"] = 2023
    assert build_report_derived_facts(question="净利率", report_id=1, report_year=2024, chunks=mismatched, evidence_map=_map(mismatched)) == []


def test_wrong_rounding_is_not_compiled_or_valid():
    facts = _build("2024年贵州茅台净利率如何？")
    corpus = compile_derived_fact_validation_corpus(facts)
    assert "50.46%" in corpus
    assert not validate_numeric_claims("净利率为50.45%。", corpus)["valid"]


def test_all_operand_evidence_ids_are_preserved_and_usage_is_auditable():
    facts = _build("2024年贵州茅台净利率如何？")
    fact = facts[0]
    expected = list(dict.fromkeys(eid for operand in fact["operands"] for eid in operand["evidence_ids"]))
    assert fact["evidence_ids"] == expected == ["E1"]
    assert derived_fact_usage("净利率为50.46%。", facts) == ["C1"]


def test_d5_and_d7_are_not_admitted_by_derived_fact_corpus():
    corpus = compile_derived_fact_validation_corpus(_build("2024年贵州茅台筹资现金流变化如何？"))
    assert not validate_numeric_claims("净流出约710.68亿元。", corpus)["valid"]
    assert not validate_numeric_claims("共6条证据。", corpus)["valid"]


def test_derived_citation_requires_all_operands_and_does_not_regress_d3():
    from app.agent.report_chat_copilot_agent import (
        _citation_metadata_leaks,
        _derived_fact_label_leaks,
        _resolve_local_citations,
    )
    chunks = _chunks()
    facts = _build("2024年贵州茅台净利率如何？")
    citation = {"derived_fact_id": "C1", "evidence_ids": ["E1"], "claim": "净利率为50.46%"}
    resolved, audit = _resolve_local_citations([citation], _map(chunks), facts)
    assert audit["valid"] is True
    assert audit["resolved_derived_fact_ids"] == ["C1"]
    assert resolved[0]["chunk_id"] == 4
    bad = deepcopy(citation)
    bad["evidence_ids"] = []
    assert _resolve_local_citations([bad], _map(chunks), facts)[1]["valid"] is False
    assert _citation_metadata_leaks("按年报披露数据计算，净利率为50.46%。", [4]) == []
    assert _derived_fact_label_leaks("按年报披露数据计算，净利率为50.46%。") == []
    assert _derived_fact_label_leaks("计算结果见C1。") == ["C1"]
