"""
C5 Action Tools — unit tests (no live DB / no live APIs).

Tests:
  1. execute_add_to_watchlist: successful insert → ActionResult ok=True, already_exists=False
  2. execute_add_to_watchlist: duplicate insert → ActionResult ok=True, already_exists=True
  3. execute_add_to_watchlist: returns watchlist_action card
  4. execute_create_analysis_run: LLM init failure → ActionResult ok=False
  5. execute_create_analysis_run: Registry init failure → ActionResult ok=False
  6. execute_create_analysis_run: successful create → ActionResult ok=True, analysis_run card
  7. execute_create_compare_selection: returns compare_link card, no await
  8. process_confirm: routes to correct action tool
  9. process_confirm: unknown type → safe ConfirmResult
 10. No forbidden investment phrases in any output
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.agents.chat_orchestrator import process_confirm, ConfirmResult
from app.agents.chat_tools.action_tools import (
    execute_create_compare_selection,
    ActionResult,
)

FORBIDDEN_PHRASES = ["买入", "卖出", "持有", "目标价"]
_USER_ID = uuid.uuid4()


def _make_db_mock_with_nested():
    """Create an AsyncMock db that properly supports begin_nested() as an async ctx mgr."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)
    db.flush   = AsyncMock()

    # begin_nested() must return an object that supports `async with` protocol
    nested_ctx = MagicMock()
    nested_ctx.__aenter__ = AsyncMock(return_value=None)
    nested_ctx.__aexit__  = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=nested_ctx)

    return db


def _no_forbidden(text: str) -> None:
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text, f"Found forbidden phrase '{phrase}' in: {text}"


# ── execute_create_compare_selection (synchronous) ─────────────────────────────

def test_compare_selection_basic():
    stocks = [
        {"name": "宁德时代", "market": "CN", "symbol": "300750"},
        {"name": "紫金矿业", "market": "CN", "symbol": "601899"},
    ]
    result = execute_create_compare_selection({"stocks": stocks})

    assert isinstance(result, ActionResult)
    assert result.ok is True
    assert result.action == "create_compare"
    assert result.cards, "Expected at least one card"
    assert result.cards[0]["type"] == "compare_link"
    assert "300750" in result.cards[0]["data"]["compareUrl"]
    _no_forbidden(result.answer)


def test_compare_selection_uses_existing_url():
    stocks = [{"name": "A", "market": "CN", "symbol": "000001"}]
    result = execute_create_compare_selection({
        "stocks": stocks,
        "compare_url": "/compare?stocks=CN:000001",
    })
    assert result.cards[0]["data"]["compareUrl"] == "/compare?stocks=CN:000001"


# ── execute_add_to_watchlist ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_watchlist_success():
    """New stock → inserted, already_exists=False."""
    db = _make_db_mock_with_nested()

    from app.agents.chat_tools.action_tools import execute_add_to_watchlist

    result = await execute_add_to_watchlist(
        {"market": "CN", "symbol": "688146", "name": "中船特气"},
        db, _USER_ID,
    )

    assert result.ok is True
    assert result.action == "add_watchlist"
    assert result.data["already_exists"] is False
    assert result.cards[0]["type"] == "watchlist_action"
    assert result.cards[0]["data"]["already_exists"] is False
    _no_forbidden(result.answer)
    db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_add_watchlist_already_exists():
    """Stock already in watchlist → ok=True, already_exists=True, no flush."""
    db = AsyncMock()
    existing = MagicMock()  # non-None mock
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    db.execute = AsyncMock(return_value=mock_result)
    db.flush   = AsyncMock()

    from app.agents.chat_tools.action_tools import execute_add_to_watchlist

    result = await execute_add_to_watchlist(
        {"market": "CN", "symbol": "688146", "name": "中船特气"},
        db, _USER_ID,
    )

    assert result.ok is True
    assert result.data["already_exists"] is True
    assert result.cards[0]["data"]["already_exists"] is True
    db.flush.assert_not_called()  # no insert attempted
    _no_forbidden(result.answer)


