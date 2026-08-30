"""Frozen R3.3I.2.2 diagnostics; intentionally no production behavior changes."""
from app.agents.specialist_analysis_utils import validate_numeric_claims
from app.services.report_derived_fact_service import compile_derived_fact_validation_corpus


DERIVED_FACT = {
    "derived_fact_id": "C1",
    "evidence_ids": ["E1"],
    "validation_tokens": ["50.45557293472765140003363394", "50.46%"],
}
Q3_DIRECT_CLAIM = (
    "年报主要会计数据中列示2024年营业收入170,899,152,276.34元、"
    "归母净利润86,228,146,421.62元。"
)
Q3_DERIVED_CLAIM = "按归母净利润除以营业收入计算，2024年净利率为50.46%。"
Q3_ANSWER_SENTENCE = (
    "按‘归母净利润÷营业收入’计算，2024年净利率约为50.46%，"
    "即每100元营业收入对应约50.46元归母净利润。"
    "50.46%表明每实现100元营业收入形成约50.46元归母净利润。"
)


def test_frozen_q3_claims_fail_before_full_answer_numeric_gate():
    # Q3 E1 model-visible content was compacted to the heading area and did
    # not retain the operand values or 2024 token used by the submitted claims.
    compacted_e1 = "七、近三年主要会计数据和财务指标"
    direct = validate_numeric_claims(Q3_DIRECT_CLAIM, compacted_e1)
    derived = validate_numeric_claims(
        Q3_DERIVED_CLAIM,
        compacted_e1 + " " + compile_derived_fact_validation_corpus([DERIVED_FACT]),
    )
    assert direct["unsupported_tokens"] == [
        "2024", "170,899,152,276.34", "86,228,146,421.62"
    ]
    assert derived["unsupported_tokens"] == ["2024"]


def test_q1_q2_supported_claim_shape_differs_from_q3_and_q3_adds_100():
    supported_evidence = (
        "2024 170,899,152,276.34 86,228,146,421.62 "
        + compile_derived_fact_validation_corpus([DERIVED_FACT])
    )
    assert validate_numeric_claims(Q3_DIRECT_CLAIM, supported_evidence)["valid"]
    assert validate_numeric_claims(Q3_DERIVED_CLAIM, supported_evidence)["valid"]
    q3_full = validate_numeric_claims(Q3_ANSWER_SENTENCE, supported_evidence)
    assert q3_full["unsupported_tokens"] == ["100", "100"]


def _serial_gate(*, api_terminal: bool, s8_persisted: bool,
                 backend_completed: bool, health_ok: bool) -> bool:
    return api_terminal and s8_persisted and backend_completed and health_ok


def test_diagnostic_harness_gate_blocks_next_launch_before_s8_and_backend_completion():
    assert not _serial_gate(api_terminal=False, s8_persisted=False,
                            backend_completed=False, health_ok=True)
    assert not _serial_gate(api_terminal=True, s8_persisted=False,
                            backend_completed=False, health_ok=True)
    assert not _serial_gate(api_terminal=True, s8_persisted=True,
                            backend_completed=False, health_ok=True)
    assert _serial_gate(api_terminal=True, s8_persisted=True,
                        backend_completed=True, health_ok=True)
