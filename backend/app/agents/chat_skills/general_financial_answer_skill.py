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
from dataclasses import dataclass

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

_REPORT_INTENT = re.compile(
    r"report_id|解释.{0,6}报告|报告.{0,6}(解释|结论|风险|内容)|最近.{0,4}报告|这份报告|报告里"
    r"|财报|年报|半年报|季报|一季报|三季报|年度报告|半年度报告|季度报告",
    re.IGNORECASE,
)
_NEWS_INTENT = re.compile(r"新闻|消息|公告|利好|利空|催化|哪一条影响最大", re.IGNORECASE)
_ANOMALY_INTENT = re.compile(r"异动|为什么.*(涨|跌)|大涨|大跌|涨停|跌停|放量|缩量", re.IGNORECASE)
_RISK_INTENT = re.compile(r"风险|暴雷|黑天鹅|最大.*不确定|不确定性", re.IGNORECASE)
_ACTION_OR_COMPARE_INTENT = re.compile(
    r"对比|比较|相比|和.{1,12}比|综合分析|生成.*报告|保存.*报告|加入自选|添加自选|自选股",
    re.IGNORECASE,
)
_FINANCIAL_SIGNAL = re.compile(
    r"股票|股价|行情|价格|走势|技术|K线|成交量|涨跌|表现|公司|行业|板块|资金|"
    r"财报|年报|季报|中报|半年报|营收|利润|现金流|毛利率|估值|PE|PB|ROE|分红|盈利|基本面|市场|研究|分析|"
    r"\b\d{6}\b|\b[A-Z]{1,5}\b|茅台|贵州茅台|宁德时代|中船特气|紫金矿业|腾讯|阿里|美团|苹果|英伟达|特斯拉",
    re.IGNORECASE,
)
_PRONOUN_STOCK_QUERY = re.compile(r"^(它|这家公司|这个公司|这只股票|这个标的).*(怎么样|表现|价格|走势|风险|新闻|现金流|利润|为什么)?$")


