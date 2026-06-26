"""
GeneralFinancialAnswerSkill — Phase C14.

A broad-match fallback skill that uses RAG + DeepSeek to answer general
financial research questions when specific skills fail or don't match.

Priority=100 (lowest) — only runs when all higher-priority skills pass.
Used directly by SkillRegistry.run() as exception fallback.
"""
from __future__ import annotations

import logging
import re

from app.agents.chat_skills.base import (
    BaseSkill,
    SkillContext,
    SkillResult,
    _DISCLAIMER,
)
from app.agents.chat_rag import retrieve_context, RAGReviewCoordinator
from app.agents.chat_events import safe_emit

log = logging.getLogger(__name__)

# Simple greetings that should fall through to the default handler, not DeepSeek
_SIMPLE_GREETING = re.compile(
    r"^(你好+|hello+|hi+|hey+|哈+|嗨+|喂+|您好+|早上好|晚上好|下午好|good\s*(morning|afternoon|evening))\s*[！!。.，,？?]?$",
    re.IGNORECASE,
)

# Skill-level data limitation notice (prepended when tools had no data)
_DATA_LIMIT_NOTICE = "\n\n> **数据说明：** 本次回答基于现有参考资料，部分实时工具数据不可用，结论仅供参考。"


class GeneralFinancialAnswerSkill(BaseSkill):
    name = "general_financial_answer_skill"
    description = "通用金融研究问答（DeepSeek + RAG 兜底技能）"
    intent_examples = [
        "分析这只股票",
        "给我研究一下",
        "告诉我更多信息",
    ]
    required_tools: list[str] = []
    safety_level = "read_only"
    priority = 100

    def can_handle(self, message: str, context: SkillContext) -> bool:
        # Broad match: any non-empty financial message triggers this as fallback.
        # Simple greetings pass through to _handle_default so the user sees
        # the helpful capability menu rather than a DeepSeek "hi back" response.
        stripped = message.strip()
        if _SIMPLE_GREETING.match(stripped):
            return False
        return bool(stripped)

    async def run(self, message: str, context: SkillContext) -> SkillResult:
        events: list = []
        cards: list  = []

        await safe_emit(context.event_callback, "skill_started", {
            "skill_name": self.name,
            "skill_spec": self.name,
            "source": "skill_registry_fallback",
        })

        # ── Route through FinancialAgent for real tool calls + streaming ──────
        try:
            from app.agents.financial_agent import FinancialAgent, _detect_intent
            intent = _detect_intent(message)
            has_stock = bool(intent.get("symbol"))

            agent = FinancialAgent()
            response = await agent.run(
                query=message,
                db=context.db,
                tool_registry=context.tool_registry,
                output_language=context.output_language,
                event_callback=context.event_callback,
                timeout_seconds=40.0,
            )
            answer = response.answer_text

            # Record tool calls as tool events for audit trail
            for tc in response.tool_calls:
                events.append(self._tool_event(
                    tc.tool_name,
                    tc.result_summary or "",
                    "success" if tc.status == "success" else "error",
                ))

        except Exception as exc:
            log.warning("GeneralFinancialAnswerSkill: FinancialAgent failed, falling back to RAG: %s", exc)
            # Fallback: old RAG + DeepSeek path
            answer = await self._run_rag_fallback(message, context, events)

        await safe_emit(context.event_callback, "skill_completed", {
            "skill_name": self.name,
            "ok":         True,
            "tools_used": [e.get("name", "") for e in events],
            "cards_count": 0,
            "source": "skill_registry_fallback",
        })

        return SkillResult(
            ok=True,
            skill_name=self.name,
            answer=answer,
            tool_events=events,
            cards=cards,
        )

    async def _run_rag_fallback(self, message: str, context: SkillContext, events: list) -> str:
        """Original RAG + DeepSeek path, used when FinancialAgent fails."""
        data_limited = False
        try:
            rag_result = await retrieve_context(message, context)
        except Exception as exc:
            log.warning("GeneralFinancialAnswerSkill: RAG retrieval failed: %s", exc)
            from app.agents.chat_rag.base import RAGResult
            rag_result = RAGResult(ok=False, query=message, documents=[])
            data_limited = True

        _coordinator = RAGReviewCoordinator()
        await safe_emit(context.event_callback, "rag_review_started", {"source": "rag_review_coordinator"})
        try:
            _coordinator.review(rag_result)
        except Exception:
            pass
        await safe_emit(context.event_callback, "rag_review_completed", {
            "overall_confidence": rag_result.overall_confidence,
            "documents_count":    len(rag_result.documents),
            "approved_for_answer": rag_result.approved,
            "source":             "rag_review_coordinator",
        })

        events.append(self._tool_event(
            "rag_retrieve",
            f"检索到 {len(rag_result.documents)} 份参考资料",
            "success" if rag_result.ok else "error",
        ))
        events.append(self._tool_event(
            "rag_review",
            f"可信度：{rag_result.overall_confidence}",
            "success",
        ))

        tool_results_for_llm: list[dict] = []
        rag_docs_for_llm: list[dict] = []
        for doc in rag_result.documents:
            rag_docs_for_llm.append({
                "source_type": doc.source_type if hasattr(doc, "source_type") else doc.get("source_type", ""),
                "content":     doc.content if hasattr(doc, "content") else doc.get("content", ""),
                "summary":     doc.summary if hasattr(doc, "summary") else doc.get("summary", ""),
            })

        try:
            from app.agents.chat_llm_answerer import generate_answer
            answer = await generate_answer(
                user_message=message,
                tool_results=tool_results_for_llm,
                rag_documents=rag_docs_for_llm,
                output_language=context.output_language,
                timeout_seconds=28.0,
            )
            if data_limited:
                answer = answer.rstrip() + "\n\n> **数据说明：** 本次回答基于现有参考资料，部分实时工具数据不可用，结论仅供参考。"
        except Exception as exc:
            log.warning("GeneralFinancialAnswerSkill: DeepSeek failed: %s", exc)
            answer = (
                "### 研究摘要\n\n"
                "当前研究数据获取受限，无法提供完整分析。\n\n"
                "### 后续建议\n\n"
                "- 请稍后重试，或指定具体股票代码（如 688146）\n"
                "- 可尝试「帮我生成 688146 的综合报告」获取深度分析\n\n"
                f"（{str(exc)[:80]}）\n\n_仅供研究参考，不构成投资建议。_"
            )
        return answer
