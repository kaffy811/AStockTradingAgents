"""
C14: LLM Answer Generation Tests.

1. generate_answer calls DeepSeek and returns non-empty string
2. generate_answer appends disclaimer if not present
3. generate_answer filters banned phrase 买入→关注
4. generate_answer filters banned phrase 卖出→观察
5. generate_answer handles empty tool_results gracefully
6. generate_answer handles empty rag_documents gracefully
7. generate_answer raises ValueError when DEEPSEEK_API_KEY not set
8. generate_answer raises asyncio.TimeoutError when LLM exceeds timeout
9. _build_tool_summary formats tool results correctly
10. _build_rag_summary formats RAG documents correctly
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBuildHelpers:
    """Unit tests for _build_tool_summary and _build_rag_summary."""

    def test_build_tool_summary_empty(self):
        from app.agents.chat_llm_answerer import _build_tool_summary
        result = _build_tool_summary([])
        # The actual implementation returns "（无工具数据）"
        assert "无工具数据" in result

    def test_build_tool_summary_with_results(self):
        from app.agents.chat_llm_answerer import _build_tool_summary
        results = [{"name": "get_quote_tool", "status": "success", "detail": "价格 10.5"}]
        result = _build_tool_summary(results)
        assert "get_quote_tool" in result
        assert "success" in result

    def test_build_rag_summary_empty(self):
        from app.agents.chat_llm_answerer import _build_rag_summary
        result = _build_rag_summary([])
        # The actual implementation returns "（无参考资料）"
        assert "无参考资料" in result

    def test_build_rag_summary_with_docs(self):
        from app.agents.chat_llm_answerer import _build_rag_summary
        docs = [{"source_type": "news", "content": "中船特气公告"}]
        result = _build_rag_summary(docs)
        assert "news" in result
        assert "中船特气" in result


class TestFilterBannedPhrases:
    def test_filters_buy_phrase(self):
        from app.agents.chat_llm_answerer import _filter_banned_phrases
        text = "建议买入这只股票"
        result = _filter_banned_phrases(text)
        assert "买入" not in result

    def test_filters_sell_phrase(self):
        from app.agents.chat_llm_answerer import _filter_banned_phrases
        text = "适合卖出"
        result = _filter_banned_phrases(text)
        assert "卖出" not in result

    def test_safe_text_unchanged(self):
        from app.agents.chat_llm_answerer import _filter_banned_phrases
        text = "研究这只股票的技术面"
        result = _filter_banned_phrases(text)
        assert result == text


class TestGenerateAnswer:
    """
    generate_answer imports get_llm_client locally inside the function body:
        from app.llm.factory import get_llm_client
    So we must patch "app.llm.factory.get_llm_client".
    """

    @pytest.mark.asyncio
    async def test_returns_non_empty_string(self):
        """generate_answer returns non-empty answer from LLM."""
        from app.agents.chat_llm_answerer import generate_answer

        mock_llm = MagicMock()
        mock_llm.chat_flash.return_value = "### 研究摘要\n\n这是研究结论。"

        with patch("app.llm.factory.get_llm_client", return_value=mock_llm):
            result = await generate_answer(
                user_message="688146 为什么涨",
                tool_results=[],
                rag_documents=[],
            )
        assert result
        assert len(result) > 10

    @pytest.mark.asyncio
    async def test_appends_disclaimer(self):
        """generate_answer always appends the disclaimer."""
        from app.agents.chat_llm_answerer import generate_answer

        mock_llm = MagicMock()
        mock_llm.chat_flash.return_value = "研究内容"

        with patch("app.llm.factory.get_llm_client", return_value=mock_llm):
            result = await generate_answer(
                user_message="test",
                tool_results=[],
                rag_documents=[],
            )
        assert "仅供研究参考" in result

    @pytest.mark.asyncio
    async def test_raises_on_empty_llm_response(self):
        """generate_answer raises RuntimeError when LLM returns empty string."""
        from app.agents.chat_llm_answerer import generate_answer

        mock_llm = MagicMock()
        mock_llm.chat_flash.return_value = ""

        with patch("app.llm.factory.get_llm_client", return_value=mock_llm):
            with pytest.raises(RuntimeError):
                await generate_answer(
                    user_message="test",
                    tool_results=[],
                    rag_documents=[],
                )

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        """generate_answer raises asyncio.TimeoutError when LLM is too slow."""
        from app.agents.chat_llm_answerer import generate_answer

        with patch("app.llm.factory.get_llm_client"):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                with pytest.raises(asyncio.TimeoutError):
                    await generate_answer(
                        user_message="test",
                        tool_results=[],
                        rag_documents=[],
                        timeout_seconds=0.001,
                    )

    @pytest.mark.asyncio
    async def test_filters_buy_in_llm_output(self):
        """generate_answer filters '买入' from LLM response."""
        from app.agents.chat_llm_answerer import generate_answer

        mock_llm = MagicMock()
        mock_llm.chat_flash.return_value = "建议买入这只股票，前景很好。"

        with patch("app.llm.factory.get_llm_client", return_value=mock_llm):
            result = await generate_answer(
                user_message="688146",
                tool_results=[],
                rag_documents=[],
            )
        assert "买入" not in result

    @pytest.mark.asyncio
    async def test_filters_sell_in_llm_output(self):
        """generate_answer filters '卖出' from LLM response."""
        from app.agents.chat_llm_answerer import generate_answer

        mock_llm = MagicMock()
        mock_llm.chat_flash.return_value = "适合卖出，注意风险。"

        with patch("app.llm.factory.get_llm_client", return_value=mock_llm):
            result = await generate_answer(
                user_message="688146",
                tool_results=[],
                rag_documents=[],
            )
        assert "卖出" not in result

    @pytest.mark.asyncio
    async def test_handles_empty_tool_results(self):
        """generate_answer does not crash on empty tool_results."""
        from app.agents.chat_llm_answerer import generate_answer

        mock_llm = MagicMock()
        mock_llm.chat_flash.return_value = "### 研究摘要\n内容。"

        with patch("app.llm.factory.get_llm_client", return_value=mock_llm):
            result = await generate_answer(
                user_message="test",
                tool_results=[],
                rag_documents=[],
            )
        assert result

    @pytest.mark.asyncio
    async def test_handles_empty_rag_documents(self):
        """generate_answer does not crash on empty rag_documents."""
        from app.agents.chat_llm_answerer import generate_answer

        mock_llm = MagicMock()
        mock_llm.chat_flash.return_value = "### 研究摘要\n内容。"

        with patch("app.llm.factory.get_llm_client", return_value=mock_llm):
            result = await generate_answer(
                user_message="test",
                tool_results=[{"name": "tool1", "status": "success"}],
                rag_documents=[],
            )
        assert result
