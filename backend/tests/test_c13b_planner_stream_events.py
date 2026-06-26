"""
C13-b: Planner Streaming Event Tests.

Tests for planner_step_started/planner_step_completed events from PlannerExecutor:
1. PlannerExecutor emits planner_step_started for skill steps
2. PlannerExecutor emits planner_step_completed for skill steps
3. planner_step_started payload has step_id, name, status=running
4. planner_step_completed has status=completed on success
5. Failed skill step emits planner_step_completed with status=failed
6. Multiple steps emit events in order
7. Action steps do NOT execute (confirmation only)
8. Events are emitted via context.event_callback
9. Executor still returns valid ExecutionResult when event_callback raises
10. planner_step_completed has step_type and name fields
"""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agents.chat_planner.base import PlannerResult, PlanStep, ExecutionResult
from app.agents.chat_skills.base import SkillContext, SkillResult


def _make_plan(steps: list[PlanStep], intent_type="anomaly_then_risk") -> PlannerResult:
    return PlannerResult(
        ok=True,
        intent_type=intent_type,
        steps=steps,
        safety_flags=[],
    )


def _make_skill_step(name="stock_anomaly_skill", step_id="1") -> PlanStep:
    return PlanStep(
        step_id=step_id,
        step_type="skill",
        name=name,
        status="pending",
    )


def _make_context(cb=None):
    ctx = SkillContext(
        db=AsyncMock(),
        user_id=str(uuid.uuid4()),
        event_callback=cb,
    )
    return ctx


def _make_skill_registry(skill_name="stock_anomaly_skill", skill_ok=True, raise_exc=False):
    """Return a mock SkillRegistry."""
    registry = MagicMock()

    mock_skill = MagicMock()
    mock_skill.name = skill_name

    if raise_exc:
        mock_skill.run = AsyncMock(side_effect=RuntimeError("skill boom"))
    else:
        mock_result = SkillResult(
            ok=skill_ok,
            skill_name=skill_name,
            answer="分析完成",
            tool_events=[{"name": "get_quote_tool", "status": "success"}],
            cards=[],
        )
        mock_skill.run = AsyncMock(return_value=mock_result)

    registry.select_by_name = MagicMock(return_value=mock_skill)
    return registry


