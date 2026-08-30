from __future__ import annotations

from app.agent.report_chat_copilot_agent import (
    _build_canonical_validation_evidence_map,
    _build_local_evidence_context,
    _citation_metadata_leaks,
    _resolve_local_citations,
)
from app.services.report_derived_fact_service import (
    build_request_local_formula_policies,
    build_report_derived_facts,
    validate_numeric_claims_with_derived_formula_scales,
)


CANONICAL = {
    "chunk_id": 4, "report_id": 1, "report_year": 2024, "period": "2024-12-31",
    "content": (
        "单位：元 币种：人民币 2024年 2023年 "
        "营业收入 170,899,152,276.34 147,693,604,994.14 "
        "归属于上市公司股东的净 利润 86,228,146,421.62 74,734,071,550.75"
    ),
}
COMPACTED = {**CANONICAL, "content": "七、近三年主要会计数据和财务指标"}


def _facts(evidence_map=None):
    evidence_map = evidence_map or {"E1": CANONICAL}
    return build_report_derived_facts(
        question="2024年净利率", report_id=1, report_year=2024,
        chunks=[CANONICAL], evidence_map=evidence_map,
    )


def test_canonical_e1_validates_claim_when_compacted_e1_omits_numbers():
    _, model_map = _build_local_evidence_context([COMPACTED])
    canonical_map = _build_canonical_validation_evidence_map(model_map, [CANONICAL])
    claim = {"evidence_id": "E1", "claim": "2024年营业收入170,899,152,276.34元。"}
    _, audit = _resolve_local_citations([claim], canonical_map, _facts(canonical_map), report_year=2024)
    assert model_map["E1"]["content"] == COMPACTED["content"]
    assert canonical_map["E1"]["content"] == CANONICAL["content"]
    assert audit["valid"] is True


def test_fabricated_number_and_wrong_period_remain_rejected():
    evidence = {"E1": CANONICAL}
    fabricated = {"evidence_id": "E1", "claim": "2024年营业收入9999.99元。"}
    wrong_period = {"evidence_id": "E1", "claim": "2023年营业收入170,899,152,276.34元。"}
    assert _resolve_local_citations([fabricated], evidence, _facts(), report_year=2024)[1]["valid"] is False
    assert _resolve_local_citations([wrong_period], evidence, _facts(), report_year=2024)[1]["valid"] is False


def test_c1_resolves_only_from_operand_canonical_evidence():
    facts = _facts()
    citation = {"derived_fact_id": "C1", "evidence_ids": ["E1"], "claim": "2024年净利率为50.46%。"}
    assert _resolve_local_citations([citation], {"E1": CANONICAL}, facts, report_year=2024)[1]["valid"]
    missing_operand = {"E1": {**CANONICAL, "content": "2024年净利率50.46%"}}
    assert not _resolve_local_citations([citation], missing_operand, facts, report_year=2024)[1]["valid"]


def test_100_is_allowed_only_in_validated_ratio_percentage_formula_span():
    fact = _facts()[0]
    corpus = CANONICAL["content"] + " " + fact["display_result"]
    policy = build_request_local_formula_policies([fact], {"E1": CANONICAL}, ["C1"])
    valid = "2024年净利率为50.46%，即每100元营业收入对应50.46元归母净利润。"
    independent = "2024年净利率为50.46%。另有100个项目。"
    thousand = "2024年净利率为50.46%，即每1000元营业收入对应50.46元归母净利润。"
    assert validate_numeric_claims_with_derived_formula_scales(valid, corpus, policy)["valid"]
    assert not validate_numeric_claims_with_derived_formula_scales(independent, corpus, policy)["valid"]
    assert not validate_numeric_claims_with_derived_formula_scales(thousand, corpus, policy)["valid"]
    assert not validate_numeric_claims_with_derived_formula_scales(valid, corpus)["valid"]


def test_formula_policy_requires_resolved_c1_and_canonical_operands():
    fact = _facts()[0]
    assert build_request_local_formula_policies([fact], {"E1": CANONICAL}, []) == []
    assert build_request_local_formula_policies([fact], {"E1": COMPACTED}, ["C1"]) == []


def test_non_formula_constants_and_fabricated_numbers_remain_rejected():
    fact = _facts()[0]
    corpus = CANONICAL["content"] + " " + fact["display_result"]
    policy = build_request_local_formula_policies([fact], {"E1": CANONICAL}, ["C1"])
    rejected = [
        "净利率为50.46%，公司完成100%经营目标。",
        "净利率为50.46%，另有100个项目。",
        "净利率为50.46%，计算时乘以1000。",
        "净利率为50.46%，计算时乘以10000。",
        "净利率为50.46%，计算时乘以101。",
        "净利率为50.46%，完成率为99%。",
        "净利率为50.46%，营业收入为9999.99元。",
    ]
    assert all(
        not validate_numeric_claims_with_derived_formula_scales(text, corpus, policy)["valid"]
        for text in rejected
    )


def test_formula_policy_parameter_defaults_to_no_behavior_change():
    fact = _facts()[0]
    corpus = CANONICAL["content"] + " " + fact["display_result"]
    formula = "净利率=归母净利润÷营业收入×100%，结果为50.46%。"
    assert not validate_numeric_claims_with_derived_formula_scales(formula, corpus)["valid"]


def test_d3_model_and_answer_containment_does_not_regress():
    model_json, _ = _build_local_evidence_context([COMPACTED])
    assert '"chunk_id"' not in model_json
    assert "report_chunks" not in model_json
    assert _citation_metadata_leaks("净利率约为50.46%。", [4]) == []
