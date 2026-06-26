"""
C13-b: Skill Streaming Event Tests.

Tests for skill_started/skill_completed events emitted by all 6 skills:
1. StockAnomalySkill emits skill_started
2. StockAnomalySkill emits skill_completed
3. skill_completed has ok=True on success
4. skill_started payload has skill_name field
5. RiskFirstSkill emits skill_started/skill_completed
6. WatchlistReviewSkill emits skill_started/skill_completed
7. IndustryHotspotSkill emits skill_started/skill_completed
8. Skill passes event_callback to tool_registry.call()
9. Skill completes normally even if event_callback raises
10. All 6 skills emit skill_started and skill_completed
"""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agents.chat_skills.base import SkillContext


def _make_context(cb=None):
    ctx = SkillContext(
        db=AsyncMock(),
        user_id=str(uuid.uuid4()),
        event_callback=cb,
    )
    mock_result = MagicMock(ok=False, data=None, cards=[], summary="no data", tool_name="mock")
    ctx.tool_registry = MagicMock()
    ctx.tool_registry.call = AsyncMock(return_value=mock_result)
    return ctx


async def _collect_events(skill, message, ctx):
    events = []

    async def cb(event_type, payload):
        events.append((event_type, payload))

    ctx.event_callback = cb
    await skill.run(message, ctx)
    return events


class TestStockAnomalySkillEvents:

    @pytest.mark.asyncio
    async def test_emits_skill_started(self):
        """StockAnomalySkill must emit skill_started."""
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill

        skill = StockAnomalySkill()
        ctx = _make_context()
        events = await _collect_events(skill, "中船特气最近为什么涨", ctx)

        types = [e[0] for e in events]
        assert "skill_started" in types, f"Events: {types}"

    @pytest.mark.asyncio
    async def test_emits_skill_completed(self):
        """StockAnomalySkill must emit skill_completed."""
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill

        skill = StockAnomalySkill()
        ctx = _make_context()
        events = await _collect_events(skill, "688146 异动分析", ctx)

        types = [e[0] for e in events]
        assert "skill_completed" in types, f"Events: {types}"

    @pytest.mark.asyncio
    async def test_skill_completed_ok_true_on_success(self):
        """skill_completed payload must have ok=True on successful run."""
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill

        skill = StockAnomalySkill()
        ctx = _make_context()
        events = await _collect_events(skill, "688146 异动", ctx)

        completed = next((e[1] for e in events if e[0] == "skill_completed"), None)
        assert completed is not None
        assert completed["ok"] is True

    @pytest.mark.asyncio
    async def test_skill_started_has_skill_name(self):
        """skill_started payload must include skill_name field."""
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill

        skill = StockAnomalySkill()
        ctx = _make_context()
        events = await _collect_events(skill, "688146", ctx)

        started = next((e[1] for e in events if e[0] == "skill_started"), None)
        assert started is not None
        assert "skill_name" in started
        assert started["skill_name"] == "stock_anomaly_skill"


class TestRiskFirstSkillEvents:

    @pytest.mark.asyncio
    async def test_emits_skill_started_and_completed(self):
        """RiskFirstSkill must emit both skill_started and skill_completed."""
        from app.agents.chat_skills.risk_first_skill import RiskFirstSkill

        skill = RiskFirstSkill()
        ctx = _make_context()
        events = await _collect_events(skill, "最大风险是什么", ctx)

        types = [e[0] for e in events]
        assert "skill_started" in types
        assert "skill_completed" in types


