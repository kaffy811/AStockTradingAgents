from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "phase6u_production_regression_cases.json"


class RecordingLLM:
    def __init__(self, response: str = "旧结构输出 999 强烈买入") -> None:
        self.response = response
        self.calls = 0
        self.messages = None

    def chat(self, messages, temperature=0.3, model=None):
        self.calls += 1
        self.messages = messages
        return self.response


def _load_cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _ctx(memory_context=None):
    return SimpleNamespace(
        db=SimpleNamespace(),
        user_id="u1",
        session_id="s1",
        output_language="zh-CN",
        tool_registry=SimpleNamespace(),
        event_callback=None,
        memory_context=memory_context,
    )


def _sample_sections(**overrides) -> dict[str, str]:
    sections = {
        "technical": "\n".join([
            "# 技术面",
            "## observed_facts",
            "- 2026-07-10 收盘价 100 元，短期趋势偏弱。",
            "## limitations",
            "- 技术面仅覆盖近 20 个交易日行情数据。",
        ]),
        "fundamental": "\n".join([
            "# 基本面",
            "## observed_facts",
            "- 2024 年年报营业收入 200 亿元，净利润 80 亿元，基本面改善且财务数据稳定。",
            "## limitations",
            "- 估值数据不可用，报告期为 2024-12-31。",
        ]),
        "news": "\n".join([
            "# 新闻面",
            "## observed_facts",
            "- 2026-07-12 监管新闻偏负面，可能影响市场情绪。",
            "## limitations",
            "- 新闻时间窗口为 72 小时，新闻解读存在不确定性。",
        ]),
        "peer_comparison": "\n".join([
            "# 同行对比",
            "## observed_facts",
            "- 同行样本 2 家，目标公司增长但 ROE 低于同行样本。",
            "## limitations",
            "- 同行样本来源 PEER_MAP，样本不代表完整行业。",
        ]),
    }
    sections.update(overrides)
    return sections


def _statuses(**overrides) -> dict[str, dict]:
    statuses = {
        "technical": {"status": "success", "message": None},
        "fundamental": {"status": "success", "message": None},
        "news": {"status": "success", "message": None},
        "peer_comparison": {"status": "success", "message": None},
    }
    statuses.update(overrides)
    return statuses


def _valid_report(extra: str = "") -> str:
    return f"""# 综合分析报告：贵州茅台（CN/600519）

## 综合结论
本报告分析对象为 贵州茅台（CN/600519）。基于子报告整理。

## 核心事实卡片
- 2024 年年报营业收入 200 亿元，净利润 80 亿元。

## 基本面与财务
基本面改善。

## 市场与技术
短期趋势偏弱。

## 新闻与事件
监管新闻偏负面，可能影响市场情绪。

## 同行位置
ROE 低于同行样本。

## 关键联动
中长期与短期信号不一致。

## 主要风险
新闻解读存在不确定性。

## 数据限制
估值数据不可用。

## 后续观察
继续观察后续报告期与行情数据。
{extra}
"""


def test_phase6u_production_fixture_has_30_cases_and_required_contract():
    cases = _load_cases()

    assert len(cases) == 30
    assert {case["id"] for case in cases} == set(range(1, 31))
    required_keys = {
        "expected_route",
        "expected_skill",
        "expected_agent",
        "required_tools",
        "expected_entity",
        "expected_market",
        "expected_report_context",
        "prohibited_content",
        "required_limitations",
        "expected_output_shape",
    }
    assert all(required_keys.issubset(case) for case in cases)
    assert all("skip" not in case for case in cases)


def test_phase6u_key_questions_hit_expected_main_chains():
    cases = {case["id"]: case for case in _load_cases()}

    assert all(cases[i]["expected_agent"] == "ReportChatCopilotAgent" for i in range(1, 9))
    assert cases[10]["expected_agent"] == "PeerComparisonAnalystAgent"
    assert cases[15]["expected_agent"] == "ComprehensiveAnalysisCoordinator"
    assert cases[19]["expected_agent"] == "TechnicalAnalystAgent"
    assert cases[23]["expected_agent"] == "NewsAnalystAgent"
    assert cases[30]["expected_route"] == "safety"


def test_phase6u_financial_report_questions_do_not_enter_gfa():
    for case in _load_cases()[:8]:
        assert case["expected_skill"] == "ReportExplanationSkill"
        assert case["expected_agent"] == "ReportChatCopilotAgent"
        assert case["expected_skill"] != "GeneralFinancialAnswerSkill"


def test_phase6u_technical_news_and_comparison_not_swallowed_by_gfa():
    cases = {case["id"]: case for case in _load_cases()}

    assert cases[19]["expected_agent"] == "TechnicalAnalystAgent"
    assert cases[23]["expected_agent"] == "NewsAnalystAgent"
    assert cases[10]["expected_agent"] == "PeerComparisonAnalystAgent"
    assert cases[10]["expected_skill"] == "none"
    assert "GeneralFinancialAnswerSkill" in cases[10]["prohibited_content"]


