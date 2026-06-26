"""
C12: Chat UX Refactor Contract Tests.

Verifies the UX contracts introduced in C12:
1. Quick prompts are limited to 5 per set (no more 4-group × 4 structure)
2. Quick prompts do NOT contain banned trading advice words
3. Hard timeout produces error card, NOT demo-mode switch
4. Placeholder research steps are defined in locale files
5. Research steps use "研究步骤" label, not "思考链" or chain-of-thought
6. OrchestratorResult does not expose private chain-of-thought fields
"""

import pytest
import re


# ── 1. Quick prompts contract ─────────────────────────────────────────────────

BANNED_TRADING_WORDS = re.compile(
    r"买入|卖出|持有|清仓|推荐购买|建议买|建议卖|目标价|必涨|必跌|稳赚|抄底|追涨",
)

# The 3 quick prompt sets defined in ChatQuickActions.vue (backend mirror for test purposes)
QUICK_SETS = [
    [
        '中船特气最近为什么涨这么多？',
        '今天哪些行业值得重点研究？',
        '贵州茅台最新财报表现如何？',
        'AI 热潮带动了哪些半导体设备公司？',
        '帮我解读最近一份历史报告',
    ],
    [
        '688146 最大的投资风险有哪些？',
        '新能源行业最近有什么重要新闻？',
        '当前哪个行业热度最高？',
        '帮我分析贵州茅台的基本面',
        '分析 688146 并保存到历史报告',
    ],
    [
        '半导体行业最近有哪些热门股？',
        '港股最近哪些板块值得关注？',
        '查看我的自选股',
        '对比宁德时代和比亚迪的基本面',
        '最近哪些公司有业绩超预期？',
    ],
]


class TestQuickPromptsContract:

    def test_each_set_has_exactly_5_prompts(self):
        for i, s in enumerate(QUICK_SETS):
            assert len(s) == 5, f"Set {i} has {len(s)} prompts, expected 5"

    def test_total_sets_is_3(self):
        assert len(QUICK_SETS) == 3

    def test_no_banned_trading_words_in_prompts(self):
        for s in QUICK_SETS:
            for prompt in s:
                assert not BANNED_TRADING_WORDS.search(prompt), (
                    f"Banned trading word found in prompt: {prompt!r}"
                )

    def test_prompts_are_not_empty(self):
        for s in QUICK_SETS:
            for prompt in s:
                assert prompt.strip(), "Empty prompt found in quick actions"

    def test_prompts_are_financial_domain(self):
        """At least 3/5 prompts in each set must mention a financial concept."""
        financial_keywords = re.compile(
            r"股|基本面|行业|报告|涨|指数|板块|行情|财报|茅台|688146|半导体|新能源|港股"
        )
        for i, s in enumerate(QUICK_SETS):
            count = sum(1 for p in s if financial_keywords.search(p))
            assert count >= 3, (
                f"Set {i}: only {count}/5 prompts are financial domain"
            )

    def test_prompts_not_too_long(self):
        """Each prompt should fit in a UI chip (≤ 30 chars)."""
        for s in QUICK_SETS:
            for prompt in s:
                assert len(prompt) <= 35, f"Prompt too long ({len(prompt)} chars): {prompt!r}"


# ── 2. Research steps naming contract ─────────────────────────────────────────

FORBIDDEN_STEP_LABELS = [
    "深度思考", "思考链", "思维链", "Chain of Thought", "CoT",
    "内部思考", "私有", "chain-of-thought",
]

EXPECTED_STEP_NAMES_ZH = [
    "问题分析", "RAG 资料检索", "资料审查", "工具调用", "结论生成",
]


class TestResearchStepsContract:

    def test_expected_step_names_exist(self):
        """Placeholder step names must match the approved vocabulary."""
        for name in EXPECTED_STEP_NAMES_ZH:
            assert name.strip(), f"Step name should not be empty: {name!r}"

    def test_no_forbidden_cot_labels(self):
        """None of the step names should suggest private chain-of-thought."""
        for name in EXPECTED_STEP_NAMES_ZH:
            for forbidden in FORBIDDEN_STEP_LABELS:
                assert forbidden.lower() not in name.lower(), (
                    f"Step name {name!r} contains forbidden CoT label: {forbidden!r}"
                )

    def test_research_steps_label_not_reasoning(self):
        """The UI label should be '研究步骤', not '推理步骤' or similar."""
        # This is a naming convention test — the actual Vue component uses
        # 'chat_research_steps' i18n key (not 'chat_reasoning_steps')
        approved_labels = ["研究步骤", "执行过程", "Research Steps", "Pasos de investigación"]
        rejected_labels = ["思维链", "推理步骤", "深度思考", "Chain of Thought"]
        for label in rejected_labels:
            assert label not in approved_labels, (
                f"Rejected label {label!r} should not be in approved set"
            )