@dataclass(frozen=True)
class RoutingDecision:
    action: str
    reason: str
    effective_query: str


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
        decision = self._routing_decision(message, context)
        return decision.action in {"handle", "clarify"}

    def _routing_decision(self, message: str, context: SkillContext) -> RoutingDecision:
        stripped = (message or "").strip()
        if not stripped:
            return RoutingDecision("defer", "empty", stripped)
        if _SIMPLE_GREETING.match(stripped):
            return RoutingDecision("defer", "simple_greeting", stripped)
        if _REPORT_INTENT.search(stripped):
            return RoutingDecision("defer", "specific_report_explanation", stripped)
        if _NEWS_INTENT.search(stripped):
            return RoutingDecision("defer", "specific_news_catalyst", stripped)
        if _ANOMALY_INTENT.search(stripped):
            return RoutingDecision("defer", "specific_stock_anomaly", stripped)
        if _RISK_INTENT.search(stripped):
            return RoutingDecision("defer", "specific_risk_first", stripped)
        if _ACTION_OR_COMPARE_INTENT.search(stripped):
            return RoutingDecision("defer", "action_or_comparison_intent", stripped)

        memory_context = getattr(context, "memory_context", None)
        resolved_query = (getattr(memory_context, "resolved_query", "") or "").strip() if memory_context else ""
        active_stocks = [
            e for e in (getattr(memory_context, "active_entities", []) or [])
            if getattr(e, "type", "") == "stock" and (getattr(e, "code", "") or getattr(e, "name", ""))
        ] if memory_context else []

        if _PRONOUN_STOCK_QUERY.search(stripped):
            if resolved_query and resolved_query != stripped:
                return RoutingDecision("handle", "memory_resolved_pronoun", resolved_query)
            if len(active_stocks) == 1:
                stock = active_stocks[0]
                name = getattr(stock, "name", "") or getattr(stock, "code", "")
                return RoutingDecision("handle", "single_memory_entity", f"{name} {stripped}")
            if len(active_stocks) > 1:
                return RoutingDecision("clarify", "ambiguous_memory_entities", stripped)
            return RoutingDecision("clarify", "missing_entity_for_pronoun", stripped)

        if _FINANCIAL_SIGNAL.search(stripped):
            return RoutingDecision("handle", "general_financial_fallback", resolved_query or stripped)

        return RoutingDecision("defer", "non_financial", stripped)

    def _clarification_answer(self, reason: str) -> str:
        if reason == "ambiguous_memory_entities":
            body = "当前会话里有多个可能的股票对象，请明确要分析哪家公司和市场，例如“贵州茅台 CN/600519 最近表现如何”。"
        else:
            body = "当前没有足够上下文确认要分析的公司或股票代码。请补充公司名称、代码和市场，例如“贵州茅台 CN/600519 最近表现如何”。"
        return body + _DISCLAIMER

    def _memory_prompt_block(self, context: SkillContext) -> str:
        mem_ctx = getattr(context, "memory_context", None)
        if mem_ctx is not None and not mem_ctx.is_empty():
            mem_block = mem_ctx.to_prompt_block()
            if mem_block:
                return mem_block
        return ""

    def _fallback_evidence_from_events(self, events: list) -> list[dict]:
        evidence: list[dict] = []
        for event in events:
            detail = event.get("detail", "")
            if event.get("name") == "rag_review":
                continue
            if "检索到 0" in detail:
                continue
            if event.get("status") == "success" and detail:
                evidence.append({
                    "name": event.get("name", "tool_result"),
                    "status": "success",
                    "detail": detail,
                })
        return evidence

    def _fallback_data_quality(self, events: list, rag_docs: list[dict] | None = None) -> dict:
        successes = [e for e in events if e.get("status") == "success"]
        failures = [e for e in events if e.get("status") != "success"]
        has_rag = bool(rag_docs)
        if successes and has_rag:
            level = "medium"
        elif successes or has_rag:
            level = "partial"
        else:
            level = "insufficient"
        return {
            "level": level,
            "evidence_count": len(successes) + len(rag_docs or []),
            "failed_tools": [e.get("name") for e in failures if e.get("name")],
        }

    def _sanitize_fallback_error(self, exc: Exception) -> str:
        text = str(exc)[:120]
        text = re.sub(r"(/[A-Za-z0-9_.@-]+)+", "[path]", text)
        text = re.sub(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*\S+", r"\1=[redacted]", text)
        text = re.sub(r"(?i)api[_-]?key|secret|token|password", "credential", text)
        return text or "unknown_error"

    def _has_reliable_evidence(self, events: list, rag_docs: list[dict] | None = None) -> bool:
        return bool(self._fallback_evidence_from_events(events)) or bool(rag_docs)

    def _no_evidence_fallback_answer(self, message: str, reason: str) -> str:
        return (
            "### 研究摘要\n\n"
            "当前通用金融问答主链遇到技术失败，且没有可用的工具结果或已审核参考资料，因此不能生成具体股票事实、价格、涨跌幅或财务数字。\n\n"
            "### 关键依据\n\n"
            "- 本次没有可靠 evidence 可用于事实回答。\n\n"
            "### 风险与不确定性\n\n"
            f"- 技术失败原因已降级处理：{reason}。\n"
            "- 工具失败不等于公司没有相关数据。\n\n"
            "### 后续观察\n\n"
            "- 可以稍后重试，或补充明确股票代码、市场和具体问题维度。\n\n"
            "### 资料来源与可信度\n\n"
            "- 证据不足：未获得可靠来源，本回答不能视为完整工具分析。\n\n"
            "_仅供研究参考，不构成投资建议。_"
        )

    async def run(self, message: str, context: SkillContext) -> SkillResult:
        events: list = []
        cards: list  = []

        await safe_emit(context.event_callback, "skill_started", {
            "skill_name": self.name,
            "skill_spec": self.name,
            "source": "skill_registry_fallback",
        })

        decision = self._routing_decision(message, context)
        if decision.action == "clarify":
            answer = self._clarification_answer(decision.reason)
            await safe_emit(context.event_callback, "skill_completed", {
                "skill_name": self.name,
                "ok": True,
                "tools_used": [],
                "cards_count": 0,
                "source": "skill_registry_fallback",
            })
            return SkillResult(
                ok=True,
                skill_name=self.name,
                answer=answer,
                tool_events=[],
                cards=cards,
                metadata={"routing_decision": {"action": decision.action, "reason": decision.reason}},
            )

        # ── Route through FinancialAgent for real tool calls + streaming ──────
        try:
            from app.agents.financial_agent import FinancialAgent
            effective_query = decision.effective_query

            agent = FinancialAgent()
            response = await agent.run(
                query=effective_query,
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
            answer = await self._run_rag_fallback(
                message=decision.effective_query,
                context=context,
                events=events,
                failure_reason=self._sanitize_fallback_error(exc),
            )

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
            metadata={"routing_decision": {"action": decision.action, "reason": decision.reason}},
        )

    async def _run_rag_fallback(self, message: str, context: SkillContext, events: list, failure_reason: str = "") -> str:
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

        if not self._has_reliable_evidence(events, rag_docs_for_llm):
            return self._no_evidence_fallback_answer(message, failure_reason or "financial_agent_failed")

        try:
            from app.agents.chat_llm_answerer import generate_answer
            answer = await generate_answer(
                user_message=message,
                tool_results=self._fallback_evidence_from_events(events),
                rag_documents=rag_docs_for_llm,
                output_language=context.output_language,
                timeout_seconds=28.0,
                memory_context=context.memory_context,  # C32.1.1
                data_quality=self._fallback_data_quality(events, rag_docs_for_llm),
                fallback_mode=True,
            )
            if data_limited:
                answer = answer.rstrip() + "\n\n> **数据说明：** 本次回答基于现有参考资料，部分实时工具数据不可用，结论仅供参考。"
        except Exception as exc:
            log.warning("GeneralFinancialAnswerSkill: DeepSeek failed: %s", exc)
            answer = (
                "### 研究摘要\n\n"
                "当前研究数据获取受限，只能提供有限信息下的研究摘要，不能补充具体股票事实或数字。\n\n"
                "### 关键依据\n\n"
                "- 已成功取得的证据不足以形成完整分析。\n\n"
                "### 风险与不确定性\n\n"
                "- 工具或生成服务异常，不代表公司没有相关数据。\n\n"
                "### 后续观察\n\n"
                "- 请稍后重试，或指定具体股票代码、市场和问题维度。\n\n"
                "### 资料来源与可信度\n\n"
                "- 证据不足，可信度低。\n\n"
                "_仅供研究参考，不构成投资建议。_"
            )
        return answer