def test_phase6u_multi_turn_symbol_report_and_new_entity_context_contracts():
    cases = {case["id"]: case for case in _load_cases()}

    assert cases[9]["expected_report_context"] == "inherit_symbol_and_report_id"
    assert cases[9]["expected_entity"]["symbol"] == "600519"
    assert cases[14]["expected_report_context"] == "new_entity_overrides_old_entity"
    assert cases[14]["expected_entity"]["symbol"] == "000001"
    assert "贵州茅台" in cases[14]["prohibited_content"]


def test_phase6u_narrow_questions_keep_narrow_output_contracts():
    cases = {case["id"]: case for case in _load_cases()}

    assert "cashflow_only" in cases[3]["expected_output_shape"]
    assert "narrow_answer" in cases[4]["expected_output_shape"]
    assert "volume_narrow_question" == cases[20]["expected_report_context"]
    assert "technical_levels" in cases[21]["expected_output_shape"]


def test_phase6u_synthesis_prompt_uses_structured_summary_not_full_markdown():
    from app.agents.comprehensive_analysis_coordinator import ComprehensiveAnalysisCoordinator

    long_irrelevant = "\n".join(f"完整正文 filler {i}" for i in range(120))
    sections = _sample_sections(technical=_sample_sections()["technical"] + "\n" + long_irrelevant)
    prompt = ComprehensiveAnalysisCoordinator._build_synthesis_prompt(
        "CN", "600519", sections, "贵州茅台（CN/600519）"
    )

    assert "技术面仅覆盖近 20 个交易日行情数据" in prompt
    assert "收盘价 100 元" in prompt
    assert "完整正文 filler 119" not in prompt
    assert "证据摘要" in prompt
    assert len(prompt) <= 9500


def test_phase6u_comprehensive_report_does_not_add_unsupported_numbers():
    from app.agents.comprehensive_analysis_coordinator import _finalize_synthesis_report

    report, validation = _finalize_synthesis_report(
        _valid_report("\n新增成交额 999 亿元。"),
        _sample_sections(),
        "CN",
        "600519",
        "贵州茅台（CN/600519）",
        stock_name="贵州茅台",
    )

    assert "999" not in report
    assert "未提供数字" in report
    assert validation["unsupported_number_count"] >= 1


def test_phase6u_comprehensive_report_preserves_subreport_limitations():
    from app.agents.comprehensive_analysis_coordinator import _finalize_synthesis_report

    report = _valid_report().replace("估值数据不可用。", "本次限制见子报告。")
    finalized, validation = _finalize_synthesis_report(
        report, _sample_sections(), "CN", "600519", "贵州茅台（CN/600519）"
    )

    assert "估值数据不可用" in finalized
    assert "新闻时间窗口为 72 小时" in finalized
    assert "同行样本来源 PEER_MAP" in finalized
    assert validation["missing_limitation_count"] >= 1


def test_phase6u_subreport_conflicts_are_explicitly_marked():
    from app.agents.comprehensive_analysis_coordinator import _finalize_synthesis_report

    report, _ = _finalize_synthesis_report(
        "旧结构输出",
        _sample_sections(),
        "CN",
        "600519",
        "贵州茅台（CN/600519）",
    )

    assert "中长期与短期信号不一致" in report
    assert "财务数据稳定不覆盖新闻负面事件" in report
    assert "自身增长但低于同行样本" in report


def test_phase6u_missing_subreport_marks_partial_and_keeps_success_dimensions(monkeypatch):
    from app.agents.comprehensive_analysis_coordinator import ComprehensiveAnalysisCoordinator

    llm = RecordingLLM("旧结构输出")
    coordinator = ComprehensiveAnalysisCoordinator.__new__(ComprehensiveAnalysisCoordinator)
    coordinator._llm = llm
    sections = _sample_sections(news="[news 模块暂时不可用：provider empty]")
    statuses = _statuses(news={"status": "failed", "message": "provider empty"})
    monkeypatch.setattr(coordinator, "_run_agents_parallel", lambda market, symbol: (sections, statuses))

    result = coordinator.analyze("CN", "600519")

    assert result["metadata"]["partial"] is True
    assert "本次无可用数据" in result["report"]
    assert "营业收入 200 亿元" in result["report"]
    assert result["sections"]["fundamental"] == sections["fundamental"]


