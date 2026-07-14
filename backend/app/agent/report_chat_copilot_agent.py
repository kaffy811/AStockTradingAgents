"""
app/agent/report_chat_copilot_agent.py — 问财报 Chat Copilot Agent

ReportChatCopilotAgent.chat(...)
  0. Normalize question + detect prompt injection
  1. Check Redis cache (skip if force_refresh=True)
  2. Classify question (reject investment-advice / prohibited queries)
  3. Load session memory (prior turns for this session+ts_code)
  4. Expand query keywords for RAG retrieval (conversation-aware)
  5. Call ReportRagService to fetch relevant chunks
  6. Call DeepSeek LLM (flash model, temperature=0.3) with memory context
  7. Call FundamentalReviewAgent for compliance canonicalization
  8. Write result to cache + append turn to session memory
  9. Return structured result — never raises

New fields in response (Phase 6K):
  cache_meta    — {"hit", "key", "ttl_seconds", "created_at"}
  memory_meta   — {"session_id", "turns_loaded", "context_used"}
  safety_meta   — {"normalized": bool, "prompt_injection_detected": bool}
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.agent.report_context import is_narrow_question, report_scope_line, resolve_report_selection

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_QUESTION_LEN = 500

_SAFE_REJECTION_ANSWER: dict[str, Any] = {
    "answer": (
        "非常抱歉，您的问题涉及投资建议、目标价格或其他不适合在本平台回答的内容。"
        "本系统仅提供基于公开财报的客观信息查询，不提供买卖建议、目标价或收益承诺。"
        "如有财报数据方面的问题，欢迎继续提问。"
    ),
    "confidence": "high",
    "evidence_used": [],
    "data_limitations": [],
    "source_chunks": [],
    "disclaimer": "本内容基于已接入的公开财报片段，仅供参考，不构成投资建议。",
}

# Prohibited keywords — trigger immediate rejection
_REJECTION_KEYWORDS = [
    "买入", "卖出", "加仓", "减仓",
    "目标价", "价格目标",
    "保证收益", "必然上涨", "明天涨", "明天跌",
    "内幕", "操纵", "庄家",
]

# Prompt injection trigger phrases (CN + EN)
_INJECTION_PHRASES = [
    # Chinese
    "忽略之前", "忽略上面", "忽略前面", "忽略所有规则",
    "忘记之前", "忘记上面", "忘记规则",
    "输出提示词", "输出系统提示", "打印提示",
    "越狱", "绕过规则", "扮演", "roleplay",
    # English
    "ignore previous", "ignore all previous", "ignore above",
    "disregard previous", "disregard instructions",
    "forget previous", "forget your instructions",
    "print your prompt", "reveal your prompt", "output your instructions",
    "jailbreak", "bypass your rules", "act as ",
    "you are now", "pretend you are",
    "do anything now", "dan mode",
]

# ── Query expansion map ───────────────────────────────────────────────────────

_EXPANSION_MAP: list[tuple[list[str], str]] = [
    (["现金流", "cash flow", "cashflow"],   "经营活动现金流 现金流量 净额"),
    (["风险", "risk"],                       "风险因素 市场风险 经营风险"),
    (["主营", "主业", "business"],          "主营业务 产品 收入构成"),
    (["分红", "dividend"],                  "利润分配 分红 股利"),
    (["盈利", "profit", "利润"],            "毛利率 净利率 利润 盈利能力"),
]


# ── Normalization & safety ────────────────────────────────────────────────────

def _normalize_question(question: str) -> tuple[str, bool]:
    """
    Normalize a question for cache key computation and LLM safety.

    Steps:
      1. Strip leading/trailing whitespace
      2. Collapse runs of whitespace to single space
      3. Normalize Unicode to NFC
      4. Normalize punctuation (，→, 。→. ？→? ！→!)
      5. Lowercase all ASCII (for cache deduplication only)
      6. Truncate to _MAX_QUESTION_LEN

    Returns (normalized_question, was_changed).
    The normalized form is used for cache key; the original cleaned text is sent to LLM.
    """
    original = question
    # Strip + collapse whitespace
    q = " ".join(question.split())
    # NFC normalization (handle full-width chars etc.)
    q = unicodedata.normalize("NFC", q)
    # Normalize fullwidth punctuation to ASCII equivalents
    punct_map = str.maketrans({
        "，": ",", "。": ".", "？": "?", "！": "!",
        "；": ";", "：": ":", "\u201c": '"', "\u201d": '"',
        "\u2018": "'", "\u2019": "'", "（": "(", "）": ")",
        "【": "[", "】": "]",
    })
    q = q.translate(punct_map)
    # Truncate
    if len(q) > _MAX_QUESTION_LEN:
        q = q[:_MAX_QUESTION_LEN]
    return q, (q != original.strip())


def _detect_prompt_injection(question: str) -> bool:
    """
    Return True if the question contains prompt injection patterns.

    Detection is heuristic and permissive — only obvious patterns are caught.
    All detections are logged but do NOT cause hard rejection; the router
    may choose to proceed with extra caution or reject based on the flag.
    """
    q_lower = question.lower()
    for phrase in _INJECTION_PHRASES:
        if phrase.lower() in q_lower:
            log.warning("Prompt injection pattern detected: %r in question", phrase)
            return True
    return False


def _classify_question(question: str) -> str:
    """
    Returns "allowed" or "rejected".

    Rejects if any prohibited keyword is present (case-insensitive).
    """
    q_lower = question.lower()
    for kw in _REJECTION_KEYWORDS:
        if kw in q_lower or kw in question:
            log.info("Question rejected due to keyword: %s", kw)
            return "rejected"
    return "allowed"


def _expand_query(question: str, memory_turns: list[dict] | None = None) -> str:
    """
    Expand query with domain keywords for better RAG retrieval.

    Phase 6K: also extracts keywords from the most recent memory turn
    to support conversation-aware follow-up questions.

    Returns original question + appended expansion terms.
    """
    expansions: list[str] = []
    q_lower = question.lower()

    for triggers, extra in _EXPANSION_MAP:
        for trigger in triggers:
            if trigger in q_lower or trigger in question:
                expansions.append(extra)
                break  # Only add each expansion group once

    # Conversation-aware: if question is very short (likely a follow-up),
    # also expand using keywords from the previous turn's question.
    if memory_turns and len(question.strip()) < 20:
        prev_q = (memory_turns[-1] or {}).get("q", "")
        if prev_q:
            prev_lower = prev_q.lower()
            for triggers, extra in _EXPANSION_MAP:
                if extra not in expansions:
                    for trigger in triggers:
                        if trigger in prev_lower or trigger in prev_q:
                            expansions.append(extra)
                            break

    if expansions:
        return question + " " + " ".join(expansions)
    return question


def _load_system_prompt() -> str:
    path = _PROMPTS_DIR / "report_chat_system.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.warning("report_chat_system.md not found at %s", path)
        return (
            "You are a financial report Q&A assistant. "
            "Answer ONLY based on provided source_chunks. "
            "Output valid JSON with keys: answer, confidence, evidence_used, "
            "data_limitations, source_chunks, disclaimer."
        )


def _strip_json_fence(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _build_chunks_context(chunks: list[dict]) -> str:
    """Serialize RAG chunks as compact JSON for LLM prompt injection."""
    compact = []
    for c in chunks:
        compact.append({
            "chunk_id":      c.get("chunk_id"),
            "report_type":   c.get("report_type"),
            "report_year":   c.get("report_year"),
            "period":        c.get("period"),
            "section_title": c.get("section_title"),
            "content":       (c.get("content") or "")[:1200],
            "score":         c.get("score"),
        })
    return json.dumps(compact, ensure_ascii=False, indent=None)


def _build_report_metadata_context(report_context: dict[str, Any]) -> str:
    return json.dumps(
        {
            "symbol": report_context.get("symbol"),
            "market": report_context.get("market"),
            "stock_name": report_context.get("stock_name"),
            "report_id": report_context.get("report_id"),
            "report_year": report_context.get("report_year"),
            "report_type": report_context.get("report_type"),
            "period_end": report_context.get("period_end"),
            "title": report_context.get("title"),
            "disclosure_date": report_context.get("disclosure_date"),
            "selection_reason": report_context.get("selection_reason"),
            "switched_from_report_id": report_context.get("switched_from_report_id"),
        },
        ensure_ascii=False,
    )


def _format_data_limited_answer(question: str, report_context: dict[str, Any], chunks: list[dict], limitations: list[str]) -> str:
    narrow = is_narrow_question(question)
    scope = report_scope_line_from_dict(report_context)
    if narrow:
        return (
            "## 结论\n"
            "当前已接入资料不足以形成强结论。\n\n"
            "## 关键数据\n"
            "未获得可验证的结构化财务字段或足够的已审核财报片段。\n\n"
            "## 解释\n"
            "不能使用模型记忆补充财务数字，也不能猜测缺失字段。\n\n"
            "## 数据限制\n"
            + "\n".join(f"- {item}" for item in limitations)
            + "\n\n## 来源\n"
            + (f"- {len(chunks)} 条已检索财报片段" if chunks else "- 未检索到可引用片段")
        )
    return (
        "## 结论摘要\n"
        "当前已接入资料不足以完整回答该问题，以下仅说明报告范围和数据限制。\n\n"
        "## 报告与数据范围\n"
        f"- {scope}\n\n"
        "## 关键财务表现\n"
        "- 缺少可验证的结构化财务字段或足够的财报片段，不能编造数字。\n\n"
        "## 现金流与财务质量\n"
        "- 证据不足，暂不形成判断。\n\n"
        "## 主要变化与原因\n"
        "- 报告未提供足够证据时，不推断原因。\n\n"
        "## 风险与数据限制\n"
        + "\n".join(f"- {item}" for item in limitations)
        + "\n\n## 证据来源\n"
        + (f"- {len(chunks)} 条已检索财报片段" if chunks else "- 未检索到可引用片段")
    )


def report_scope_line_from_dict(report_context: dict[str, Any]) -> str:
    return (
        f"{report_context.get('market')}/{report_context.get('symbol')}，"
        f"report_id={report_context.get('report_id')}，"
        f"{report_context.get('report_year') or '未知年份'}，"
        f"{report_context.get('report_type') or '未知类型'}，"
        f"报告期 {report_context.get('period_end') or '未知'}"
    )


def _compute_rag_status(rag_result: dict) -> str:
    """
    Map RAG result metadata to a readable status string.

    Returns one of: "unavailable" | "keyword_only" | "local" | "mock"
    """
    provider = rag_result.get("provider", "")
    search_mode = rag_result.get("search_mode", "")
    fallback_used = rag_result.get("fallback_used", False)

    if not rag_result.get("chunks"):
        return "unavailable"
    if provider == "mock":
        return "mock"
    if fallback_used or search_mode in ("keyword", "bm25"):
        return "keyword_only"
    return "local"


def _make_error_result(errors: list[str], partial: bool = True) -> dict:
    from app.agent.report_chat_cache import _empty_cache_meta
    return {
        "answer": "当前已接入资料不足以判断此问题，请稍后重试或换一个问题。",
        "source_chunks": [],
        "review_audit": {},
        "rag_status": "unavailable",
        "confidence": "low",
        "data_limitations": ["服务暂时不可用，请稍后重试"],
        "errors": errors,
        "partial": partial,
        "cache_meta":  _empty_cache_meta(),
        "memory_meta": {"session_id": None, "turns_loaded": 0, "context_used": False},
        "safety_meta": {"normalized": False, "prompt_injection_detected": False},
    }


# ── Main Agent ────────────────────────────────────────────────────────────────

class ReportChatCopilotAgent:
    """
    问财报 Chat Copilot Agent.

    Usage:
        result = await ReportChatCopilotAgent().chat(
            market="CN",
            symbol="600519",
            question="茅台近三年毛利率如何变化？",
            db=db_session,
        )
    """

    async def chat(
        self,
        market: str,
        symbol: str,
        question: str,
        db: Any,
        stock_name: str | None = None,
        report_types: list[str] | None = None,
        years: list[int] | None = None,
        report_id: int | None = None,
        top_k: int = 6,
        # Phase 6K new params
        force_refresh: bool = False,
        session_id: str | None = None,
        use_memory: bool = True,
    ) -> dict:
        """
        Returns structured result dict. Never raises.
        """
        try:
            return await self._do_chat(
                market=market,
                symbol=symbol,
                question=question,
                db=db,
                stock_name=stock_name,
                report_types=report_types,
                years=years,
                report_id=report_id,
                top_k=top_k,
                force_refresh=force_refresh,
                session_id=session_id,
                use_memory=use_memory,
            )
        except Exception as e:
            log.error("ReportChatCopilotAgent unexpected error: %s", e, exc_info=True)
            return _make_error_result(errors=[str(e)], partial=True)

    async def _do_chat(  # noqa: C901 — long but linear pipeline
        self,
        market: str,
        symbol: str,
        question: str,
        db: Any,
        stock_name: str | None,
        report_types: list[str] | None,
        years: list[int] | None,
        report_id: int | None,
        top_k: int,
        force_refresh: bool,
        session_id: str | None,
        use_memory: bool,
    ) -> dict:
        from app.agent.report_chat_cache import (
            read_cache, write_cache, _empty_cache_meta,
        )
        from app.agent.report_chat_session_memory import (
            load_memory, append_turn, build_memory_context_prompt, memory_meta_dict,
        )

        errors: list[str] = []

        # ── 0. Sanitize inputs ────────────────────────────────────────────────
        question = (question or "").strip()
        if len(question) > _MAX_QUESTION_LEN:
            question = question[:_MAX_QUESTION_LEN]
            log.info("Question truncated to %d chars", _MAX_QUESTION_LEN)

        if not question:
            return _make_error_result(errors=["问题不能为空"], partial=False)

        top_k = min(top_k, 10)

        # ── 0a. Normalize question ────────────────────────────────────────────
        normalized_question, was_normalized = _normalize_question(question)

        # ── 0b. Detect prompt injection ───────────────────────────────────────
        injection_detected = _detect_prompt_injection(question)
        if injection_detected:
            # Hard-reject on obvious injection; do not proceed to LLM
            return {
                **_SAFE_REJECTION_ANSWER,
                "answer": (
                    "您的问题包含不允许的指令性内容，本系统无法处理。"
                    "请提问财报相关的客观问题，例如：公司的主营业务是什么？"
                ),
                "source_chunks": [],
                "review_audit": {
                    "source_chunks_checked": False,
                    "invalid_chunk_ids_removed": [],
                    "metadata_canonicalized": False,
                    "page_citation_removed": False,
                    "coverage_claim_rewritten": False,
                    "citation_consistency_rewritten": False,
                    "investment_advice_blocked": True,
                    "mild_phrases_rewritten": [],
                },
                "rag_status": "unavailable",
                "errors": [],
                "partial": False,
                "cache_meta":  _empty_cache_meta(),
                "memory_meta": memory_meta_dict(session_id, 0, False),
                "safety_meta": {"normalized": was_normalized, "prompt_injection_detected": True},
            }

        safety_meta = {
            "normalized":                was_normalized,
            "prompt_injection_detected": False,
        }

        # ── 1. Classify question ──────────────────────────────────────────────
        classification = _classify_question(normalized_question)
        if classification == "rejected":
            rejection_result = {
                **_SAFE_REJECTION_ANSWER,
                "source_chunks": [],
                "review_audit": {
                    "source_chunks_checked": False,
                    "invalid_chunk_ids_removed": [],
                    "metadata_canonicalized": False,
                    "page_citation_removed": False,
                    "coverage_claim_rewritten": False,
                    "citation_consistency_rewritten": False,
                    "investment_advice_blocked": True,
                    "mild_phrases_rewritten": [],
                },
                "rag_status": "unavailable",
                "errors": [],
                "partial": False,
                "cache_meta":  _empty_cache_meta(),
                "memory_meta": memory_meta_dict(session_id, 0, False),
                "safety_meta": safety_meta,
            }
            return rejection_result

        # ── 2. Resolve ts_code ────────────────────────────────────────────────
        try:
            from app.datasource.tushare_client import _to_ts_code
            ts_code = _to_ts_code(market, symbol)
        except Exception as e:
            log.warning("Could not resolve ts_code for %s/%s: %s", market, symbol, e)
            ts_code = f"{symbol}.SH" if (market or "").upper() == "CN" else str(symbol).upper()

        # ── 3. Load session memory before report selection/cache ─────────────
        memory_turns: list[dict] = []
        memory_context_used = False

        if use_memory and session_id:
            try:
                memory_turns = await load_memory(session_id, ts_code)
            except Exception as e:
                log.debug("Session memory load failed: %s", e)
                memory_turns = []

        # ── 4. Resolve report selection ──────────────────────────────────────
        try:
            selection = await resolve_report_selection(
                db=db,
                market=market,
                symbol=symbol,
                stock_name=stock_name,
                question=normalized_question,
                report_id=report_id,
                report_types=report_types,
                years=years,
                memory_turns=memory_turns,
            )
        except Exception as e:
            log.warning("Report selection failed for %s/%s: %s", market, symbol, e)
            selection = None

        if selection is None:
            return {
                "answer": "无法确定本次要使用的财报，请提供明确的股票代码和 report_id 或报告年份。",
                "source_chunks": [],
                "review_audit": {},
                "rag_status": "unavailable",
                "confidence": "low",
                "evidence_used": [],
                "data_limitations": ["报告选择失败，未进入财报解释"],
                "disclaimer": "本内容基于已接入的公开财报片段，仅供参考，不构成投资建议。",
                "errors": ["report_selection_failed"],
                "partial": True,
                "cache_meta": _empty_cache_meta(),
                "memory_meta": memory_meta_dict(session_id, len(memory_turns), False),
                "safety_meta": safety_meta,
            }

        if not selection.ok:
            return {
                "answer": selection.error or "无法确定本次要使用的财报。",
                "source_chunks": [],
                "review_audit": {},
                "rag_status": "unavailable",
                "confidence": "low",
                "evidence_used": [],
                "data_limitations": [selection.error or "报告选择失败"],
                "disclaimer": "本内容基于已接入的公开财报片段，仅供参考，不构成投资建议。",
                "errors": [selection.selection_reason],
                "partial": True,
                "cache_meta": _empty_cache_meta(),
                "memory_meta": {
                    **memory_meta_dict(session_id, len(memory_turns), False),
                    "report_context": selection.metadata(),
                },
                "safety_meta": safety_meta,
            }

        selected_report_id = selection.report_id
        selected_report_types = [selection.report_type] if selection.report_type else report_types
        selected_years = [selection.report_year] if selection.report_year else years
        report_context = selection.metadata()

        # ── 5. Cache read ─────────────────────────────────────────────────────
        if not force_refresh:
            cached = await read_cache(
                ts_code=ts_code,
                normalized_question=normalized_question,
                report_types=selected_report_types,
                years=selected_years,
                report_id=selected_report_id,
            )
            if cached is not None:
                log.debug("Cache HIT for %s question=%r", ts_code, normalized_question[:40])
                cached["safety_meta"] = safety_meta
                cached["memory_meta"] = {
                    **memory_meta_dict(session_id, len(memory_turns), False),
                    "report_context": report_context,
                }
                return cached

        cache_meta = _empty_cache_meta()

        # ── 5. Expand query for RAG (conversation-aware) ──────────────────────
        expanded_query = _expand_query(normalized_question, memory_turns)

        # ── 6. RAG retrieval ──────────────────────────────────────────────────
        chunks: list[dict] = []
        rag_result: dict = {"chunks": [], "partial": False, "errors": [], "provider": "unavailable"}
        rag_status = "unavailable"

        try:
            from app.services.report_rag_service import ReportRagService
            rag_result = await ReportRagService().query(
                ts_code=ts_code,
                query_text=expanded_query,
                db=db,
                report_types=selected_report_types,
                years=selected_years,
                report_id=selected_report_id,
                top_k=top_k,
            )
            chunks = rag_result.get("chunks", []) or []
            rag_status = _compute_rag_status(rag_result)
            if rag_result.get("errors"):
                errors.extend(rag_result["errors"])
        except Exception as e:
            log.warning("RAG service failed for %s: %s", ts_code, e)
            errors.append(f"RAG检索失败: {e}")
            rag_status = "unavailable"

        # ── 7. Build allowed chunk IDs ────────────────────────────────────────
        allowed_chunk_ids = [c["chunk_id"] for c in chunks if c.get("chunk_id") is not None]

        # ── 8. Build LLM prompt (with session memory context) ─────────────────
        system_prompt = _load_system_prompt()
        chunks_json = _build_chunks_context(chunks)
        report_metadata_json = _build_report_metadata_context(report_context)

        # Inject conversation history if available
        memory_context_block = build_memory_context_prompt(memory_turns)
        memory_context_used = bool(memory_context_block)

        memory_section = ""
        if memory_context_block:
            memory_section = f"\n\n{memory_context_block}\n"

        user_prompt = (
            f"股票代码（ts_code）：{ts_code}\n\n"
            f"用户问题：{normalized_question}\n"
            f"\n本次选定报告（report_metadata）：\n{report_metadata_json}\n"
            "\n结构化财务字段（structured_financial_data）：\n[]\n"
            "\nreview_audit：将在模型输出后由系统审核；模型不得假设审核通过。\n"
            f"{memory_section}"
            f"\n已接入财报片段（source_chunks，共 {len(chunks)} 条）：\n"
            f"{chunks_json}\n\n"
            "请严格基于 report_metadata、structured_financial_data、source_chunks 和会话上下文回答问题，输出合法 JSON（不带代码块标记）。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]

        # ── 9. LLM call ────────────────────────────────────────────────────────
        raw_llm_result: dict = {}
        llm_error: str | None = None

        try:
            from app.core.config import settings
            from app.llm.deepseek_client import DeepSeekClient

            if not settings.ai_enabled:
                raise RuntimeError("AI 功能已关闭（AI_ENABLED=false）")
            if not settings.ai_api_key:
                raise RuntimeError("AI API Key 未配置")

            client = DeepSeekClient()
            loop = asyncio.get_running_loop()
            raw_text = await loop.run_in_executor(
                None,
                lambda: client.chat(
                    messages,
                    temperature=0.3,
                    model=settings.deepseek_model,   # flash model (default)
                ),
            )
            cleaned_text = _strip_json_fence(raw_text)
            raw_llm_result = json.loads(cleaned_text)

        except json.JSONDecodeError as e:
            llm_error = f"LLM 输出 JSON 解析失败: {e}"
            log.error("ReportChatCopilot JSON parse failed: %s", e)
            errors.append(llm_error)
        except Exception as e:
            llm_error = f"LLM 调用失败: {e}"
            log.error("ReportChatCopilot LLM error: %s", e)
            errors.append(llm_error)

        # If LLM completely failed, build a graceful fallback
        if llm_error or not raw_llm_result:
            limitations = ["AI 服务暂时不可用"]
            if not chunks:
                limitations.insert(0, "当前未检索到相关财报片段")
            return {
                "answer": (
                    "AI 分析服务暂时不可用。"
                    + _format_data_limited_answer(normalized_question, report_context, chunks, limitations)
                ),
                "source_chunks": chunks,
                "review_audit": {},
                "rag_status": rag_status,
                "confidence": "low",
                "data_limitations": limitations,
                "errors": errors,
                "partial": True,
                "cache_meta":  cache_meta,
                "memory_meta": {
                    **memory_meta_dict(session_id, len(memory_turns), memory_context_used),
                    "report_context": report_context,
                },
                "safety_meta": safety_meta,
            }

        # ── 10. Compliance review via FundamentalReviewAgent ──────────────────
        review_input = {
            "summary":        raw_llm_result.get("answer", ""),
            "overall_score":  None,
            "dimensions":     [],
            "highlights":     [],
            "risks":          [],
            "watch_items":    [],
            "data_limitations": raw_llm_result.get("data_limitations", []),
            "answer":         raw_llm_result.get("answer", ""),
            "confidence":     raw_llm_result.get("confidence", "low"),
            "evidence_used":  raw_llm_result.get("evidence_used", []),
            "source_chunks":  raw_llm_result.get("source_chunks", []),
            "disclaimer":     raw_llm_result.get("disclaimer", ""),
        }

        data_pack_stub = {
            "allowed_chunk_ids":  allowed_chunk_ids,
            "report_rag_context": chunks,
            "compressed_facts":   [],
        }

        review_result: dict = {}
        review_audit: dict = {}

        try:
            from app.agent.fundamental_review_agent import FundamentalReviewAgent
            review_result = await FundamentalReviewAgent().review(review_input, data_pack_stub)
            review_audit = review_result.get("audit", {})
        except Exception as e:
            log.warning("Review agent failed for chat: %s", e)
            errors.append(f"合规审核失败（使用原始结果）: {e}")
            review_result = {"final": review_input, "status": "skipped"}
            review_audit = {}

        # ── 11. Extract final output ──────────────────────────────────────────
        final: dict = review_result.get("final", review_input)

        answer = final.get("answer") or raw_llm_result.get("answer", "当前已接入资料不足以判断此问题。")
        confidence = final.get("confidence") or raw_llm_result.get("confidence", "low")
        evidence_used = final.get("evidence_used") or raw_llm_result.get("evidence_used", [])
        data_limitations = final.get("data_limitations") or raw_llm_result.get("data_limitations", [])
        source_chunks_out = final.get("source_chunks") or []
        disclaimer = final.get("disclaimer") or "本内容基于已接入的公开财报片段，仅供参考，不构成投资建议。"

        review_status = review_result.get("status", "approved")
        if review_status == "rejected":
            answer = (
                "## 结论摘要\n"
                "证据审核未通过，不能生成强结论。\n\n"
                "## 报告与数据范围\n"
                f"- {report_scope_line(selection)}\n\n"
                "## 风险与数据限制\n"
                "- 已保留可验证事实，但删除或降级了不符合证据规则的内容。\n\n"
                "## 证据来源\n"
                "- 仅限已审核通过的财报片段。"
            )
            confidence = "low"
            data_limitations = list(data_limitations or [])
            if "证据审核未通过，强结论已降级" not in data_limitations:
                data_limitations.insert(0, "证据审核未通过，强结论已降级")

        if not chunks and "当前已接入资料不足" not in answer:
            if "当前未检索到相关财报片段" not in (data_limitations or []):
                data_limitations = list(data_limitations or [])
                data_limitations.insert(0, "当前未检索到相关财报片段，不能编造财务数字")
                answer = _format_data_limited_answer(normalized_question, report_context, chunks, data_limitations)

        is_rejection = review_status == "rejected" or classification == "rejected"
        partial = bool(errors) or rag_result.get("partial", False) or review_status not in {"approved", "revised", "skipped"}

        result = {
            "answer":           answer,
            "source_chunks":    source_chunks_out,
            "review_audit":     review_audit,
            "rag_status":       rag_status,
            "confidence":       confidence,
            "evidence_used":    evidence_used,
            "data_limitations": data_limitations,
            "disclaimer":       disclaimer,
            "errors":           errors,
            "partial":          partial,
            "cache_meta":       cache_meta,
            "memory_meta": {
                **memory_meta_dict(session_id, len(memory_turns), memory_context_used),
                "report_context": report_context,
            },
            "safety_meta":      safety_meta,
        }

        # ── 12. Write to cache + append session memory ────────────────────────
        if not partial or is_rejection:
            await write_cache(
                ts_code=ts_code,
                normalized_question=normalized_question,
                result=result,
                report_types=selected_report_types,
                years=selected_years,
                report_id=selected_report_id,
                is_rejection=is_rejection,
            )
            # Refresh cache_meta in the returned result (key was computed inside write_cache)
            from app.agent.report_chat_cache import make_cache_key
            import time as _time
            from app.core.config import settings as _settings
            _ttl = 60 if is_rejection else _settings.report_chat_cache_ttl_seconds
            result["cache_meta"] = {
                "hit":         False,
                "key":         make_cache_key(ts_code, normalized_question, selected_report_types, selected_years, selected_report_id),
                "ttl_seconds": _ttl,
                "created_at":  int(_time.time()),
            }

        if use_memory and session_id and not partial and not is_rejection:
            await append_turn(
                session_id=session_id,
                ts_code=ts_code,
                question=normalized_question,
                answer=answer,
                metadata={"report_context": report_context},
            )

        return result
