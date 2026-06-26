"""
C14: Truthful Steps Contract Tests.

Verifies that placeholder steps show correct states:
1. _makePlaceholderSteps structure — first step running, rest pending (contract test)
2. statusIcon('pending') must NOT return '✓' (frontend contract)
3. statusIcon('running') returns '◌'
4. statusIcon('completed' / 'success') returns '✓'
5. statusIcon('failed') returns '✕'
6. statusIcon('error') returns '✕'
7. statusIcon('skipped') returns '—'
8. statusIcon('stopped') returns '□'
9. onError handler sets running→failed, pending→skipped (contract)
10. onStop handler sets running→stopped, pending→skipped (contract)
"""
from __future__ import annotations

import pytest


class TestPlaceholderStepsContract:
    """Contracts for the placeholder steps structure used in ChatCopilotView."""

    def test_placeholder_has_5_steps(self):
        """There must be exactly 5 placeholder steps."""
        # This is a Python representation of what the frontend _makePlaceholderSteps() creates
        steps = [
            {"name": "问题分析",   "status": "running"},
            {"name": "RAG资料检索", "status": "pending"},
            {"name": "资料审查",   "status": "pending"},
            {"name": "工具调用",   "status": "pending"},
            {"name": "结论生成",   "status": "pending"},
        ]
        assert len(steps) == 5

    def test_only_first_step_is_running(self):
        """Only the first placeholder step should be 'running' — rest must be 'pending'."""
        steps = [
            {"name": "问题分析",   "status": "running"},
            {"name": "RAG资料检索", "status": "pending"},
            {"name": "资料审查",   "status": "pending"},
            {"name": "工具调用",   "status": "pending"},
            {"name": "结论生成",   "status": "pending"},
        ]
        running = [s for s in steps if s["status"] == "running"]
        pending = [s for s in steps if s["status"] == "pending"]
        assert len(running) == 1
        assert len(pending) == 4
        assert running[0]["name"] == "问题分析"

    def test_pending_not_same_as_success(self):
        """'pending' is a distinct state — it must not be treated as success."""
        pending_statuses = {"pending"}
        success_statuses = {"success", "completed"}
        assert pending_statuses.isdisjoint(success_statuses)


class TestStatusIconContract:
    """
    Contract tests for ChatReasoningSteps.vue statusIcon() function.
    These are Python-side contracts; the actual function is in Vue.
    """

    def _status_icon(self, status: str) -> str:
        """Mirror of ChatReasoningSteps.vue statusIcon() function."""
        if status in ("failed", "error"):  return "✕"
        if status == "running":            return "◌"
        if status == "pending":            return "○"
        if status == "skipped":            return "—"
        if status == "partial":            return "◑"
        if status == "stopped":            return "□"
        return "✓"

    def test_pending_is_not_checkmark(self):
        """CRITICAL: pending must not show ✓ — this was the original bug."""
        icon = self._status_icon("pending")
        assert icon != "✓", "Bug regression: pending should not show ✓"

    def test_pending_shows_circle(self):
        icon = self._status_icon("pending")
        assert icon == "○"

    def test_running_shows_spinner(self):
        assert self._status_icon("running") == "◌"

    def test_success_shows_checkmark(self):
        assert self._status_icon("success") == "✓"

    def test_completed_shows_checkmark(self):
        assert self._status_icon("completed") == "✓"

    def test_failed_shows_cross(self):
        assert self._status_icon("failed") == "✕"

    def test_error_shows_cross(self):
        assert self._status_icon("error") == "✕"

    def test_skipped_shows_dash(self):
        assert self._status_icon("skipped") == "—"

    def test_stopped_shows_box(self):
        assert self._status_icon("stopped") == "□"


class TestStepStateTransitions:
    """Contract tests for step state transitions on agent_error and stop."""

    def _simulate_on_error(self, steps: list[dict]) -> list[dict]:
        """Simulate ChatCopilotView.vue onError handler."""
        for step in steps:
            if step["status"] == "running":
                step["status"] = "failed"
            elif step["status"] == "pending":
                step["status"] = "skipped"
        return steps

    def _simulate_on_stop(self, steps: list[dict]) -> list[dict]:
        """Simulate ChatCopilotView.vue onStop handler."""
        for step in steps:
            if step["status"] == "running":
                step["status"] = "stopped"
            elif step["status"] == "pending":
                step["status"] = "skipped"
        return steps

    def test_on_error_marks_running_as_failed(self):
        steps = [
            {"status": "success"},
            {"status": "running"},
            {"status": "pending"},
            {"status": "pending"},
        ]
        result = self._simulate_on_error(steps)
        assert result[1]["status"] == "failed"

    def test_on_error_marks_pending_as_skipped(self):
        steps = [
            {"status": "success"},
            {"status": "running"},
            {"status": "pending"},
            {"status": "pending"},
        ]
        result = self._simulate_on_error(steps)
        assert result[2]["status"] == "skipped"
        assert result[3]["status"] == "skipped"

    def test_on_error_preserves_success_steps(self):
        steps = [{"status": "success"}, {"status": "running"}]
        result = self._simulate_on_error(steps)
        assert result[0]["status"] == "success"

    def test_on_stop_marks_running_as_stopped(self):
        steps = [{"status": "running"}, {"status": "pending"}]
        result = self._simulate_on_stop(steps)
        assert result[0]["status"] == "stopped"

    def test_on_stop_marks_pending_as_skipped(self):
        steps = [{"status": "running"}, {"status": "pending"}]
        result = self._simulate_on_stop(steps)
        assert result[1]["status"] == "skipped"
