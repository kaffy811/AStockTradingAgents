"""
C14: Session Title Auto-Update Tests.

1. maybe_update_session_title returns new title when session has default title
2. maybe_update_session_title returns None when session already has real title
3. maybe_update_session_title truncates to 30 chars
4. maybe_update_session_title strips newlines
5. maybe_update_session_title returns None for empty content
6. maybe_update_session_title returns None when session not found
7. SSE stream emits session_title_updated when title updated
8. SSE stream does NOT emit session_title_updated if title already set
"""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMaybeUpdateSessionTitle:
    """Unit tests for chat_service.maybe_update_session_title."""

    @pytest.mark.asyncio
    async def test_updates_default_title(self):
        """Returns new title when session has '新的研究对话'."""
        from app.services.chat_service import maybe_update_session_title

        mock_session = MagicMock()
        mock_session.title = "新的研究对话"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await maybe_update_session_title(
            mock_db, uuid.uuid4(), "中船特气最近为什么涨这么多"
        )
        assert result == "中船特气最近为什么涨这么多"
        assert mock_session.title == "中船特气最近为什么涨这么多"

    @pytest.mark.asyncio
    async def test_no_update_when_title_already_set(self):
        """Returns None when session already has a real title."""
        from app.services.chat_service import maybe_update_session_title

        mock_session = MagicMock()
        mock_session.title = "之前的研究对话"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await maybe_update_session_title(
            mock_db, uuid.uuid4(), "新问题内容"
        )
        assert result is None
        assert mock_session.title == "之前的研究对话"

    @pytest.mark.asyncio
    async def test_truncates_to_30_chars(self):
        """Truncates content to 30 characters."""
        from app.services.chat_service import maybe_update_session_title

        mock_session = MagicMock()
        mock_session.title = "新的研究对话"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        long_content = "这是一段非常长的用户问题内容，超过了三十个字符的限制，应该被截断"
        result = await maybe_update_session_title(mock_db, uuid.uuid4(), long_content)
        assert result is not None
        assert len(result) <= 30

    @pytest.mark.asyncio
    async def test_strips_newlines(self):
        """Strips newlines from content."""
        from app.services.chat_service import maybe_update_session_title

        mock_session = MagicMock()
        mock_session.title = "新的研究对话"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await maybe_update_session_title(
            mock_db, uuid.uuid4(), "第一行\n第二行"
        )
        assert result is not None
        assert "\n" not in result

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_content(self):
        """Returns None when content is blank."""
        from app.services.chat_service import maybe_update_session_title

        mock_session = MagicMock()
        mock_session.title = "新的研究对话"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await maybe_update_session_title(mock_db, uuid.uuid4(), "   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_session_not_found(self):
        """Returns None when session does not exist."""
        from app.services.chat_service import maybe_update_session_title

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await maybe_update_session_title(mock_db, uuid.uuid4(), "问题内容")
        assert result is None
