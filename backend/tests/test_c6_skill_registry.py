"""
C6 SkillRegistry — unit tests.

Tests verify:
  1. Registration and listing of 6 skills
  2. select_skill() returns the correct skill for known intents
  3. select_skill() returns None for unknown intents
  4. run() returns SkillResult
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.chat_skills.base import SkillContext, SkillResult
from app.agents.chat_skills.registry import SkillRegistry
from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
from app.agents.chat_skills.risk_first_skill import RiskFirstSkill
from app.agents.chat_skills.news_catalyst_skill import NewsCatalystSkill
from app.agents.chat_skills.watchlist_review_skill import WatchlistReviewSkill
from app.agents.chat_skills.industry_hotspot_skill import IndustryHotspotSkill
from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill


def _make_registry() -> SkillRegistry:
    sreg = SkillRegistry()
    for skill in [
        ReportExplanationSkill(),
        WatchlistReviewSkill(),
        IndustryHotspotSkill(),
        RiskFirstSkill(),
        StockAnomalySkill(),
        NewsCatalystSkill(),
    ]:
        sreg.register(skill)
    return sreg


def _make_context() -> SkillContext:
    return SkillContext(
        db=MagicMock(),
        user_id="user-test-001",
        output_language="zh-CN",
        tool_registry=MagicMock(),
    )


# ── 1. Registration ────────────────────────────────────────────────────────────

def test_registry_register_6_skills():
    sreg = _make_registry()
    assert len(sreg.list_skills()) == 6


def test_registry_sorted_by_priority():
    sreg = _make_registry()
    priorities = [s.priority for s in sreg.list_skills()]
    assert priorities == sorted(priorities)


# ── 2. select_skill — correct matches ─────────────────────────────────────────

def test_select_skill_anomaly():
    sreg = _make_registry()
    ctx = _make_context()
    skill = sreg.select_skill("中船特气最近为什么涨这么多", ctx)
    assert skill is not None
    assert isinstance(skill, StockAnomalySkill)


def test_select_skill_risk_first():
    sreg = _make_registry()
    ctx = _make_context()
    skill = sreg.select_skill("最大风险是什么", ctx)
    assert skill is not None
    assert isinstance(skill, RiskFirstSkill)


def test_select_skill_news_catalyst():
    sreg = _make_registry()
    ctx = _make_context()
    skill = sreg.select_skill("有没有实质利好", ctx)
    assert skill is not None
    assert isinstance(skill, NewsCatalystSkill)


def test_select_skill_watchlist_review():
    sreg = _make_registry()
    ctx = _make_context()
    skill = sreg.select_skill("看看我的自选股", ctx)
    assert skill is not None
    assert isinstance(skill, WatchlistReviewSkill)


def test_select_skill_industry():
    sreg = _make_registry()
    ctx = _make_context()
    skill = sreg.select_skill("哪些行业值得重点研究", ctx)
    assert skill is not None
    assert isinstance(skill, IndustryHotspotSkill)


def test_select_skill_report_explanation():
    sreg = _make_registry()
    ctx = _make_context()
    skill = sreg.select_skill("解释最近报告", ctx)
    assert skill is not None
    assert isinstance(skill, ReportExplanationSkill)


# ── 3. select_skill — None for unknown ────────────────────────────────────────

def test_select_skill_returns_none_for_unknown():
    sreg = _make_registry()
    ctx = _make_context()
    skill = sreg.select_skill("你好", ctx)
    assert skill is None


def test_select_skill_returns_none_for_generic_greeting():
    sreg = _make_registry()
    ctx = _make_context()
    skill = sreg.select_skill("帮我查一下天气", ctx)
    assert skill is None


# ── 4. run() returns SkillResult ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_returns_skill_result():
    sreg = SkillRegistry()
    mock_skill = ReportExplanationSkill()

    # Patch can_handle to always return True
    mock_skill.can_handle = lambda msg, ctx: True

    async def mock_run(msg, ctx):
        return SkillResult(
            ok=True,
            skill_name="report_explanation_skill",
            answer="报告摘要测试\n\n_仅供研究参考，不构成投资建议。_",
        )

    mock_skill.run = mock_run
    sreg.register(mock_skill)

    ctx = _make_context()
    result = await sreg.run("解释报告", ctx)
    assert result is not None
    assert isinstance(result, SkillResult)
    assert result.ok is True
    assert result.skill_name == "report_explanation_skill"


@pytest.mark.asyncio
async def test_run_returns_none_when_no_match():
    sreg = _make_registry()
    ctx = _make_context()
    result = await sreg.run("你好世界", ctx)
    assert result is None


@pytest.mark.asyncio
async def test_run_catches_skill_exception():
    sreg = SkillRegistry()
    mock_skill = StockAnomalySkill()
    mock_skill.can_handle = lambda msg, ctx: True

    async def failing_run(msg, ctx):
        raise RuntimeError("Simulated skill crash")

    mock_skill.run = failing_run
    sreg.register(mock_skill)

    ctx = _make_context()
    result = await sreg.run("中船特气", ctx)
    assert result is not None
    # C14: skill exception triggers DeepSeek fallback; error is always recorded
    assert result.error is not None  # original exception always preserved
    assert result.answer             # always returns an answer (fallback or hardcoded)