# ── execute_create_analysis_run ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analysis_run_llm_failure():
    """LLM init failure → ok=False, error message."""
    db = AsyncMock()
    with patch("app.agents.chat_tools.action_tools.get_llm_client",
               side_effect=ValueError("No API key")):
        from app.agents.chat_tools.action_tools import execute_create_analysis_run
        result = await execute_create_analysis_run(
            {"market": "CN", "symbol": "688146", "name": "中船特气"},
            db, _USER_ID,
        )

    assert result.ok is False
    assert result.error is not None
    _no_forbidden(result.answer)


@pytest.mark.asyncio
async def test_analysis_run_registry_failure():
    """Registry init failure → ok=False."""
    db = AsyncMock()
    mock_llm = MagicMock()
    with patch("app.agents.chat_tools.action_tools.get_llm_client", return_value=mock_llm), \
         patch("app.agents.chat_tools.action_tools.get_run_registry",
               side_effect=RuntimeError("Redis unavailable")):
        from app.agents.chat_tools.action_tools import execute_create_analysis_run
        result = await execute_create_analysis_run(
            {"market": "CN", "symbol": "688146", "name": "中船特气"},
            db, _USER_ID,
        )

    assert result.ok is False
    _no_forbidden(result.answer)


@pytest.mark.asyncio
async def test_analysis_run_success():
    """Successful run creation → ok=True, analysis_run card, run_id in data."""
    db = AsyncMock()
    mock_llm = MagicMock()
    mock_registry = AsyncMock()
    mock_run_ref = MagicMock()
    mock_run_ref.run_id = "run-test-001"
    mock_registry.create_run = AsyncMock(return_value=mock_run_ref)

    mock_runner = MagicMock()
    mock_runner.run_analysis = AsyncMock()

    with patch("app.agents.chat_tools.action_tools.get_llm_client", return_value=mock_llm), \
         patch("app.agents.chat_tools.action_tools.get_run_registry", return_value=mock_registry), \
         patch("app.agents.chat_tools.action_tools.RealtimeAnalysisRunner", return_value=mock_runner), \
         patch("app.agents.chat_tools.action_tools.asyncio.create_task"):
        from app.agents.chat_tools.action_tools import execute_create_analysis_run
        result = await execute_create_analysis_run(
            {"market": "CN", "symbol": "688146", "name": "中船特气"},
            db, _USER_ID,
        )

    assert result.ok is True
    assert result.data["run_id"] == "run-test-001"
    assert result.cards[0]["type"] == "analysis_run"
    assert result.cards[0]["data"]["run_id"] == "run-test-001"
    _no_forbidden(result.answer)


# ── process_confirm routing ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_confirm_add_watchlist():
    """process_confirm routes add_watchlist to execute_add_to_watchlist."""
    db = _make_db_mock_with_nested()

    result = await process_confirm(
        confirmation_type="add_watchlist",
        params={"market": "CN", "symbol": "688146", "name": "中船特气"},
        db=db,
        user_id=_USER_ID,
    )

    assert isinstance(result, ConfirmResult)
    assert result.cards[0]["type"] == "watchlist_action"
    _no_forbidden(result.answer)


@pytest.mark.asyncio
async def test_process_confirm_create_compare():
    """process_confirm routes create_compare to execute_create_compare_selection."""
    db = AsyncMock()
    stocks = [{"name": "宁德时代", "market": "CN", "symbol": "300750"}]

    result = await process_confirm(
        confirmation_type="create_compare",
        params={"stocks": stocks},
        db=db,
        user_id=_USER_ID,
    )

    assert isinstance(result, ConfirmResult)
    assert result.cards[0]["type"] == "compare_link"
    _no_forbidden(result.answer)


@pytest.mark.asyncio
async def test_process_confirm_unknown_type():
    """Unknown action type → safe fallback ConfirmResult."""
    db = AsyncMock()
    result = await process_confirm(
        confirmation_type="unknown_action_xyz",
        params={},
        db=db,
        user_id=_USER_ID,
    )

    assert isinstance(result, ConfirmResult)
    assert "已完成" in result.answer
    _no_forbidden(result.answer)


@pytest.mark.asyncio
async def test_process_confirm_exception_handled():
    """Exception inside action tool → safe error ConfirmResult (no re-raise)."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("DB error"))

    result = await process_confirm(
        confirmation_type="add_watchlist",
        params={"market": "CN", "symbol": "688146", "name": "中船特气"},
        db=db,
        user_id=_USER_ID,
    )

    assert isinstance(result, ConfirmResult)
    assert "错误" in result.answer
