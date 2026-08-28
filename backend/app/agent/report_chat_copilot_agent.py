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
import hashlib
import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

from app.agent.report_context import (
    is_narrow_question,
    latest_memory_report_id,
    report_scope_line,
    resolve_report_selection,
)

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_QUESTION_LEN = 500
_REPORT_CHAT_OVERALL_TIMEOUT_SECONDS = 120.0
_REPORT_SELECTION_TIMEOUT_SECONDS = 12.0
_RAG_QUERY_TIMEOUT_SECONDS = 8.0
_LLM_SYNTHESIS_TIMEOUT_SECONDS = 90.0
_REVIEW_TIMEOUT_SECONDS = 5.0
_EVIDENCE_CACHE_TTL_SECONDS = 20 * 60
_SELECTION_CACHE_TTL_SECONDS = 45 * 60
_MAX_EVIDENCE_CHARS = 6000
_MAX_CHUNK_CHARS = 1200
_REPORT_CHAT_FAST_PATH_VERSION = "d4_2_v1"

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


def _extract_response_text(value: Any) -> str:
    """Extract assistant text from common LLM/agent response shapes."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("answer", "final_answer", "content", "response", "text", "message", "result"):
            nested = value.get(key)
            text = _extract_response_text(nested)
            if text:
                return text
        choices = value.get("choices")
        if isinstance(choices, list) and choices:
            text = _extract_response_text(choices[0])
            if text:
                return text
        return ""
    if hasattr(value, "content"):
        text = _extract_response_text(getattr(value, "content"))
        if text:
            return text
    if hasattr(value, "text"):
        text = _extract_response_text(getattr(value, "text"))
        if text:
            return text
    if hasattr(value, "choices"):
        text = _extract_response_text({"choices": getattr(value, "choices")})
        if text:
            return text
    return ""


def _normalize_llm_json_result(value: Any) -> dict:
    """Return a dict with canonical answer when the LLM shape is non-standard."""
    if isinstance(value, dict):
        normalized = dict(value)
        if not str(normalized.get("answer") or "").strip():
            extracted = _extract_response_text(normalized)
            if extracted:
                normalized["answer"] = extracted
        return normalized
    extracted = _extract_response_text(value)
    return {"answer": extracted} if extracted else {}


def _ms_since(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _hash_payload(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _selection_cache_key(
    *,
    ts_code: str,
    normalized_question: str,
    report_id: int | None,
    report_types: list[str] | None,
    years: list[int] | None,
    memory_report_id: int | None,
) -> str:
    return "report_chat:selection:{ver}:{ts}:{fingerprint}".format(
        ver=_REPORT_CHAT_FAST_PATH_VERSION,
        ts=ts_code,
        fingerprint=_hash_payload({
            "q": normalized_question,
            "rid": report_id,
            "rt": report_types or [],
            "yr": years or [],
            "mem": memory_report_id,
        }),
    )


def _evidence_cache_key(
    *,
    ts_code: str,
    report_id: int | None,
    normalized_question: str,
    top_k: int,
) -> str:
    return "report_chat:evidence:{ver}:{ts}:{rid}:{qh}:{top_k}".format(
        ver=_REPORT_CHAT_FAST_PATH_VERSION,
        ts=ts_code,
        rid=report_id or "none",
        qh=_hash_payload({"q": normalized_question}),
        top_k=top_k,
    )


async def _cache_get_json(key: str) -> Any | None:
    try:
        from app.services.cache_service import cache_service
        return await cache_service.get_json(key)
    except Exception:
        return None


async def _cache_set_json(key: str, value: Any, ttl: int) -> bool:
    try:
        from app.services.cache_service import cache_service
        return await cache_service.set_json(key, value, ttl)
    except Exception:
        return False


def _selection_from_metadata(metadata: dict[str, Any] | None):
    if not isinstance(metadata, dict) or not metadata.get("report_id"):
        return None
    from app.agent.report_context import ReportSelection
    return ReportSelection(
        report_id=int(metadata["report_id"]),
        symbol=str(metadata.get("symbol") or ""),
        market=str(metadata.get("market") or ""),
        ts_code=str(metadata.get("ts_code") or ""),
        stock_name=metadata.get("stock_name"),
        report_year=metadata.get("report_year"),
        report_type=metadata.get("report_type"),
        period_end=metadata.get("period_end"),
        title=metadata.get("title"),
        disclosure_date=metadata.get("disclosure_date"),
        selection_reason=str(metadata.get("selection_reason") or "cache_hit"),
        pdf_url=metadata.get("pdf_url"),
        source_url=metadata.get("source_url"),
        parsed=metadata.get("parsed"),
        rag_status=metadata.get("rag_status"),
        chunk_count=metadata.get("chunk_count"),
        switched_from_report_id=metadata.get("switched_from_report_id"),
        error=metadata.get("error"),
    )


def _is_pdf_question(question: str) -> bool:
    return bool(re.search(r"(pdf|PDF|链接|入口|在哪里|下载|官方)", question or ""))


def _is_indexed_report(report_context: dict[str, Any]) -> bool:
    rag_status = str(report_context.get("rag_status") or "").lower()
    return bool(report_context.get("parsed")) and rag_status in {"indexed", "embedded", "ready", "chunked"}


def _limit_evidence_chunks(chunks: list[dict], max_chars: int = _MAX_EVIDENCE_CHARS) -> list[dict]:
    limited: list[dict] = []
    used = 0
    for chunk in chunks or []:
        item = dict(chunk)
        content = str(item.get("content") or "")[:_MAX_CHUNK_CHARS]
        if not content.strip():
            continue
        if used + len(content) > max_chars:
            remaining = max(0, max_chars - used)
            if remaining < 160:
                break
            content = content[:remaining]
        item["content"] = content
        limited.append(item)
        used += len(content)
        if used >= max_chars:
            break
    return limited


def _evidence_chars(chunks: list[dict]) -> int:
    return sum(len(str(c.get("content") or "")) for c in chunks or [])


def _table_rows_aligned(text: str) -> bool:
    for block in re.findall(r"((?:\|[^\n]*\|\n?){2,})", text or ""):
        rows = [line for line in block.splitlines() if line.strip().startswith("|")]
        counts = [line.count("|") for line in rows]
        if counts and len(set(counts)) > 1:
            return False
    return True


def _answer_consistency_issues(answer: str, *, source_chunks_count: int) -> list[str]:
    issues: list[str] = []
    text = answer or ""
    if "需通过工具获取，此处不自行估算" in text or "归属于上市公司股东的（" in text:
        issues.append("PLACEHOLDER_LEAK")
    if source_chunks_count > 0 and "工具仅返回新闻标题" in text:
        issues.append("NEWS_ONLY_CONTRADICTION")
    if not _table_rows_aligned(text):
        issues.append("MARKDOWN_TABLE_MISALIGNED")
    if text.count("不构成投资建议") > 1:
        issues.append("DUPLICATE_DISCLAIMER")
    return issues


def _format_pdf_answer(report_context: dict[str, Any]) -> str:
    title = report_context.get("title") or "已选财务报告"
    year = report_context.get("report_year") or "未知年度"
    period = report_context.get("period_end") or "未知期间"
    url = report_context.get("pdf_url") or report_context.get("source_url")
    if url:
        return (
            f"## 官方 PDF\n"
            f"- 报告：{title}\n"
            f"- 年度/期间：{year} / {period}\n"
            f"- 官方 PDF：{url}\n\n"
            "该链接来自已持久化的官方报告 metadata，未重新触发下载、解析或索引。"
        )
    return (
        f"## 官方 PDF\n"
        f"- 报告：{title}\n"
        f"- 年度/期间：{year} / {period}\n"
        "- 当前已选报告没有可展示的官方 PDF 链接。"
    )


def _format_evidence_fallback_answer(
    *,
    question: str,
    report_context: dict[str, Any],
    chunks: list[dict],
    reason: str,
) -> str:
    title = report_context.get("title") or "已选财务报告"
    year = report_context.get("report_year") or "未知年度"
    period = report_context.get("period_end") or "未知期间"
    pdf_url = report_context.get("pdf_url") or report_context.get("source_url")
    lines = [
        "## 结论",
        f"自动总结未完成：{reason}。以下仅列出已检索到的报告证据，不能编造报告片段之外的数字或判断。",
        "",
        "## 报告范围",
        f"- 报告：{title}",
        f"- 年度/期间：{year} / {period}",
    ]
    if pdf_url:
        lines.append(f"- 官方 PDF：{pdf_url}")
    lines.extend(["", "## 关键数据"])
    if not chunks:
        lines.append("- 当前未检索到可引用的报告片段，不能使用模型记忆补充财务数字。")
    lines.extend(["", "## 已检索到的证据"])
    if not chunks:
        lines.append("- 当前未检索到可引用的报告片段。")
    for idx, chunk in enumerate(chunks[:6], 1):
        section = chunk.get("section_title") or f"片段 {chunk.get('chunk_id') or idx}"
        content = re.sub(r"\s+", " ", str(chunk.get("content") or "")).strip()
        if len(content) > 260:
            content = content[:260] + "…"
        page = ""
        if chunk.get("page_start"):
            page = f"（页码 {chunk.get('page_start')}）"
        lines.append(f"{idx}. {section}{page}：{content}")
    lines.extend([
        "",
        "## 数据来源说明",
        f"- 问题：{question}",
        f"- 证据片段数：{len(chunks)}",
    ])
    return "\n".join(lines)


async def _emit_report_stage(event_callback: Any, *, phase: str, title: str, status: str = "running") -> None:
    if not event_callback:
        return
    try:
        await event_callback("thinking_event", {
            "phase": phase,
            "title": title,
            "content": title,
            "status": status,
            "agent": "ReportChatCopilotAgent",
            "importance": "medium",
            "timestamp": None,
        })
    except Exception:
        pass


async def _query_company_v2_indexed_evidence(
    *,
    ts_code: str,
    symbol: str,
    report_context: dict[str, Any],
    query_text: str,
    top_k: int,
) -> dict[str, Any]:
    from app.services.company_v2_report_rag_retriever import company_v2_report_rag_retriever

    report_id = int(report_context.get("report_id"))
    report_year = report_context.get("report_year")
    raw = await asyncio.to_thread(
        company_v2_report_rag_retriever.retrieve,
        report_id=report_id,
        question=query_text,
        top_k=top_k,
        symbol=symbol or (ts_code or "").split(".")[0] or None,
        report_year=int(report_year) if report_year else None,
    )
    chunks: list[dict[str, Any]] = []
    for item in raw.get("chunks") or []:
        chunks.append({
            "chunk_id": item.get("chunk_id"),
            "report_id": item.get("report_id") or report_id,
            "ts_code": ts_code,
            "report_type": item.get("report_type") or report_context.get("report_type"),
            "report_year": item.get("report_year") or report_context.get("report_year"),
            "period": str(item.get("report_year") or report_context.get("period_end") or ""),
            "chunk_index": item.get("chunk_id"),
            "section_title": item.get("section_title"),
            "content": item.get("text_excerpt") or "",
            "score": item.get("score"),
            "score_detail": item.get("score_detail"),
            "page_start": item.get("page_start"),
            "page_end": item.get("page_end"),
            "source_url": item.get("source_url") or report_context.get("source_url") or report_context.get("pdf_url"),
            "has_embedding": bool((item.get("score_detail") or {}).get("embedding_score")),
        })
    return {
        "chunks": chunks,
        "partial": bool(raw.get("error_code")),
        "errors": [raw["error_code"]] if raw.get("error_code") else [],
        "search_mode": raw.get("retrieval_mode") or "company_v2_hybrid",
        "total": len(chunks),
        "fallback_used": False,
        "provider": "company_v2_report_rag",
        "selected_report_id": report_id,
    }


async def _query_indexed_report_db_evidence(
    *,
    db: Any,
    ts_code: str,
    report_context: dict[str, Any],
    query_text: str,
    top_k: int,
) -> dict[str, Any]:
    """Fast indexed-report path: bounded lexical DB fetch by report_id."""
    from sqlalchemy import or_, select
    from app.models.company_v2_report_rag import ReportRagChunk, ReportRagDocument

    report_id = int(report_context.get("report_id"))
    terms: list[str] = []
    if any(term in query_text for term in ("收入", "营收", "利润", "净利润", "业绩", "财务指标")):
        terms.extend(["营业收入", "净利润", "归属于上市公司股东", "主要会计数据", "主要财务指标"])
    if "风险" in query_text:
        terms = ["风险", "风险因素", "可能面对的风险"] + terms
    if "现金流" in query_text or "经营现金流" in query_text:
        terms = ["经营活动产生的现金流量净额", "现金流量", "经营活动"] + terms
    # Deduplicate while preserving order.
    terms = list(dict.fromkeys(terms))[:8]

    doc_stmt = (
        select(ReportRagDocument)
        .where(
            ReportRagDocument.report_id == report_id,
            ReportRagDocument.active_index == 1,
            ReportRagDocument.deleted_at.is_(None),
        )
        .order_by(ReportRagDocument.index_generation.desc())
    )
    doc = (await db.execute(doc_stmt)).scalars().first()
    if doc is None:
        return {
            "chunks": [],
            "partial": True,
            "errors": ["COMPANY_V2_INDEX_NOT_FOUND"],
            "search_mode": "indexed_db_lexical",
            "total": 0,
            "fallback_used": False,
            "provider": "indexed_report_db",
            "selected_report_id": report_id,
        }

    stmt = select(ReportRagChunk).where(
        ReportRagChunk.rag_document_id == int(doc.id),
        ReportRagChunk.report_id == report_id,
    )
    if terms:
        stmt = stmt.where(or_(*[ReportRagChunk.text.ilike(f"%{term}%") for term in terms]))
    stmt = stmt.order_by(ReportRagChunk.chunk_index).limit(max(1, min(int(top_k or 6), 8)))

    result = await db.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        fallback_stmt = (
            select(ReportRagChunk)
            .where(
                ReportRagChunk.rag_document_id == int(doc.id),
                ReportRagChunk.report_id == report_id,
            )
            .order_by(ReportRagChunk.chunk_index)
            .limit(max(1, min(int(top_k or 6), 8)))
        )
        rows = (await db.execute(fallback_stmt)).scalars().all()
    chunks: list[dict[str, Any]] = []
    for row in rows:
        content = str(row.text or "")
        chunks.append({
            "chunk_id": row.id,
            "report_id": row.report_id,
            "ts_code": ts_code,
            "report_type": doc.report_type,
            "report_year": doc.report_year,
            "period": report_context.get("period_end") or str(doc.report_year),
            "chunk_index": row.chunk_index,
            "section_title": row.section_title,
            "content": content[:_MAX_CHUNK_CHARS],
            "page_start": row.page_start,
            "page_end": row.page_end,
            "source_url": doc.source_url or report_context.get("source_url") or report_context.get("pdf_url"),
            "has_embedding": bool(row.embedding),
            "score": 0.55,
            "score_detail": {"keyword_terms": terms},
        })
    return {
        "chunks": chunks,
        "partial": False,
        "errors": [],
        "search_mode": "indexed_db_lexical",
        "total": len(chunks),
        "fallback_used": False,
        "provider": "indexed_report_db",
        "selected_report_id": report_id,
    }


def financial_evidence_compactor(
    chunks: list[dict],
    *,
    max_chars_per_chunk: int = 400,
    max_total_chars: int = 2000,
) -> list[dict]:
    """Compress RAG chunks for LLM prompt injection.

    Preserves numeric and financial sentences; removes PDF boilerplate.
    Targets ``max_total_chars`` total across all chunks so synthesis
    prompt stays under ~5 000 chars even with system prompt overhead.
    """
    import re as _re

    _NUM_RE = _re.compile(
        r"\d[\d,.，．]*[%％亿万元千百]?|\b\d+\.\d+\b|"
        r"营收|收入|利润|净利|毛利|现金流|每股|ROE|ROA|负债|资产|权益|"
        r"增长|同比|环比|上升|下降|增加|减少|revenue|profit|growth|cash|equity|eps",
        _re.IGNORECASE,
    )
    _BOILERPLATE_RE = _re.compile(
        r"（适用|□不适用|√适用|前瞻性陈述|不构成.{0,10}承诺|"
        r"是否存在被控股股东|是否存在违反规定|是否存在半数以上|"
        r"敬请投资者注意|本公司郑重提示|年度报告摘要",
        _re.IGNORECASE,
    )
    _SENT_RE = _re.compile(r"[。！？；;!?]|\n\n")

    def _compress(text: str, cap: int) -> str:
        if not text:
            return ""
        text = text.strip()
        # Always process through boilerplate/financial filter regardless of length.
        sentences = [s.strip() for s in _SENT_RE.split(text) if s.strip()]
        kept: list[str] = []
        total = 0
        for s in sentences:
            if _BOILERPLATE_RE.search(s):
                continue
            if _NUM_RE.search(s) and total + len(s) <= cap:
                kept.append(s)
                total += len(s)
        if not kept:
            # No financial sentences — keep all non-boilerplate content up to cap
            for s in sentences:
                if not _BOILERPLATE_RE.search(s) and total + len(s) <= cap:
                    kept.append(s)
                    total += len(s)
        if not kept:
            # Complete fallback: first `cap` chars of raw text
            return text[:cap]
        # Join and enforce hard cap (separator chars can push total slightly over)
        return ("。".join(kept))[:cap]

    per_chunk_cap = min(max_chars_per_chunk, max_total_chars // max(len(chunks), 1))
    result = []
    total_used = 0
    for c in chunks:
        raw = c.get("content") or ""
        remaining = max_total_chars - total_used
        cap = min(per_chunk_cap, remaining)
        if cap <= 0:
            break
        compressed = _compress(raw, cap)
        total_used += len(compressed)
        result.append({**c, "content": compressed})
    return result


def _build_local_evidence_context(
    chunks: list[dict],
) -> tuple[str, dict[str, dict]]:
    """Build LLM-safe evidence and a request-local resolver map.

    Database chunk identifiers stay exclusively in ``evidence_map``.  The
    serialized context exposes only stable labels scoped to this invocation.
    """
    model_evidence: list[dict] = []
    evidence_map: dict[str, dict] = {}
    for idx, chunk in enumerate(chunks, start=1):
        evidence_id = f"E{idx}"
        evidence_map[evidence_id] = chunk
        model_evidence.append({
            "evidence_id":  evidence_id,
            "report_type":  chunk.get("report_type"),
            "report_year":  chunk.get("report_year"),
            "period":       chunk.get("period"),
            "section":      chunk.get("section_title"),
            "content":      (chunk.get("content") or "")[:1200],
            "score":        chunk.get("score"),
        })
    return json.dumps(model_evidence, ensure_ascii=False, indent=None), evidence_map


def _strip_model_visible_chunk_metadata(value: Any) -> Any:
    """Return a model-facing copy without raw chunk locator fields."""
    if isinstance(value, dict):
        return {
            key: _strip_model_visible_chunk_metadata(item)
            for key, item in value.items()
            if "chunk_id" not in str(key).lower()
        }
    if isinstance(value, list):
        return [_strip_model_visible_chunk_metadata(item) for item in value]
    return value


def _resolve_local_citations(
    citations: Any,
    evidence_map: dict[str, dict],
) -> tuple[list[dict], dict]:
    """Resolve request-local evidence labels into canonical source chunks."""
    if citations is None:
        citations = []
    if not isinstance(citations, list):
        return [], {"valid": False, "reason": "citations_not_list", "invalid_ids": []}

    resolved: list[dict] = []
    invalid_ids: list[str] = []
    invalid_claim_ids: list[str] = []
    seen: set[str] = set()
    duplicate_ids: list[str] = []
    for citation in citations:
        if not isinstance(citation, dict):
            invalid_ids.append("<non-object>")
            continue
        evidence_id = str(citation.get("evidence_id") or "").strip()
        if not re.fullmatch(r"E[1-9]\d*", evidence_id) or evidence_id not in evidence_map:
            invalid_ids.append(evidence_id or "<missing>")
            continue
        if evidence_id in seen:
            duplicate_ids.append(evidence_id)
            continue
        seen.add(evidence_id)
        chunk = evidence_map[evidence_id]
        claim = str(citation.get("claim") or "").strip()[:500]
        if not claim:
            invalid_claim_ids.append(evidence_id)
            continue
        from app.agents.specialist_analysis_utils import validate_numeric_claims
        claim_evidence = " ".join(
            str(value or "")
            for value in (
                chunk.get("content"),
                chunk.get("report_year"),
                chunk.get("period"),
            )
        ).strip()
        claim_validation = validate_numeric_claims(
            claim,
            claim_evidence,
        )
        if not claim_validation["valid"]:
            invalid_claim_ids.append(evidence_id)
            continue
        resolved.append({
            "chunk_id": chunk.get("chunk_id"),
            "citation": claim,
        })

    valid = not invalid_ids and not duplicate_ids and not invalid_claim_ids
    return resolved, {
        "valid": valid,
        "reason": "ok" if valid else "invalid_evidence_reference",
        "invalid_ids": invalid_ids,
        "duplicate_ids": duplicate_ids,
        "invalid_claim_ids": invalid_claim_ids,
        "resolved_count": len(resolved),
    }


def _citation_metadata_leaks(answer: str, retrieved_chunk_ids: list[Any]) -> list[str]:
    """Find raw retrieved IDs only when used in citation/source context."""
    text = str(answer or "")
    leaks: list[str] = []
    for raw_id in retrieved_chunk_ids:
        if raw_id is None:
            continue
        chunk_id = str(raw_id)
        escaped = re.escape(chunk_id)
        patterns = (
            rf"(?i)(?:chunk(?:_id)?|source[_\s-]*chunk|citation|evidence|source|id)"
            rf"\s*[#:=：\(（\[]*\s*{escaped}(?!\d)",
            rf"(?:来源|引用(?:编号)?|证据(?:片段)?|片段|编号|ID)"
            rf"\s*[#:=：\(（\[]*\s*{escaped}(?!\d)",
            rf"第\s*{escaped}\s*(?:个|条)?\s*(?:证据|片段|引用)",
        )
        if any(re.search(pattern, text) for pattern in patterns):
            leaks.append(chunk_id)
    return leaks


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
        event_callback: Any = None,
        # Phase 6W-R1.1 Blocking-F: intent type for cache key separation
        intent_type: str = "analysis",
        trace_recorder: Any = None,
    ) -> dict:
        """
        Returns structured result dict. Never raises.

        *intent_type* is included in the Redis cache key to prevent locator
        answers from being served for analysis queries and vice versa.
        Values: ``"analysis"`` (default), ``"locator"``.
        """
        try:
            return await asyncio.wait_for(
                self._do_chat(
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
                    event_callback=event_callback,
                    intent_type=intent_type,
                    trace_recorder=trace_recorder,
                ),
                timeout=_REPORT_CHAT_OVERALL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            if trace_recorder is not None:
                await trace_recorder.fail_active("REPORT_AGENT_TIMEOUT")
            log.error("ReportChatCopilotAgent timed out for %s/%s", market, symbol)
            result = _make_error_result(errors=["REPORT_AGENT_TIMEOUT"], partial=True)
            result["status"] = "failed"
            result["error_code"] = "REPORT_AGENT_TIMEOUT"
            result["answer"] = "报告数据获取或总结生成超时，请稍后重试。"
            return result
        except Exception as e:
            if trace_recorder is not None:
                await trace_recorder.fail_active("REPORT_AGENT_UNEXPECTED_ERROR")
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
        event_callback: Any,
        intent_type: str = "analysis",
        trace_recorder: Any = None,
    ) -> dict:
        from app.agent.report_chat_cache import (
            read_cache, write_cache, _empty_cache_meta,
        )
        from app.agent.report_chat_session_memory import (
            load_memory, append_turn, build_memory_context_prompt, memory_meta_dict,
        )

        errors: list[str] = []
        total_start = time.perf_counter()
        timings: dict[str, int] = {
            "report_selection_ms": 0,
            "report_document_load_ms": 0,
            "rag_status_check_ms": 0,
            "vector_query_ms": 0,
            "lexical_query_ms": 0,
            "rerank_ms": 0,
            "chunk_fetch_ms": 0,
            "evidence_assembly_ms": 0,
            "llm_queue_ms": 0,
            "llm_first_token_ms": 0,
            "llm_total_ms": 0,
            "review_ms": 0,
            "persistence_ms": 0,
            "total_ms": 0,
        }
        perf_meta: dict[str, Any] = {
            "cache": {
                "final_answer": "bypass" if force_refresh else "miss",
                "selection": "miss",
                "evidence": "miss",
            },
            "timeout_layer": None,
            "retry_count": 0,
            "llm_model": None,
            "top_k_requested": top_k,
            "fast_path_version": _REPORT_CHAT_FAST_PATH_VERSION,
        }

        # ── 0. Sanitize inputs ────────────────────────────────────────────────
        question = (question or "").strip()
        if len(question) > _MAX_QUESTION_LEN:
            question = question[:_MAX_QUESTION_LEN]
            log.info("Question truncated to %d chars", _MAX_QUESTION_LEN)

        if not question:
            return _make_error_result(errors=["问题不能为空"], partial=False)

        top_k = min(top_k, 8)
        perf_meta["top_k_effective"] = top_k

        # ── 0a. Normalize question ────────────────────────────────────────────
        normalized_question, was_normalized = _normalize_question(question)

        # ── 0a.1 Auto-extract report year from question text ──────────────────
        # When the caller did not supply an explicit `years` filter but the
        # question contains a 4-digit year (e.g. "2024年财报"), use it as the
        # report selection hint so the correct annual period is retrieved rather
        # than always defaulting to the latest available report.
        # Note: \b fails for Chinese text (Chinese chars are \w in Python Unicode
        # mode), so we use digit-boundary lookarounds instead.
        if not years:
            import re as _re_yr
            _yr_matches = _re_yr.findall(r'(?<!\d)(20[012]\d)(?!\d)', normalized_question)
            if _yr_matches:
                years = [int(y) for y in dict.fromkeys(_yr_matches)]  # deduplicated, order-preserving

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
        if trace_recorder is not None:
            await trace_recorder.start("S1", {
                "market": market, "symbol": symbol, "report_id": report_id,
                "report_types": report_types, "years": years,
            })
        await _emit_report_stage(event_callback, phase="report_selection", title="正在定位报告")
        memory_report_id = latest_memory_report_id(memory_turns)
        selection_key = _selection_cache_key(
            ts_code=ts_code,
            normalized_question=normalized_question,
            report_id=report_id,
            report_types=report_types,
            years=years,
            memory_report_id=memory_report_id,
        )
        selection = None
        selection_start = time.perf_counter()
        try:
            if not force_refresh:
                cached_selection = await _cache_get_json(selection_key)
                selection = _selection_from_metadata(cached_selection)
                if selection is not None:
                    perf_meta["cache"]["selection"] = "hit"
            if selection is None:
                selection = await asyncio.wait_for(
                    resolve_report_selection(
                        db=db,
                        market=market,
                        symbol=symbol,
                        stock_name=stock_name,
                        question=normalized_question,
                        report_id=report_id,
                        report_types=report_types,
                        years=years,
                        memory_turns=memory_turns,
                    ),
                    timeout=_REPORT_SELECTION_TIMEOUT_SECONDS,
                )
                if selection and selection.ok:
                    await _cache_set_json(selection_key, selection.metadata(), _SELECTION_CACHE_TTL_SECONDS)
        except Exception as e:
            log.warning("Report selection failed for %s/%s: %s", market, symbol, e)
            perf_meta["timeout_layer"] = "report_selection" if isinstance(e, asyncio.TimeoutError) else perf_meta["timeout_layer"]
            selection = None
        timings["report_selection_ms"] = _ms_since(selection_start)

        if selection is None:
            if trace_recorder is not None:
                await trace_recorder.finish("S1", status="failed", error_code="REPORT_SELECTION_FAILED",
                                            payload={"duration_ms": timings["report_selection_ms"]})
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
            if trace_recorder is not None:
                await trace_recorder.finish("S1", status="failed", error_code=str(selection.selection_reason),
                                            output_data=selection.metadata())
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
        perf_meta["report_id"] = selected_report_id
        perf_meta["report_year"] = selection.report_year
        perf_meta["report_context"] = report_context
        if trace_recorder is not None:
            from app.services.report_analysis_trace_service import numeric_inventory
            await trace_recorder.finish("S1", output_data=report_context, payload={
                "selected_report_id": selected_report_id, "selected_report_year": selection.report_year,
                "selected_report_type": selection.report_type,
                "selected_period": selection.period_end,
                "disclosure_date": selection.disclosure_date,
                "report_context_numeric_date_tokens": numeric_inventory(report_context),
                "selection_source": selection.selection_reason,
                "selection_cache": perf_meta["cache"]["selection"],
            })

        # ── 4b. PDF/link fast path ───────────────────────────────────────────
        if _is_pdf_question(normalized_question):
            if trace_recorder is not None:
                for _stage in ("S2", "S3", "S4", "S5", "S6", "S7"):
                    await trace_recorder.skip(_stage, "PDF_LOCATOR_FAST_PATH")
            answer = _format_pdf_answer(report_context)
            timings["total_ms"] = _ms_since(total_start)
            return {
                "status": "completed",
                "answer": answer,
                "source_chunks": [],
                "review_audit": {},
                "rag_status": "not_required",
                "confidence": "high" if (report_context.get("pdf_url") or report_context.get("source_url")) else "low",
                "evidence_used": [],
                "data_limitations": [] if (report_context.get("pdf_url") or report_context.get("source_url")) else ["已选报告缺少官方 PDF URL"],
                "disclaimer": "本内容基于已接入的公开财报片段，仅供参考，不构成投资建议。",
                "errors": [],
                "partial": False,
                "cache_meta": _empty_cache_meta(),
                "memory_meta": {
                    **memory_meta_dict(session_id, len(memory_turns), False),
                    "report_context": report_context,
                },
                "safety_meta": safety_meta,
                "performance_meta": {
                    **perf_meta,
                    "stage_timings_ms": timings,
                    "source_chunks_count": 0,
                    "evidence_chars": 0,
                },
            }

        # ── 5. Cache read ─────────────────────────────────────────────────────
        if not force_refresh:
            cached = await read_cache(
                ts_code=ts_code,
                normalized_question=normalized_question,
                report_types=selected_report_types,
                years=selected_years,
                report_id=selected_report_id,
                intent_type=intent_type,
            )
            if cached is not None:
                log.debug("Cache HIT for %s question=%r", ts_code, normalized_question[:40])
                perf_meta["cache"]["final_answer"] = "hit"
                cached["safety_meta"] = safety_meta
                cached["memory_meta"] = {
                    **memory_meta_dict(session_id, len(memory_turns), False),
                    "report_context": report_context,
                }
                cached["performance_meta"] = {
                    **(cached.get("performance_meta") or {}),
                    **perf_meta,
                    "stage_timings_ms": {**timings, "total_ms": _ms_since(total_start)},
                }
                if trace_recorder is not None:
                    for _stage in ("S2", "S3", "S4", "S5", "S6", "S7"):
                        await trace_recorder.skip(_stage, "FINAL_ANSWER_CACHE_HIT")
                return cached

        cache_meta = _empty_cache_meta()

        # ── 5. Expand query for RAG (conversation-aware) ──────────────────────
        expanded_query = _expand_query(normalized_question, memory_turns)

        # ── 6. RAG retrieval ──────────────────────────────────────────────────
        if trace_recorder is not None:
            await trace_recorder.start("S2", {
                "normalized_question": normalized_question, "expanded_query": expanded_query,
                "report_id": selected_report_id, "top_k": top_k,
            })
        await _emit_report_stage(event_callback, phase="report_evidence_retrieval", title="正在检索报告证据")
        chunks: list[dict] = []
        rag_result: dict = {"chunks": [], "partial": False, "errors": [], "provider": "unavailable"}
        rag_status = "unavailable"
        evidence_key = _evidence_cache_key(
            ts_code=ts_code,
            report_id=selected_report_id,
            normalized_question=expanded_query,
            top_k=top_k,
        )

        evidence_start = time.perf_counter()
        try:
            cached_evidence = await _cache_get_json(evidence_key)
            if isinstance(cached_evidence, dict) and cached_evidence.get("chunks"):
                rag_result = cached_evidence.get("rag_result") or {}
                chunks = cached_evidence.get("chunks") or []
                rag_status = cached_evidence.get("rag_status") or _compute_rag_status(rag_result)
                perf_meta["cache"]["evidence"] = "hit"
            else:
                rag_start = time.perf_counter()
                if _is_indexed_report(report_context):
                    rag_result = await asyncio.wait_for(
                        _query_indexed_report_db_evidence(
                            db=db,
                            ts_code=ts_code,
                            report_context=report_context,
                            query_text=expanded_query,
                            top_k=top_k,
                        ),
                        timeout=_RAG_QUERY_TIMEOUT_SECONDS,
                    )
                else:
                    from app.services.report_rag_service import ReportRagService
                    rag_result = await asyncio.wait_for(
                        ReportRagService().query(
                            ts_code=ts_code,
                            query_text=expanded_query,
                            db=db,
                            report_types=selected_report_types,
                            years=selected_years,
                            report_id=selected_report_id,
                            top_k=top_k,
                        ),
                        timeout=_RAG_QUERY_TIMEOUT_SECONDS,
                    )
                timings["vector_query_ms"] = _ms_since(rag_start)
                chunks = rag_result.get("chunks", []) or []
                rag_status = _compute_rag_status(rag_result)
                await _cache_set_json(
                    evidence_key,
                    {
                        "chunks": chunks,
                        "rag_result": rag_result,
                        "rag_status": rag_status,
                        "report_context": report_context,
                        "created_at": int(time.time()),
                    },
                    _EVIDENCE_CACHE_TTL_SECONDS,
                )
                perf_meta["cache"]["evidence"] = "written"
            chunks = rag_result.get("chunks", []) or []
            if perf_meta["cache"]["evidence"] == "hit":
                chunks = cached_evidence.get("chunks") or []
            chunks = _limit_evidence_chunks(chunks)
            rag_status = _compute_rag_status(rag_result)
            if rag_result.get("errors"):
                errors.extend(rag_result["errors"])
        except asyncio.TimeoutError:
            perf_meta["timeout_layer"] = "rag_query"
            stale_evidence = await _cache_get_json(evidence_key)
            if isinstance(stale_evidence, dict) and stale_evidence.get("chunks"):
                chunks = _limit_evidence_chunks(stale_evidence.get("chunks") or [])
                rag_result = stale_evidence.get("rag_result") or {"chunks": chunks, "partial": True, "errors": ["RAG timeout; stale evidence used"]}
                rag_status = stale_evidence.get("rag_status") or _compute_rag_status(rag_result)
                perf_meta["cache"]["evidence"] = "stale_hit"
                errors.append("RAG检索超时，已使用缓存证据")
            else:
                errors.append("RAG检索超时")
                rag_status = "unavailable"
        except Exception as e:
            log.warning("RAG service failed for %s: %s", ts_code, e)
            errors.append(f"RAG检索失败: {e}")
            rag_status = "unavailable"
        timings["evidence_assembly_ms"] = _ms_since(evidence_start)
        timings["chunk_fetch_ms"] = timings["evidence_assembly_ms"]
        perf_meta["chunks_before_rerank"] = len(rag_result.get("chunks", []) or chunks)
        perf_meta["chunks_after_rerank"] = len(chunks)
        perf_meta["source_chunks_count"] = len(chunks)
        perf_meta["evidence_chars"] = _evidence_chars(chunks)
        perf_meta["indexed_fast_path"] = _is_indexed_report(report_context)
        if trace_recorder is not None:
            _retrieval_failed = not chunks and bool(errors)
            await trace_recorder.finish(
                "S2", status="failed" if _retrieval_failed else "completed",
                error_code="RAG_RETRIEVAL_FAILED" if _retrieval_failed else None,
                output_data={"provider": rag_result.get("provider"), "search_mode": rag_result.get("search_mode"), "chunk_count": len(chunks)},
                payload={"provider": rag_result.get("provider"), "search_mode": rag_result.get("search_mode"),
                         "retrieval_timeout": perf_meta.get("timeout_layer") == "rag_query",
                         "cache": perf_meta["cache"]["evidence"], "errors": errors},
            )
            await trace_recorder.start("S3", {"chunk_count": len(chunks)})
            await trace_recorder.finish("S3", output_data=[{
                "chunk_id": c.get("chunk_id"), "section_title": c.get("section_title"),
                "page_start": c.get("page_start"), "page_end": c.get("page_end"),
                "content_hash": _hash_payload(c.get("content") or ""),
            } for c in chunks], payload={"retrieved_evidence_ids": [c.get("chunk_id") for c in chunks]})
            _pre_compaction = "\n".join(str(c.get("content") or "") for c in chunks)
            from app.services.report_analysis_trace_service import numeric_inventory
            await trace_recorder.start("S4", {"retrieved_evidence_ids": [c.get("chunk_id") for c in chunks]})
            await trace_recorder.finish("S4", output_data=_pre_compaction, payload={
                "pre_compaction_evidence_hash": _hash_payload(_pre_compaction),
                "pre_compaction_numeric_inventory": numeric_inventory(_pre_compaction),
                "evidence_chars": len(_pre_compaction),
                "numeric_tokens": re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?(?:%|％)?", _pre_compaction)[:500],
                "evidence_preview": _pre_compaction,
            })

        # ── 7. Build allowed chunk IDs ────────────────────────────────────────
        allowed_chunk_ids = [c["chunk_id"] for c in chunks if c.get("chunk_id") is not None]
        if not chunks:
            timings["total_ms"] = _ms_since(total_start)
            _no_evidence_errors = list(errors) + ["NO_REPORT_EVIDENCE", "NUMERIC_EVIDENCE_MISSING"]
            return {
                "status": "failed",
                "error_code": "NO_REPORT_EVIDENCE",
                "answer": _format_evidence_fallback_answer(
                    question=normalized_question,
                    report_context=report_context,
                    chunks=[],
                    reason="未检索到可引用的报告证据",
                ),
                "source_chunks": [],
                "review_audit": {},
                "rag_status": rag_status,
                "confidence": "low",
                "evidence_used": [],
                "data_limitations": ["当前未检索到相关财报片段，不能编造财务数字"],
                "disclaimer": "本内容基于已接入的公开财报片段，仅供参考，不构成投资建议。",
                "errors": _no_evidence_errors,
                "partial": True,
                # R1.2: numeric_validation always present — evidence_missing is the authoritative state
                "numeric_validation": {
                    "valid": False,
                    "reason": "numeric_evidence_missing",
                    "evidence_available": False,
                    "replaced_count": 0,
                    "unsupported_count": 0,
                    "has_artifacts": False,
                },
                "cache_meta": cache_meta,
                "memory_meta": {
                    **memory_meta_dict(session_id, len(memory_turns), False),
                    "report_context": report_context,
                },
                "safety_meta": safety_meta,
                "performance_meta": {
                    **perf_meta,
                    "stage_timings_ms": timings,
                },
            }

        structured_financial_data: dict[str, Any] = {"fields": {}, "field_count": 0}
        # Cache key includes a hash of current chunk IDs so stale extractions
        # are automatically invalidated when the indexed chunks change.
        _sf_chunk_hash = _hash_payload([c.get("chunk_id") for c in chunks])
        structured_cache_key = (
            f"report_financial_fields"
            f":{selected_report_id or report_context.get('report_id')}"
            f":{_sf_chunk_hash}:v2"
        )
        cached_structured = await _cache_get_json(structured_cache_key)
        if isinstance(cached_structured, dict) and cached_structured.get("fields"):
            structured_financial_data = cached_structured
            perf_meta["cache"]["structured_financial_fields"] = "hit"
        else:
            try:
                from app.services.report_financial_table_extractor_tool import report_financial_table_extractor_tool
                structured_financial_data = report_financial_table_extractor_tool.extract_from_chunks(
                    report_id=selected_report_id or report_context.get("report_id") or "",
                    chunks=chunks,
                    report_year=report_context.get("report_year"),
                    source_document_id=report_context.get("source_document_id"),
                )
                if structured_financial_data.get("fields"):
                    await _cache_set_json(structured_cache_key, structured_financial_data, ttl=30 * 86400)
                    perf_meta["cache"]["structured_financial_fields"] = "written"
                else:
                    perf_meta["cache"]["structured_financial_fields"] = "empty"
            except Exception as exc:
                perf_meta["cache"]["structured_financial_fields"] = "error"
                errors.append(f"结构化财报字段提取失败: {str(exc)[:120]}")

        # ── 8. Build LLM prompt (with session memory context) ─────────────────
        await _emit_report_stage(event_callback, phase="report_synthesis", title="正在生成分析")
        system_prompt = _load_system_prompt()
        # Compress evidence to ≤2000 chars before serialising for the LLM prompt.
        # financial_evidence_compactor preserves numeric / financial sentences and
        # strips PDF boilerplate, keeping synthesis prompt under ~5 000 chars total.
        if trace_recorder is not None:
            await trace_recorder.start("S5", {"pre_compaction_hash": _hash_payload([c.get("content") for c in chunks])})
        compacted_chunks = financial_evidence_compactor(chunks, max_chars_per_chunk=400, max_total_chars=2000)
        if trace_recorder is not None:
            from app.services.report_analysis_trace_service import (
                compaction_evidence_snapshot,
                structured_financial_snapshot,
            )
            from app.services.report_financial_table_extractor_tool import report_financial_table_extractor_tool
            _post_compaction = "\n".join(str(c.get("content") or "") for c in compacted_chunks)
            _compaction_audit = compaction_evidence_snapshot(chunks, compacted_chunks)
            _structured_audit = structured_financial_snapshot(
                structured_financial_data,
                report_id=selected_report_id,
                report_year=selection.report_year,
                source=str(structured_financial_data.get("extraction_method") or "report_financial_table_extractor"),
                as_of=selection.disclosure_date,
                cache_status=str(perf_meta["cache"].get("structured_financial_fields") or "unknown"),
                expected_cache_version=report_financial_table_extractor_tool.cache_version,
                evidence_hash=_compaction_audit["pre_compaction_evidence_hash"],
            )
            await trace_recorder.finish("S5", output_data=_post_compaction, payload={
                **_compaction_audit,
                "structured_financial_fields_snapshot": _structured_audit,
                "evidence_chars": len(_post_compaction),
                "numeric_tokens": re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?(?:%|％)?", _post_compaction)[:500],
                "evidence_preview": _post_compaction,
            })
        chunks_json, evidence_map = _build_local_evidence_context(compacted_chunks)
        model_structured_financial_data = _strip_model_visible_chunk_metadata(
            structured_financial_data
        )
        perf_meta["prompt_evidence_chars"] = sum(len(c.get("content") or "") for c in compacted_chunks)
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
            f"\n结构化财务字段（structured_financial_data）：\n{json.dumps(model_structured_financial_data, ensure_ascii=False, default=str)}\n"
            "\nreview_audit：将在模型输出后由系统审核；模型不得假设审核通过。\n"
            f"{memory_section}"
            f"\n已接入财报证据（evidence，共 {len(compacted_chunks)} 条）：\n"
            f"{chunks_json}\n\n"
            "请严格基于 report_metadata、structured_financial_data、source_chunks 和会话上下文回答问题，输出合法 JSON（不带代码块标记）。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]

        # ── 9. LLM call ────────────────────────────────────────────────────────
        if trace_recorder is not None:
            await trace_recorder.start("S6", {
                "evidence_ids": list(evidence_map), "prompt_hash": _hash_payload(messages),
                "structured_financial_hash": _hash_payload(model_structured_financial_data),
                "structured_financial_fields_snapshot": _structured_audit,
            })
        raw_llm_result: dict = {}
        raw_text = ""
        llm_error: str | None = None
        llm_timed_out = False
        llm_error_category: str | None = None
        llm_trace_start = time.perf_counter()

        try:
            from app.core.config import settings
            from app.llm.deepseek_client import DeepSeekClient

            if not settings.ai_enabled:
                raise RuntimeError("AI 功能已关闭（AI_ENABLED=false）")
            if not settings.ai_api_key:
                raise RuntimeError("AI API Key 未配置")
            perf_meta["llm_model"] = settings.deepseek_model

            client = DeepSeekClient()
            loop = asyncio.get_running_loop()
            llm_start = time.perf_counter()
            raw_response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: client.chat(
                        messages,
                        temperature=0.3,
                        model=settings.deepseek_model,   # flash model (default)
                    ),
                ),
                timeout=_LLM_SYNTHESIS_TIMEOUT_SECONDS,
            )
            timings["llm_total_ms"] = _ms_since(llm_start)
            timings["llm_first_token_ms"] = timings["llm_total_ms"]
            raw_text = _extract_response_text(raw_response)
            if not raw_text:
                raise RuntimeError("LLM 返回为空")
            cleaned_text = _strip_json_fence(raw_text)
            raw_llm_result = _normalize_llm_json_result(json.loads(cleaned_text))

        except json.JSONDecodeError as e:
            llm_error_category = "invalid_json_output"
            llm_error = f"LLM 输出 JSON 解析失败: {e}"
            log.error("ReportChatCopilot JSON parse failed: %s", e)
            errors.append(llm_error)
        except asyncio.TimeoutError:
            llm_timed_out = True
            llm_error_category = "timeout"
            llm_error = "LLM 调用超时"
            timings["llm_total_ms"] = _LLM_SYNTHESIS_TIMEOUT_SECONDS * 1000
            perf_meta["timeout_layer"] = "llm_synthesis"
            log.error("ReportChatCopilot LLM timeout")
            errors.append(llm_error)
        except Exception as e:
            llm_error_category = "empty_output" if "LLM 返回为空" in str(e) else "provider_error"
            llm_error = f"LLM 调用失败: {e}"
            log.error("ReportChatCopilot LLM error: %s", e)
            errors.append(llm_error)

        if trace_recorder is not None:
            if "llm_total_ms" not in timings:
                timings["llm_total_ms"] = _ms_since(llm_trace_start)
            _raw_output_present = bool(raw_text)
            await trace_recorder.finish(
                "S6", status="failed" if llm_error else "completed",
                error_code="REPORT_LLM_TIMEOUT" if llm_timed_out else "REPORT_LLM_SYNTHESIS_FAILED" if llm_error else None,
                output_data=raw_llm_result,
                payload={"raw_llm_result": raw_llm_result, "raw_output_copy": raw_text,
                         "raw_output_present": _raw_output_present,
                         "raw_output_absent": not _raw_output_present,
                         "output_hash": _hash_payload(raw_text) if _raw_output_present else None,
                         "provider_error_category": llm_error_category,
                         "timeout_layer": "llm_synthesis" if llm_timed_out else None,
                         "duration_ms": timings.get("llm_total_ms"),
                         "error": llm_error,
                         "citation_fields": raw_llm_result.get("citations", []) if isinstance(raw_llm_result, dict) else []},
            )

        # If LLM completely failed, build a graceful fallback
        if llm_error or not raw_llm_result:
            limitations = ["AI 服务暂时不可用"]
            if not chunks:
                limitations.insert(0, "当前未检索到相关财报片段")
            timings["total_ms"] = _ms_since(total_start)
            if chunks:
                fallback_answer = _format_evidence_fallback_answer(
                    question=normalized_question,
                    report_context=report_context,
                    chunks=chunks,
                    reason="自动总结未在时限内完成" if llm_timed_out else "自动总结生成失败",
                )
                return {
                    "status": "partial_success",
                    "error_code": "REPORT_LLM_TIMEOUT" if llm_timed_out else "REPORT_LLM_SYNTHESIS_FAILED",
                    "answer": fallback_answer,
                    "source_chunks": chunks,
                    "review_audit": {"status": "skipped_after_synthesis_failure"},
                    "rag_status": rag_status,
                    "confidence": "medium" if chunks else "low",
                    "data_limitations": limitations + ["已使用检索到的报告证据生成确定性降级回答"],
                    "errors": errors,
                    "partial": True,
                    "cache_meta":  cache_meta,
                    "memory_meta": {
                        **memory_meta_dict(session_id, len(memory_turns), memory_context_used),
                        "report_context": report_context,
                    },
                    "safety_meta": safety_meta,
                    "performance_meta": {
                        **perf_meta,
                        "stage_timings_ms": timings,
                    },
                }
            return {
                "status": "failed" if llm_timed_out else "completed",
                "error_code": "REPORT_LLM_TIMEOUT" if llm_timed_out else None,
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

        # Resolve LLM-local labels before the existing canonical source review.
        if trace_recorder is not None:
            await trace_recorder.start("S7", {"raw_llm_hash": _hash_payload(raw_llm_result)})
        resolved_citations, citation_validation = _resolve_local_citations(
            raw_llm_result.get("citations"),
            evidence_map,
        )
        if not citation_validation["valid"]:
            errors.append("CITATION_VALIDATION_FAILED")

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
            "source_chunks":  resolved_citations,
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
            review_start = time.perf_counter()
            review_result = await asyncio.wait_for(
                FundamentalReviewAgent().review(review_input, data_pack_stub),
                timeout=_REVIEW_TIMEOUT_SECONDS,
            )
            timings["review_ms"] = _ms_since(review_start)
            review_audit = review_result.get("audit", {})
        except asyncio.TimeoutError:
            timings["review_ms"] = int(_REVIEW_TIMEOUT_SECONDS * 1000)
            perf_meta["timeout_layer"] = perf_meta["timeout_layer"] or "review"
            errors.append("合规审核超时（使用原始结果）")
            review_result = {"final": review_input, "status": "skipped"}
            review_audit = {"status": "timeout_skipped"}
        except Exception as e:
            log.warning("Review agent failed for chat: %s", e)
            errors.append(f"合规审核失败（使用原始结果）: {e}")
            review_result = {"final": review_input, "status": "skipped"}
            review_audit = {}

        # ── 11. Extract final output ──────────────────────────────────────────
        final: dict = review_result.get("final", review_input)

        answer = _extract_response_text(final) or _extract_response_text(raw_llm_result)
        confidence = final.get("confidence") or raw_llm_result.get("confidence", "low")
        evidence_used = final.get("evidence_used") or raw_llm_result.get("evidence_used", [])
        data_limitations = final.get("data_limitations") or raw_llm_result.get("data_limitations", [])
        source_chunks_out = final.get("source_chunks") or resolved_citations or chunks
        disclaimer = final.get("disclaimer") or "本内容基于已接入的公开财报片段，仅供参考，不构成投资建议。"

        if not str(answer or "").strip():
            answer = (
                "报告证据已获取，但本次总结生成暂时失败。"
                + _format_data_limited_answer(
                    normalized_question,
                    report_context,
                    chunks,
                    ["总结生成返回空白，未编造财务数字"],
                )
            )
            confidence = "low"
            data_limitations = list(data_limitations or [])
            if "总结生成返回空白，已降级为证据范围说明" not in data_limitations:
                data_limitations.insert(0, "总结生成返回空白，已降级为证据范围说明")
            errors.append("EMPTY_LLM_ANSWER")

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

        consistency_issues = _answer_consistency_issues(answer, source_chunks_count=len(source_chunks_out or chunks))
        if consistency_issues:
            errors.extend(consistency_issues)
            answer = _format_evidence_fallback_answer(
                question=normalized_question,
                report_context=report_context,
                chunks=chunks,
                reason="自动生成结果存在格式或证据一致性问题",
            )
            confidence = "medium" if chunks else "low"
            data_limitations = list(data_limitations or [])
            for issue in consistency_issues:
                if issue not in data_limitations:
                    data_limitations.append(issue)
            review_audit = {
                **(review_audit or {}),
                "answer_consistency_guard": "fallback",
                "issues": consistency_issues,
            }

        is_rejection = review_status == "rejected" or classification == "rejected"

        citation_leaks = _citation_metadata_leaks(answer, allowed_chunk_ids)
        if citation_leaks:
            errors.append("CITATION_METADATA_LEAK")
            answer = _format_evidence_fallback_answer(
                question=normalized_question,
                report_context=report_context,
                chunks=chunks,
                reason="自动生成结果包含内部引用标识，已安全降级",
            )
            confidence = "medium" if chunks else "low"
            data_limitations = list(data_limitations or [])
            data_limitations.insert(0, "检测到内部引用标识，原始回答未发布")
            review_audit = {
                **(review_audit or {}),
                "citation_metadata_leak": True,
                "leaked_chunk_ids": citation_leaks,
            }

        # ── R1.2 P0: Numeric validation gate ─────────────────────────────────
        # Build evidence corpus from retrieved RAG chunks (same text the LLM saw).
        # validate_numeric_claims() returns structured state so downstream can gate
        # status without needing to re-parse the answer.
        from app.agents.specialist_analysis_utils import (  # noqa: PLC0415
            validate_numeric_claims,
            has_sanitization_artifacts,
        )
        _evidence_text = " ".join(str(c.get("content") or "") for c in (chunks or []))
        # Augment 1: structured financial extraction output (field values + raw_text
        # windows around each regex match, which include nearby yoy% columns).
        _sf_ev = json.dumps(structured_financial_data, ensure_ascii=False, default=str)
        # Augment 2: report context metadata.  Adds disclosure_date (e.g.
        # "2025-04-02") to the corpus so date-component tokens ("-04", "-02",
        # "2025") extracted from dates mentioned in the LLM answer are in the
        # allowed set and do not trigger UNSUPPORTED_NUMBERS.
        _ctx_ev = json.dumps(report_context, ensure_ascii=False, default=str)
        # Augment 3: 亿-unit equivalents of large raw yuan values.  The LLM often
        # writes "约1,708.99亿元" after seeing the raw 170,899,152,276.34元 in
        # evidence.  Dividing every large number (≥1e8) in the base corpus by 1e8
        # and appending the result (to 2 d.p.) makes canonical "1708.99" visible
        # to the allowed-set builder so these unit-converted claims pass.
        _base_corpus = _evidence_text + " " + _sf_ev
        _yi_extras: list[str] = []
        for _ytok in re.findall(r"(?<![A-Za-z_])[-+]?[\d,]+(?:\.\d+)?", _base_corpus):
            try:
                _yv = float(_ytok.replace(",", "").lstrip("+"))
            except ValueError:
                continue
            if abs(_yv) >= 1e8:
                _yi_extras.append(f"{_yv / 1e8:.2f}")
        _evidence_text = " ".join(
            x for x in [_evidence_text, _sf_ev, _ctx_ev, " ".join(_yi_extras)] if x.strip()
        ).strip()
        _nv = validate_numeric_claims(answer, _evidence_text)
        _has_artifact = has_sanitization_artifacts(answer)

        _numeric_validation = {
            "valid":              _nv["valid"],
            "reason":             _nv["reason"],
            "evidence_available": _nv["evidence_available"],
            "replaced_count":     _nv["replaced_count"],
            "unsupported_count":  len(_nv.get("unsupported_tokens") or []),
            "has_artifacts":      _has_artifact,
            "citation_metadata_leak": bool(citation_leaks),
            "citation_validation": citation_validation,
        }
        if trace_recorder is not None:
            from app.services.report_analysis_trace_service import numeric_token_provenance
            _unsupported = [str(item) for item in (_nv.get("unsupported_tokens") or [])]
            await trace_recorder.finish("S7", status="failed" if (not _nv["valid"] or citation_leaks or not citation_validation["valid"]) else "completed",
                error_code=("CITATION_METADATA_LEAK" if citation_leaks else "CITATION_VALIDATION_FAILED" if not citation_validation["valid"] else "NUMERIC_VALIDATION_FAILED" if not _nv["valid"] else None),
                output_data={"numeric_validation": _numeric_validation, "citation_validation": citation_validation},
                payload={
                    "unsupported_tokens": _unsupported,
                    "token_contexts": numeric_token_provenance(answer, _unsupported, {
                        "S1": report_context,
                        "S4": _pre_compaction,
                        "S5": _post_compaction,
                        "structured_facts": _structured_audit,
                        "S6": answer,
                    }),
                    "allowed_evidence_token_summary": {
                        "evidence_hash": _hash_payload(_evidence_text),
                        "numeric_tokens": re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?(?:%|％)?", _evidence_text)[:500],
                    },
                    "selected_report_id": selected_report_id, "selected_report_year": selection.report_year,
                    "retrieved_evidence_ids": allowed_chunk_ids,
                    "citation_validation": citation_validation,
                    "citation_metadata_leak": bool(citation_leaks),
                })

        if not _nv["valid"]:
            if _nv["reason"] == "numeric_evidence_missing":
                # Empty evidence: numeric claims cannot be traced to source — must degrade
                errors.append("NUMERIC_EVIDENCE_MISSING")
                _lim = "数字声明无法通过证据验证（证据缺失），已降级"
                if _lim not in (data_limitations or []):
                    data_limitations = list(data_limitations or [])
                    data_limitations.insert(0, _lim)
            elif _nv["reason"] == "unsupported_numbers_found":
                _bad = ", ".join(str(t) for t in (_nv.get("unsupported_tokens") or [])[:5])
                errors.append(f"UNSUPPORTED_NUMBERS:{_bad}")
                _lim = f"部分数字无法在证据中找到对应（{_bad}）"
                if _lim not in (data_limitations or []):
                    data_limitations = list(data_limitations or [])
                    data_limitations.insert(0, _lim)

        if _has_artifact:
            errors.append("SANITIZATION_ARTIFACTS_IN_ANSWER")
            _lim = "输出中存在净化标记（未提供数字/[path]），内容已降级"
            if _lim not in (data_limitations or []):
                data_limitations = list(data_limitations or [])
                data_limitations.insert(0, _lim)

        # numeric_invalid forces partial=True so status cannot be "completed"
        _numeric_invalid = not _nv["valid"] or _has_artifact

        partial = bool(errors) or _numeric_invalid or rag_result.get("partial", False) or review_status not in {"approved", "revised", "skipped"}
        timings["total_ms"] = _ms_since(total_start)

        result = {
            "status":             "partial_success" if partial and chunks else "completed",
            "answer":           answer,
            "source_chunks":    source_chunks_out,
            "review_audit":     review_audit,
            "rag_status":       rag_status,
            "confidence":       confidence,
            "evidence_used":    evidence_used,
            "data_limitations": data_limitations,
            "disclaimer":       disclaimer,
            "errors":              errors,
            "partial":             partial,
            "numeric_validation":  _numeric_validation,  # R1.2: validation state for debugging/badge
            "cache_meta":          cache_meta,
            "memory_meta": {
                **memory_meta_dict(session_id, len(memory_turns), memory_context_used),
                "report_context": report_context,
            },
            "safety_meta":      safety_meta,
            "performance_meta": {
                **perf_meta,
                "llm_evidence_ids": list(evidence_map),
                "citation_validation": citation_validation,
                "stage_timings_ms": timings,
            },
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
                intent_type=intent_type,
            )
            # Refresh cache_meta in the returned result (key was computed inside write_cache)
            from app.agent.report_chat_cache import make_cache_key
            import time as _time
            from app.core.config import settings as _settings
            _ttl = 60 if is_rejection else _settings.report_chat_cache_ttl_seconds
            result["cache_meta"] = {
                "hit":         False,
                "key":         make_cache_key(ts_code, normalized_question, selected_report_types, selected_years, selected_report_id, intent_type),
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
