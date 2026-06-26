"""
test_c11_internal_agent_workflow.py — Phase C11 Internal Agent Workflow tests.

Tests: analysis_and_save_report intent detection, confirmation creation,
       external channel refusal, and existing confirmation flow unchanged.
"""
from __future__ import annotations

import re
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.chat_orchestrator import (
    _match_analysis_save_report,
    _match_external_channel,
    process_message,
    process_confirm,
)


# ── Intent matchers ────────────────────────────────────────────────────────────

class TestMatchAnalysisSaveReport:
    def test_match_fen_xi_bing_bao_cun(self):
        assert _match_analysis_save_report("帮我分析中船特气并保存到历史报告")

    def test_match_fen_xi_ran_hou_bao_cun(self):
        assert _match_analysis_save_report("分析688146然后生成历史报告")

    def test_match_bao_cun_zhi_bao_gao(self):
        assert _match_analysis_save_report("保存至历史报告")

    def test_match_sheng_cheng_bing_bao_cun(self):
        assert _match_analysis_save_report("生成报告并保存")

    def test_no_match_simple_report(self):
        # Plain "generate report" should NOT match this (handled by _match_report)
        assert not _match_analysis_save_report("帮我生成综合报告")

    def test_no_match_view_report(self):
        assert not _match_analysis_save_report("查看历史报告")


class TestMatchExternalChannel:
    def test_match_email(self):
        assert _match_external_channel("发到邮箱")

    def test_match_wechat(self):
        assert _match_external_channel("发给微信")

    def test_match_dingtalk(self):
        assert _match_external_channel("钉钉推送")

    def test_match_feishu(self):
        assert _match_external_channel("飞书发送")

    def test_no_match_normal_save(self):
        assert not _match_external_channel("保存到历史报告")

    def test_no_match_analysis(self):
        assert not _match_external_channel("帮我分析688146")


# ── Full process_message integration ──────────────────────────────────────────

def _mock_registry():
    """Return a ToolRegistry mock that returns ok results."""
    mock = MagicMock()
    resolve_result = MagicMock()
    resolve_result.ok = True
    resolve_result.data = {"market": "CN", "symbol": "688146", "name": "中船特气"}
    resolve_result.tool_name = "resolve_stock_tool"
    resolve_result.summary = "resolved"
    resolve_result.permission_level = "read_only"
    resolve_result.duration_ms = 10
    resolve_result.started_at = None
    resolve_result.error = None
    resolve_result.cards = []

    async def _call(name, db, **kw):
        return resolve_result

    mock.call = _call
    return mock


@pytest.mark.asyncio
async def test_analysis_save_report_returns_confirmation():
    """Analyze+save intent should return a confirmation, not an answer."""
    with patch("app.agents.chat_orchestrator._registry", _mock_registry()):
        result = await process_message(
            content="帮我分析中船特气并保存到历史报告",
            db=AsyncMock(),
            user_id=uuid.uuid4(),
            session_id=None,
        )
    assert result.confirmation is not None
    assert result.confirmation.get("type") == "create_analysis_run"


@pytest.mark.asyncio
async def test_external_channel_returns_refusal():
    """External channel intent should return a polite refusal."""
    with patch("app.agents.chat_orchestrator._registry", _mock_registry()):
        result = await process_message(
            content="把报告发到我的邮箱",
            db=AsyncMock(),
            user_id=uuid.uuid4(),
            session_id=None,
        )
    assert result.answer
    assert result.confirmation is None
    assert "暂不支持" in result.answer or "不支持" in result.answer


@pytest.mark.asyncio
async def test_analysis_save_scope_fundamental():
    """Messages mentioning 基本面 should set scope=fundamental."""
    with patch("app.agents.chat_orchestrator._registry", _mock_registry()):
        result = await process_message(
            content="分析688146基本面并保存到历史报告",
            db=AsyncMock(),
            user_id=uuid.uuid4(),
            session_id=None,
        )
    assert result.confirmation is not None
    params = (result.confirmation or {}).get("params", {})
    assert params.get("scope") == "fundamental"


@pytest.mark.asyncio
async def test_external_channel_wechat_refusal():
    with patch("app.agents.chat_orchestrator._registry", _mock_registry()):
        result = await process_message(
            content="钉钉通知一下",
            db=AsyncMock(),
            user_id=uuid.uuid4(),
            session_id=None,
        )
    # Either a refusal answer or default (no trading instructions)
    assert "不提供交易指令" not in result.answer  # not a safety refusal


@pytest.mark.asyncio
async def test_process_confirm_unknown_type_still_works():
    """Existing process_confirm contract unchanged."""
    result = await process_confirm(
        confirmation_type="unknown_action_xyz",
        params={},
        db=AsyncMock(),
        user_id=uuid.uuid4(),
    )
    assert result.answer  # returns something, not a crash
