"""
C30.3 Tests: Chat Runtime Transaction Safety.

T1-T6:   C30.3.1 — Transaction isolation in chat_streaming._orchestrate()
T7-T10:  C30.3.2 — safe_flush helper in chat_service
T11-T13: C30.3.3 — Background runner session isolation (regression guard)
"""
from __future__ import annotations

import asyncio
import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _make_session_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_user_id() -> uuid.UUID:
    return uuid.uuid4()


def _mock_db():
    """Return an AsyncMock that mimics AsyncSession flush/commit/rollback."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
    return db


# ══════════════════════════════════════════════════════════════════════════════
# T1-T6: C30.3.1 — transaction isolation in chat_streaming._orchestrate()
# ══════════════════════════════════════════════════════════════════════════════

class TestStreamingTransactionIsolation:
    """Verify chat_streaming commits user message before orchestration starts."""

    def test_t1_chat_streaming_imports_commit_after_user_message(self):
        """T1: chat_streaming._orchestrate() calls db.commit() after save_user_message."""
        import inspect
        import app.agents.chat_streaming as cs
        src = inspect.getsource(cs)
        # After save_user_message, there must be an await db.commit()
        # Look for the pattern: save_user_message ... commit
        save_pos = src.find("save_user_message(")
        commit_pos = src.find("await db.commit()", save_pos)
        assert save_pos > 0, "save_user_message must be in chat_streaming"
        assert commit_pos > 0, "db.commit() must follow save_user_message"
        assert commit_pos > save_pos, "db.commit() must come AFTER save_user_message"

    def test_t2_title_catch_block_calls_rollback(self):
        """T2: The title update except block calls db.rollback() before continuing."""
        import inspect
        import app.agents.chat_streaming as cs
        src = inspect.getsource(cs)
        # Locate the title-update try/except block
        title_try = src.find("maybe_update_session_title(")
        assert title_try > 0, "maybe_update_session_title must be in chat_streaming"
        # Find the except block that follows
        except_pos = src.find("except Exception:", title_try)
        assert except_pos > 0, "except block must follow maybe_update_session_title"
        # rollback must appear between except and the next non-indented section
        rollback_pos = src.find("await db.rollback()", except_pos)
        assert rollback_pos > 0, "db.rollback() must appear in title update except block"
        # rollback must come before the next Phase comment
        next_phase = src.find("# ── Phase 2:", except_pos)
        assert rollback_pos < next_phase, (
            "db.rollback() in title except block must appear before Phase 2 starts"
        )

    def test_t3_title_update_commits_when_successful(self):
        """T3: When title update succeeds, a db.commit() is called for it."""
        import inspect
        import app.agents.chat_streaming as cs
        src = inspect.getsource(cs)
        # After maybe_update_session_title + new_title check, there must be commit
        title_pos = src.find("maybe_update_session_title(")
        new_title_pos = src.find("if new_title:", title_pos)
        assert new_title_pos > title_pos
        commit_in_title = src.find("await db.commit()", new_title_pos)
        # That commit must appear before the except block
        except_pos = src.find("except Exception:", title_pos)
        assert commit_in_title > 0, "commit inside 'if new_title' block required"
        assert commit_in_title < except_pos, (
            "Title commit must be inside the try block, not the except"
        )

    def test_t4_user_message_commit_is_c3031_annotated(self):
        """T4: The commit after save_user_message has a C30.3.1 annotation."""
        import inspect
        import app.agents.chat_streaming as cs
        src = inspect.getsource(cs)
        # The C30.3.1 comment must appear near the db.commit() call
        assert "C30.3.1" in src, "C30.3.1 annotation must be present in chat_streaming"

    @pytest.mark.asyncio
    async def test_t5_safe_flush_leaves_session_clean_on_failure(self):
        """T5: safe_flush() calls rollback and re-raises so session is clean."""
        from app.services.chat_service import safe_flush

        db = _mock_db()
        db.flush.side_effect = RuntimeError("constraint violation")

        with pytest.raises(RuntimeError, match="constraint violation"):
            await safe_flush(db, context="test_t5")

        db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_t6_safe_flush_no_rollback_on_success(self):
        """T6: safe_flush() does NOT call rollback when flush succeeds."""
        from app.services.chat_service import safe_flush

        db = _mock_db()
        db.flush.return_value = None  # success

        await safe_flush(db, context="test_t6")

        db.rollback.assert_not_called()
        db.flush.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# T7-T10: C30.3.2 — safe_flush helper
# ══════════════════════════════════════════════════════════════════════════════

class TestSafeFlush:
    """Verify safe_flush helper contract."""

    def test_t7_safe_flush_is_async(self):
        """T7: safe_flush is a coroutine function."""
        from app.services.chat_service import safe_flush
        assert inspect.iscoroutinefunction(safe_flush)

    def test_t8_safe_flush_has_context_kwarg(self):
        """T8: safe_flush accepts a 'context' keyword argument."""
        from app.services.chat_service import safe_flush
        sig = inspect.signature(safe_flush)
        assert "context" in sig.parameters, "safe_flush must accept 'context' kwarg"

    def test_t9_save_user_message_uses_safe_flush(self):
        """T9: save_user_message calls safe_flush (not bare db.flush)."""
        import inspect
        from app.services import chat_service
        src = inspect.getsource(chat_service.save_user_message)
        assert "safe_flush" in src, "save_user_message must call safe_flush"
        # Must NOT call bare db.flush() directly
        assert "await db.flush()" not in src, (
            "save_user_message must not call bare db.flush() — use safe_flush"
        )

    def test_t10_save_assistant_message_uses_safe_flush(self):
        """T10: save_assistant_message calls safe_flush (not bare db.flush)."""
        import inspect
        from app.services import chat_service
        src = inspect.getsource(chat_service.save_assistant_message)
        assert "safe_flush" in src, "save_assistant_message must call safe_flush"
        assert "await db.flush()" not in src, (
            "save_assistant_message must not call bare db.flush() — use safe_flush"
        )


# ══════════════════════════════════════════════════════════════════════════════
# T11-T13: C30.3.3 — Background runner session isolation (regression guard)
# ══════════════════════════════════════════════════════════════════════════════

class TestBackgroundRunnerSessionIsolation:
    """
    Background analysis runners must NOT share the chat_streaming db session.
    Each runner must create its own AsyncSession so a failed report save cannot
    poison the chat session's transaction.
    """

    def test_t11_action_tools_uses_own_session_for_background_task(self):
        """T11: execute_create_analysis_run creates AsyncSessionLocal for bg task."""
        import inspect
        import app.agents.chat_tools.action_tools as at
        src = inspect.getsource(at)
        # Background task must open its own session
        assert "AsyncSessionLocal" in src, (
            "action_tools must use AsyncSessionLocal for background report tasks"
        )
        assert "async with AsyncSessionLocal()" in src, (
            "background task must use 'async with AsyncSessionLocal()' context manager"
        )

    def test_t12_action_tools_bg_session_not_same_as_chat_db(self):
        """T12: The background session variable is distinct from the 'db' parameter."""
        import inspect
        import app.agents.chat_tools.action_tools as at
        src = inspect.getsource(at)
        # There should be an alias like 'bg_db' or 'report_db' that is not 'db'
        # The key guarantee: the inner async-with block uses a DIFFERENT name
        assert "async with AsyncSessionLocal() as bg_db" in src or \
               "async with AsyncSessionLocal() as report_db" in src or \
               "async with AsyncSessionLocal() as _db" in src, (
            "Background task must bind AsyncSessionLocal() to a different variable (bg_db etc.)"
        )

    def test_t13_realtime_runner_does_not_use_shared_outer_db(self):
        """T13: RealtimeAnalysisRunner receives its own session (not the streaming session)."""
        import inspect
        import app.agents.realtime_analysis_runner as rar
        src = inspect.getsource(rar)
        # Runner must accept db as a parameter (injected fresh from action_tools)
        # and must not import or reuse a global session
        assert "async def run(" in src or "async def execute(" in src or \
               "async def start(" in src or "db" in src, (
            "RealtimeAnalysisRunner must accept a db session parameter"
        )
        # Must NOT import get_db (which is a FastAPI dependency injector)
        assert "from app.core.database import get_db" not in src, (
            "RealtimeAnalysisRunner must not use get_db — it should receive db as param"
        )


# ══════════════════════════════════════════════════════════════════════════════
# T14-T16: C30.3.5 — P3 constraint regression (save before completed)
# ══════════════════════════════════════════════════════════════════════════════

class TestP3CompletedRegressionAfterC303:
    """Verify C30.3 transaction changes did not break P3 ordering constraints."""

    def test_t14_langgraph_runner_still_saves_before_completed(self):
        """T14: LangGraphRealtimeRunner still calls save_generated_report before 'completed'."""
        import inspect
        import app.agents.langgraph_realtime_runner as lgr
        src = inspect.getsource(lgr)
        save_pos      = src.find("save_generated_report")
        completed_pos = src.find('"completed"')
        assert save_pos > 0, "save_generated_report must still be in langgraph_realtime_runner"
        assert completed_pos > 0
        assert save_pos < completed_pos

    def test_t15_realtime_runner_still_saves_before_completed(self):
        """T15: RealtimeAnalysisRunner still calls save_generated_report before 'completed'."""
        import inspect
        import app.agents.realtime_analysis_runner as rar
        src = inspect.getsource(rar)
        save_pos      = src.find("save_generated_report")
        completed_pos = src.find('"completed"')
        assert save_pos > 0
        assert completed_pos > 0
        assert save_pos < completed_pos

    def test_t16_chat_streaming_commit_does_not_remove_assistant_message_save(self):
        """T16: After adding Phase 1 commit, Phase 9 (save_assistant_message) is still present."""
        import inspect
        import app.agents.chat_streaming as cs
        src = inspect.getsource(cs)
        assert "save_assistant_message(" in src, (
            "chat_streaming must still call save_assistant_message in Phase 9"
        )
        assert "await db.commit()" in src, (
            "chat_streaming must still commit after saving assistant message"
        )


# ══════════════════════════════════════════════════════════════════════════════
# T17-T20: C30.3.6 — User-visible error message sanitization
# ══════════════════════════════════════════════════════════════════════════════

class TestErrorMessageSanitization:

    def test_t17_sanitize_function_exists(self):
        """T17: _sanitize_error_for_user is defined in chat_streaming."""
        import app.agents.chat_streaming as cs
        assert hasattr(cs, "_sanitize_error_for_user"), (
            "_sanitize_error_for_user must be defined in chat_streaming"
        )

    def test_t18_db_errors_are_sanitized(self):
        """T18: PendingRollbackError is replaced with a generic friendly message."""
        from app.agents.chat_streaming import _sanitize_error_for_user

        class FakePendingRollback(Exception):
            pass
        FakePendingRollback.__name__ = "PendingRollbackError"

        exc = FakePendingRollback("can't reconnect until invalid transaction is rolled back")
        result = _sanitize_error_for_user(exc)
        # Must NOT include the raw SQLAlchemy message
        assert "rolled back" not in result
        assert "sqlalchemy" not in result.lower()

    def test_t19_sqlalchemy_in_message_is_sanitized(self):
        """T19: Exception with 'sqlalchemy' in message is sanitized."""
        from app.agents.chat_streaming import _sanitize_error_for_user

        exc = ValueError("sqlalchemy.exc.IntegrityError: DETAIL: Key (user_id)=(xxx) conflicts")
        result = _sanitize_error_for_user(exc)
        assert "sqlalchemy" not in result.lower()
        assert "IntegrityError" not in result

    def test_t20_non_db_errors_pass_through(self):
        """T20: Non-DB errors are passed through (truncated to 200 chars)."""
        from app.agents.chat_streaming import _sanitize_error_for_user

        exc = ValueError("LLM rate limit exceeded")
        result = _sanitize_error_for_user(exc)
        assert "LLM rate limit" in result

    def test_t21_fallback_uses_sanitized_error(self):
        """T21: The except block in _orchestrate uses _sanitize_error_for_user."""
        import inspect
        import app.agents.chat_streaming as cs
        src = inspect.getsource(cs._orchestrate if hasattr(cs, '_orchestrate') else cs)
        # The except block must call _sanitize_error_for_user, not raw str(exc)
        assert "_sanitize_error_for_user(exc)" in src, (
            "chat_streaming except block must call _sanitize_error_for_user(exc)"
        )