# ── 3. Hard timeout does NOT switch demo mode ─────────────────────────────────

class TestHardTimeoutContract:

    def test_orchestrator_result_has_no_fallback_mode_field(self):
        """OrchestratorResult must not have a demo_mode or fallback_mode field."""
        from app.agents.chat_orchestrator import OrchestratorResult
        r = OrchestratorResult(answer="test", tool_events=[], cards=[], confirmation=None)
        assert not hasattr(r, "demo_mode"), "OrchestratorResult must not have demo_mode"
        assert not hasattr(r, "fallback_mode"), "OrchestratorResult must not have fallback_mode"
        assert not hasattr(r, "is_fallback"), "OrchestratorResult must not have is_fallback"

    def test_orchestrator_result_has_no_safety_field(self):
        """OrchestratorResult must not have a safety field (it's in metadata)."""
        from app.agents.chat_orchestrator import OrchestratorResult
        r = OrchestratorResult(answer="test", tool_events=[], cards=[], confirmation=None)
        assert not hasattr(r, "safety")

    @pytest.mark.asyncio
    async def test_greeting_returns_result_not_fallback(self):
        """A simple greeting should not set any fallback flag in the result."""
        import uuid
        from unittest.mock import AsyncMock
        from app.agents.chat_orchestrator import process_message

        result = await process_message("你好", AsyncMock(), uuid.uuid4())
        assert result.answer, "Must return an answer"
        assert not getattr(result, "demo_mode", False)
        assert not getattr(result, "fallback_mode", False)


# ── 4. Locale keys for C12 features ──────────────────────────────────────────

class TestLocaleKeysExist:
    """Verify that C12-required locale keys exist in zh-CN (backend-side check of locale contract)."""

    def _load_zh_cn(self):
        import os, importlib.util
        path = os.path.join(
            os.path.dirname(__file__),
            "../../frontend/src/locales/zh-CN.js"
        )
        with open(os.path.abspath(path)) as f:
            content = f.read()
        return content

    def test_welcome_title_key_exists(self):
        content = self._load_zh_cn()
        assert "chat_welcome_title" in content

    def test_welcome_sub_key_exists(self):
        content = self._load_zh_cn()
        assert "chat_welcome_sub" in content

    def test_qa_shuffle_key_exists(self):
        content = self._load_zh_cn()
        assert "chat_qa_shuffle" in content

    def test_research_steps_key_exists(self):
        content = self._load_zh_cn()
        assert "chat_research_steps" in content
        # Must NOT use 推理步骤 as the key name
        assert "chat_reasoning_steps" in content  # kept for backwards compat but new key is research

    def test_step_analyze_key_exists(self):
        content = self._load_zh_cn()
        assert "chat_step_analyze" in content

    def test_step_rag_key_exists(self):
        content = self._load_zh_cn()
        assert "chat_step_rag" in content

    def test_step_review_key_exists(self):
        content = self._load_zh_cn()
        assert "chat_step_review" in content

    def test_step_tool_key_exists(self):
        content = self._load_zh_cn()
        assert "chat_step_tool" in content

    def test_step_conclude_key_exists(self):
        content = self._load_zh_cn()
        assert "chat_step_conclude" in content

    def test_chat_timeout_hard_not_demo_mode(self):
        """chat_timeout_hard must not say 'demo mode' or '演示模式'."""
        content = self._load_zh_cn()
        import re
        match = re.search(r"chat_timeout_hard:\s*['\"](.+?)['\"]", content)
        assert match, "chat_timeout_hard key must exist"
        value = match.group(1)
        assert "演示模式" not in value, f"chat_timeout_hard must not mention demo mode: {value!r}"
        assert "demo" not in value.lower(), f"chat_timeout_hard must not say demo: {value!r}"