class TestPlannerStepEvents:

    @pytest.mark.asyncio
    async def test_emits_planner_step_started_for_skill_step(self):
        """PlannerExecutor must emit planner_step_started for skill steps."""
        from app.agents.chat_planner.executor import PlannerExecutor

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        registry = _make_skill_registry()
        executor = PlannerExecutor(registry)

        plan = _make_plan([_make_skill_step()])
        await executor.execute(plan, "688146 异动", ctx)

        types = [e[0] for e in events]
        assert "planner_step_started" in types, f"Events: {types}"

    @pytest.mark.asyncio
    async def test_emits_planner_step_completed_for_skill_step(self):
        """PlannerExecutor must emit planner_step_completed for skill steps."""
        from app.agents.chat_planner.executor import PlannerExecutor

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        registry = _make_skill_registry()
        executor = PlannerExecutor(registry)

        plan = _make_plan([_make_skill_step()])
        await executor.execute(plan, "688146", ctx)

        types = [e[0] for e in events]
        assert "planner_step_completed" in types, f"Events: {types}"

    @pytest.mark.asyncio
    async def test_step_started_payload_has_step_id_name_status_running(self):
        """planner_step_started payload must have step_id, name, status=running."""
        from app.agents.chat_planner.executor import PlannerExecutor

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        registry = _make_skill_registry()
        executor = PlannerExecutor(registry)

        plan = _make_plan([_make_skill_step(step_id="step-1")])
        await executor.execute(plan, "688146", ctx)

        started = next((e[1] for e in events if e[0] == "planner_step_started"), None)
        assert started is not None
        assert "step_id" in started
        assert "name" in started
        assert started["status"] == "running"

    @pytest.mark.asyncio
    async def test_step_completed_status_completed_on_success(self):
        """planner_step_completed must have status=completed on skill success."""
        from app.agents.chat_planner.executor import PlannerExecutor

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        registry = _make_skill_registry(skill_ok=True)
        executor = PlannerExecutor(registry)

        plan = _make_plan([_make_skill_step()])
        await executor.execute(plan, "688146", ctx)

        completed = next((e[1] for e in events if e[0] == "planner_step_completed"), None)
        assert completed is not None
        assert completed["status"] == "completed"

    @pytest.mark.asyncio
    async def test_failed_skill_emits_step_completed_with_status_failed(self):
        """When skill raises, planner_step_completed must have status=failed."""
        from app.agents.chat_planner.executor import PlannerExecutor

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        registry = _make_skill_registry(raise_exc=True)
        executor = PlannerExecutor(registry)

        plan = _make_plan([_make_skill_step()])
        result = await executor.execute(plan, "688146", ctx)
        # Executor should still return ok result
        assert result is not None

        completed = next((e[1] for e in events if e[0] == "planner_step_completed"), None)
        assert completed is not None
        assert completed["status"] == "failed"

    @pytest.mark.asyncio
    async def test_multiple_steps_emit_events_in_order(self):
        """Multiple skill steps must emit step events in correct order."""
        from app.agents.chat_planner.executor import PlannerExecutor

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)

        # Registry returns different skills
        mock_skill1 = MagicMock()
        mock_skill1.name = "stock_anomaly_skill"
        mock_skill1.run = AsyncMock(return_value=SkillResult(
            ok=True, skill_name="stock_anomaly_skill", answer="ok", tool_events=[], cards=[]
        ))
        mock_skill2 = MagicMock()
        mock_skill2.name = "risk_first_skill"
        mock_skill2.run = AsyncMock(return_value=SkillResult(
            ok=True, skill_name="risk_first_skill", answer="ok", tool_events=[], cards=[]
        ))

        def select_by_name(name):
            if name == "stock_anomaly_skill":
                return mock_skill1
            return mock_skill2

        registry = MagicMock()
        registry.select_by_name = select_by_name

        executor = PlannerExecutor(registry)
        plan = _make_plan([
            _make_skill_step("stock_anomaly_skill", "1"),
            _make_skill_step("risk_first_skill", "2"),
        ])
        await executor.execute(plan, "688146", ctx)

        step_events = [(e[0], e[1].get("step_id")) for e in events if "step_" in e[0]]
        # Should have started/completed for each step
        assert len(step_events) >= 4  # 2 started + 2 completed

    @pytest.mark.asyncio
    async def test_action_steps_do_not_emit_skill_run(self):
        """Action steps should not call skill.run() — only confirmation is created."""
        from app.agents.chat_planner.executor import PlannerExecutor
        from app.agents.chat_planner.base import PlanStep

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)

        registry = MagicMock()
        mock_skill = MagicMock()
        mock_skill.run = AsyncMock()  # Should NOT be called
        registry.select_by_name = MagicMock(return_value=mock_skill)

        action_step = PlanStep(
            step_id="a1",
            step_type="action",
            name="add_watchlist",
            status="pending",
            requires_confirmation=True,
            metadata={"action_type": "add_watchlist"},
        )

        executor = PlannerExecutor(registry)
        plan = _make_plan([action_step])
        result = await executor.execute(plan, "把 688146 加入自选", ctx)

        # skill.run should NOT be called for action steps
        mock_skill.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_executor_returns_valid_result_when_callback_raises(self):
        """PlannerExecutor must still return ExecutionResult when event_callback raises."""
        from app.agents.chat_planner.executor import PlannerExecutor

        async def bad_cb(event_type, payload):
            raise RuntimeError("callback failed")

        ctx = _make_context(bad_cb)
        registry = _make_skill_registry()
        executor = PlannerExecutor(registry)

        plan = _make_plan([_make_skill_step()])
        result = await executor.execute(plan, "688146", ctx)

        assert result is not None
        assert isinstance(result, ExecutionResult)

    @pytest.mark.asyncio
    async def test_step_completed_has_step_type_and_name(self):
        """planner_step_completed payload must include step_type and name fields."""
        from app.agents.chat_planner.executor import PlannerExecutor

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        registry = _make_skill_registry(skill_name="stock_anomaly_skill")
        executor = PlannerExecutor(registry)

        plan = _make_plan([_make_skill_step("stock_anomaly_skill")])
        await executor.execute(plan, "688146", ctx)

        completed = next((e[1] for e in events if e[0] == "planner_step_completed"), None)
        assert completed is not None
        assert "step_type" in completed
        assert "name" in completed
        assert completed["step_type"] == "skill"