def test_phase6u_all_subreports_missing_does_not_call_synthesis_llm(monkeypatch):
    from app.agents.comprehensive_analysis_coordinator import ComprehensiveAnalysisCoordinator

    llm = RecordingLLM()
    coordinator = ComprehensiveAnalysisCoordinator.__new__(ComprehensiveAnalysisCoordinator)
    coordinator._llm = llm
    sections = {
        "technical": "",
        "fundamental": "",
        "peer_comparison": "",
        "news": "",
    }
    statuses = {
        key: {"status": "failed", "message": "empty"}
        for key in sections
    }
    monkeypatch.setattr(coordinator, "_run_agents_parallel", lambda market, symbol: (sections, statuses))

    result = coordinator.analyze("CN", "600519")

    assert llm.calls == 0
    assert result["metadata"]["partial"] is True
    assert "四个子报告均无可用数据" in result["report"]
    assert "空泛分析" not in result["report"]


def test_phase6u_safety_post_validation_removes_advice_prediction_cot_and_leaks():
    from app.agents.comprehensive_analysis_coordinator import _finalize_synthesis_report

    unsafe = _valid_report(
        "\n强烈买入，明天一定上涨。chain of thought: x。工具参数 api_key=abc。"
        "Traceback (most recent call last): /Users/kaffy/secret.py"
    )
    report, validation = _finalize_synthesis_report(
        unsafe, _sample_sections(), "CN", "600519", "贵州茅台（CN/600519）"
    )

    for forbidden in ["强烈买入", "明天一定上涨", "chain of thought", "工具参数", "api_key", "/Users/"]:
        assert forbidden not in report
    assert validation["safety_violation_count"] >= 1


def test_phase6u_source_range_check_removes_unseen_urls():
    from app.agents.comprehensive_analysis_coordinator import _finalize_synthesis_report

    report, validation = _finalize_synthesis_report(
        _valid_report("\n来源：https://example.invalid/fake"),
        _sample_sections(),
        "CN",
        "600519",
        "贵州茅台（CN/600519）",
    )

    assert "https://example.invalid/fake" not in report
    assert "来源未提供" in report
    assert validation["out_of_scope_source_count"] == 1


def test_phase6u_duplicate_paragraphs_are_removed():
    from app.agents.comprehensive_analysis_coordinator import _finalize_synthesis_report

    duplicated = _valid_report("\n\n重复段落。\n\n重复段落。")
    report, validation = _finalize_synthesis_report(
        duplicated, _sample_sections(), "CN", "600519", "贵州茅台（CN/600519）"
    )

    assert report.count("重复段落。") == 1
    assert validation["duplicate_section_count"] >= 1


def test_phase6u_symbol_name_and_title_are_corrected():
    from app.agents.comprehensive_analysis_coordinator import _finalize_synthesis_report

    wrong = _valid_report().replace("贵州茅台（CN/600519）", "宁德时代（CN/300750）")
    report, validation = _finalize_synthesis_report(
        wrong, _sample_sections(), "CN", "600519", "贵州茅台（CN/600519）", stock_name="贵州茅台"
    )

    assert report.startswith("# 综合分析报告：贵州茅台（CN/600519）")
    assert "CN/600519" in report
    assert validation["identity_corrections"] >= 1 or validation["shape_coerced"] is True


def test_phase6u_output_schema_and_frontend_fields_unchanged(monkeypatch):
    from app.agents.comprehensive_analysis_coordinator import ComprehensiveAnalysisCoordinator

    llm = RecordingLLM("旧结构输出")
    coordinator = ComprehensiveAnalysisCoordinator.__new__(ComprehensiveAnalysisCoordinator)
    coordinator._llm = llm
    sections = _sample_sections()
    monkeypatch.setattr(coordinator, "_run_agents_parallel", lambda market, symbol: (sections, _statuses()))

    result = coordinator.analyze("CN", "600519")

    assert {"market", "symbol", "report", "sections", "metadata"} <= set(result)
    assert set(result["sections"]) == {"technical", "fundamental", "peer_comparison", "news"}
    assert {"generated_at", "agents", "warnings", "partial", "synthesis_validation"} <= set(result["metadata"])
    assert result["market"] == "CN"
    assert result["symbol"] == "600519"


def test_phase6u_fixture_declares_no_buy_sell_cot_or_secret_allowed():
    cases = _load_cases()
    joined = "\n".join(
        item
        for case in cases
        for item in case["prohibited_content"]
    )

    assert "内部思考过程" in joined
    assert "secret" in joined
    assert any("买入" in item for case in cases for item in case["prohibited_content"])
    assert any("确定涨幅" in item for case in cases for item in case["prohibited_content"])


def test_phase6u_no_new_skip_markers_in_regression_test_file():
    text = Path(__file__).read_text(encoding="utf-8")
    skip_mark = "pytest.mark" + ".skip"
    skip_call = "pytest" + ".skip("
    assert not [
        line for line in text.splitlines()
        if skip_mark in line or skip_call in line
    ]
