from scripts.r33i2_strict_serial_harness import QUESTIONS, serial_gate


def test_next_request_is_blocked_until_all_four_terminal_conditions():
    assert not serial_gate(api_terminal=False, s8_persisted=True, backend_completed=True, health_ok=True)
    assert not serial_gate(api_terminal=True, s8_persisted=False, backend_completed=True, health_ok=True)
    assert not serial_gate(api_terminal=True, s8_persisted=True, backend_completed=False, health_ok=True)
    assert not serial_gate(api_terminal=True, s8_persisted=True, backend_completed=True, health_ok=False)
    assert serial_gate(api_terminal=True, s8_persisted=True, backend_completed=True, health_ok=True)


def test_q3_only_question_is_the_frozen_formula_request():
    assert QUESTIONS[1] == "请根据贵州茅台2024年营业收入和归母净利润计算并解释净利率。"