class TestWatchlistReviewSkillEvents:

    @pytest.mark.asyncio
    async def test_emits_skill_started_and_completed(self):
        """WatchlistReviewSkill must emit skill_started and skill_completed."""
        from app.agents.chat_skills.watchlist_review_skill import WatchlistReviewSkill

        skill = WatchlistReviewSkill()
        ctx = _make_context()

        # Simulate empty watchlist
        empty_wl = MagicMock(ok=True, data={"count": 0, "items": []}, cards=[], tool_name="get_watchlist_tool")
        ctx.tool_registry.call = AsyncMock(return_value=empty_wl)

        events = await _collect_events(skill, "看看我的自选股", ctx)

        types = [e[0] for e in events]
        assert "skill_started" in types, f"Events: {types}"
        assert "skill_completed" in types, f"Events: {types}"

    @pytest.mark.asyncio
    async def test_emits_skill_completed_on_early_return(self):
        """WatchlistReviewSkill must emit skill_completed even on early return (empty watchlist)."""
        from app.agents.chat_skills.watchlist_review_skill import WatchlistReviewSkill

        skill = WatchlistReviewSkill()
        ctx = _make_context()

        # No watchlist data triggers early return
        no_data = MagicMock(ok=False, data=None, cards=[], tool_name="get_watchlist_tool")
        ctx.tool_registry.call = AsyncMock(return_value=no_data)

        events = await _collect_events(skill, "帮我巡检自选股", ctx)

        types = [e[0] for e in events]
        assert "skill_completed" in types, f"skill_completed missing from: {types}"


class TestIndustryHotspotSkillEvents:

    @pytest.mark.asyncio
    async def test_emits_skill_started_and_completed(self):
        """IndustryHotspotSkill must emit skill_started and skill_completed."""
        from app.agents.chat_skills.industry_hotspot_skill import IndustryHotspotSkill

        skill = IndustryHotspotSkill()
        ctx = _make_context()
        events = await _collect_events(skill, "行业热点有哪些", ctx)

        types = [e[0] for e in events]
        assert "skill_started" in types, f"Events: {types}"
        assert "skill_completed" in types, f"Events: {types}"


class TestSkillEventCallbackPassthrough:

    @pytest.mark.asyncio
    async def test_skill_passes_event_callback_to_tool_registry(self):
        """Skills must pass event_callback to tool_registry.call()."""
        from app.agents.chat_skills.industry_hotspot_skill import IndustryHotspotSkill

        received_callbacks = []

        async def fake_call(tool_name, db, event_callback=None, **kwargs):
            received_callbacks.append(event_callback)
            return MagicMock(ok=False, data=None, cards=[], tool_name=tool_name)

        async def cb(event_type, payload):
            pass

        ctx = SkillContext(db=AsyncMock(), user_id="test", event_callback=cb)
        ctx.tool_registry = MagicMock()
        ctx.tool_registry.call = fake_call

        skill = IndustryHotspotSkill()
        await skill.run("行业热点", ctx)

        assert any(c is not None for c in received_callbacks), \
            "event_callback was never passed to tool_registry.call()"

    @pytest.mark.asyncio
    async def test_skill_completes_normally_when_event_callback_raises(self):
        """Skill run() must succeed even if event_callback raises exceptions."""
        from app.agents.chat_skills.watchlist_review_skill import WatchlistReviewSkill

        async def bad_cb(event_type, payload):
            raise RuntimeError("event callback exploded")

        ctx = _make_context(bad_cb)
        empty_wl = MagicMock(ok=True, data={"count": 0, "items": []}, cards=[], tool_name="get_watchlist_tool")
        ctx.tool_registry.call = AsyncMock(return_value=empty_wl)

        skill = WatchlistReviewSkill()
        result = await skill.run("看看我的自选股", ctx)
        assert result.ok is True


class TestAllSkillsHaveEventCallback:

    @pytest.mark.asyncio
    async def test_news_catalyst_skill_emits_skill_events(self):
        """NewsCatalystSkill must emit skill_started and skill_completed."""
        from app.agents.chat_skills.news_catalyst_skill import NewsCatalystSkill

        skill = NewsCatalystSkill()
        ctx = _make_context()
        events = await _collect_events(skill, "新闻有什么影响", ctx)

        types = [e[0] for e in events]
        assert "skill_started" in types
        assert "skill_completed" in types

    @pytest.mark.asyncio
    async def test_report_explanation_skill_emits_skill_events(self):
        """ReportExplanationSkill must emit skill_started and skill_completed."""
        from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill

        skill = ReportExplanationSkill()
        ctx = _make_context()
        events = await _collect_events(skill, "解释最近报告", ctx)

        types = [e[0] for e in events]
        assert "skill_started" in types
        assert "skill_completed" in types
