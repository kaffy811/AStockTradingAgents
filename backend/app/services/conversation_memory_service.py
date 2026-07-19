"""
C32.1 — Conversation Memory Service

Enhances C8 chat_memory with multi-turn conversation context:

  1. active_entities  — [{type, name, code, market}] currently being discussed
  2. recent_messages  — last 8 user+assistant messages (text snippets, sanitized)
  3. session_summary  — compressed summary (<300 chars, LLM-generated, lazy)
  4. coreference resolution — rule-based pronoun/reference → entity resolution

New memory fields stored in session_metadata["memory_v1"]:
  - "active_entities"  : list[dict]
  - "recent_messages"  : list[dict]  # [{role, snippet}]
  - "session_summary"  : str

Safety:
  - Snippets truncated to 200 chars
  - Never stores: raw tool args, SQL, stack traces, API keys, Run IDs, system prompts
  - Summarization strips all internal metadata
  - All writes fire-and-forget; failures never propagate
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import AsyncSessionLocal
from app.models.chat import ChatMessage, ChatSession
import app.agents.chat_memory as _mem

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

RECENT_MSG_LIMIT    = 8      # max messages to include in context
SNIPPET_MAX_CHARS   = 200    # max chars per message snippet
SUMMARY_MAX_CHARS   = 300    # max chars for session_summary
SUMMARY_TRIGGER     = 12     # summarize when accumulated messages exceed this
MSG_HISTORY_MAX     = 300    # max chars per msg when building LLM messages array

# ── Coreference patterns ───────────────────────────────────────────────────────

# Patterns that reference the last mentioned stock
_RE_STOCK_PRONOUN = re.compile(
    r"它(?:的|们)?|这只|这支|该股|这家公司|这家|这个股票"
    r"|这只股|此股|那只|那支|该公司",
    re.IGNORECASE,
)
# Patterns that reference all recent stocks
_RE_MULTI_STOCK_PRONOUN = re.compile(
    r"这几家|这几只|那几家|那几只|它们|这些公司|这些股票"
    r"|刚才那几家|刚才的股票",
    re.IGNORECASE,
)
# Patterns that reference the last industry
_RE_INDUSTRY_PRONOUN = re.compile(
    r"这个行业|该行业|此行业|这个板块|该板块|这个领域|这个赛道"
    r"|这行|那个行业|那个板块",
    re.IGNORECASE,
)
# Patterns that reference the last report
_RE_REPORT_PRONOUN = re.compile(
    r"这份报告|那份报告|上一份报告|刚才的报告|之前的报告|这个报告"
    r"|那个报告|最近的报告|那报告",
    re.IGNORECASE,
)

# ── Sanitization for summaries ─────────────────────────────────────────────────

_SUMMARY_STRIP_PATTERNS = [
    # Stack traces
    re.compile(r"Traceback \(most recent call last\).*", re.DOTALL),
    # SQL
    re.compile(r"SELECT\s+.+?\s+FROM\s+\S+", re.IGNORECASE | re.DOTALL),
    re.compile(r"INSERT\s+INTO\s+\S+", re.IGNORECASE),
    # API keys / tokens
    re.compile(r"[Ss][Kk]-[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
    # Run IDs / UUIDs
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    # Tool call JSON blobs
    re.compile(r"\{\"tool\":.+?\}", re.DOTALL),
    # Internal snake_case system prompts
    re.compile(r"system_prompt|raw_tool_args|sql_query", re.IGNORECASE),
]


def _sanitize_for_summary(text: str) -> str:
    """Strip sensitive/internal content before saving as summary or snippet."""
    for pattern in _SUMMARY_STRIP_PATTERNS:
        text = pattern.sub("", text)
    # Collapse whitespace
    text = " ".join(text.split())
    return text


# ── MemoryContext dataclass ───────────────────────────────────────────────────

@dataclass
class ResolvedEntity:
    type:   str   # "stock" | "industry" | "report"
    name:   str
    code:   str = ""
    market: str = ""


def _entity_from_text(text: str) -> ResolvedEntity | None:
    """
    Backward-compatible explicit-code parser.

    Natural-language security names are resolved by SecurityEntityResolver with
    database/security-master context. This helper intentionally avoids a
    production hand-written alias table.
    """
    if not text:
        return None

    ts_match = re.search(r"(?<!\d)(\d{6})\.(SH|SZ|BJ)(?![A-Z0-9])", text, re.IGNORECASE)
    if ts_match:
        code = ts_match.group(1)
        return ResolvedEntity(type="stock", name=code, code=code, market="CN")

    cn_match = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
    if cn_match:
        code = cn_match.group(1)
        return ResolvedEntity(type="stock", name=code, code=code, market="CN")

    hk_match = re.search(r"(?<!\d)0?(\d{4,5})(?!\d)", text)
    if hk_match:
        code = hk_match.group(1).zfill(5)
        return ResolvedEntity(type="stock", name=code, code=code, market="HK")

    us_match = re.search(r"(?<![A-Z0-9.])([A-Z]{1,5}(?:[.-][A-Z])?)(?![A-Z0-9])", text)
    if us_match:
        code = us_match.group(1).upper()
        return ResolvedEntity(type="stock", name=code, code=code, market="US")

    return None


@dataclass
class MemoryContext:
    """
    Structured context passed to IntentDecisionAgent and CentralPlanningAgent.

    Fields:
      recent_messages    — last N messages as (role, snippet) pairs
      session_summary    — compressed summary of conversation so far
      active_entities    — entities currently being discussed
      last_intent        — most recent intent string
      open_tasks         — pending research tasks (future use)
      user_preferences   — remembered preferences (output_language etc.)
      resolved_query     — current_query with pronouns replaced by entity names
      needs_clarification — True if coreference confidence is low
      clarification_hint  — suggested clarification message for the AI
    """
    recent_messages:     list[dict]           = field(default_factory=list)
    session_summary:     str                   = ""
    active_entities:     list[ResolvedEntity]  = field(default_factory=list)
    last_intent:         str                   = ""
    open_tasks:          list[str]             = field(default_factory=list)
    user_preferences:    dict                  = field(default_factory=dict)
    resolved_query:      str                   = ""
    needs_clarification: bool                  = False
    clarification_hint:  str                   = ""

    def to_prompt_block(self) -> str:
        """
        Build a compact context block to prepend to the LLM system prompt.
        Max ~400 chars so it doesn't overwhelm the prompt.
        """
        lines: list[str] = []

        if self.session_summary:
            lines.append(f"[会话摘要] {self.session_summary[:120]}")

        if self.active_entities:
            ents = []
            for e in self.active_entities[:3]:
                if e.code:
                    ents.append(f"{e.name}（{e.market}/{e.code}）")
                elif e.name:
                    ents.append(e.name)
            if ents:
                lines.append(f"[当前讨论] {'、'.join(ents)}")

        if self.last_intent:
            lines.append(f"[上次意图] {self.last_intent}")

        if self.recent_messages:
            last = self.recent_messages[-1]
            snippet = last.get("snippet", "")[:80]
            if snippet:
                role_label = "用户" if last.get("role") == "user" else "AI"
                lines.append(f"[最近对话] {role_label}：{snippet}")

        if not lines:
            return ""

        return "\n".join(lines)

    def is_empty(self) -> bool:
        return not (self.active_entities or self.session_summary or self.recent_messages)


# ── Coreference resolution ─────────────────────────────────────────────────────

def resolve_coreferences(
    query: str,
    memory_ctx: MemoryContext,
) -> tuple[str, bool, str]:
    """
    Replace pronouns in `query` with the entities they refer to.

    Returns:
        (resolved_query, needs_clarification, clarification_hint)
    """
    if not query:
        return query, False, ""

    # Detect which pronoun types are present before deciding anything
    has_stock_pronoun = bool(_RE_STOCK_PRONOUN.search(query))
    has_multi_stock   = bool(_RE_MULTI_STOCK_PRONOUN.search(query))
    has_industry      = bool(_RE_INDUSTRY_PRONOUN.search(query))
    has_report        = bool(_RE_REPORT_PRONOUN.search(query))

    # No pronouns → nothing to resolve, return as-is
    if not (has_stock_pronoun or has_multi_stock or has_industry or has_report):
        return query, False, ""

    resolved = query
    needs_clarification = False
    clarification_hint  = ""

    stocks     = [e for e in (memory_ctx.active_entities or []) if e.type == "stock"]
    industries = [e for e in (memory_ctx.active_entities or []) if e.type == "industry"]

    # ── Multi-stock pronoun → all recent stocks ───────────────────────────────
    if _RE_MULTI_STOCK_PRONOUN.search(query) and len(stocks) >= 2:
        names = "、".join(
            (f"{s.name}（{s.market}/{s.code}）" if s.code else s.name)
            for s in stocks[:4]
        )
        resolved = _RE_MULTI_STOCK_PRONOUN.sub(names, resolved)
        return resolved, False, ""

    # ── Single-stock pronoun → most recent stock ──────────────────────────────
    if _RE_STOCK_PRONOUN.search(query):
        if stocks:
            s = stocks[0]
            replacement = f"{s.name}（{s.market}/{s.code}）" if s.code else s.name
            resolved = _RE_STOCK_PRONOUN.sub(replacement, resolved)
        else:
            # No known stock context — ask for clarification
            needs_clarification = True
            clarification_hint = "我不确定您说的'它'指哪只股票，请问您是指哪只股票？"

    # ── Industry pronoun → most recent industry ───────────────────────────────
    if _RE_INDUSTRY_PRONOUN.search(query):
        if industries:
            ind = industries[0]
            resolved = _RE_INDUSTRY_PRONOUN.sub(ind.name, resolved)
        else:
            needs_clarification = True
            clarification_hint = "我不确定您说的'这个行业'指哪个行业，请问您是指哪个行业？"

    # ── Report pronoun → note that last_report_id is in memory ───────────────
    if _RE_REPORT_PRONOUN.search(query):
        last_report = memory_ctx.user_preferences.get("last_report_id")
        if last_report:
            # Don't replace text; just ensure orchestrator knows about the report
            pass
        else:
            needs_clarification = True
            clarification_hint = "我找不到您之前生成的报告，请问您是指哪份报告？"

    return resolved, needs_clarification, clarification_hint


# ── Build MemoryContext from DB ───────────────────────────────────────────────

async def build_memory_context(
    db: AsyncSession,
    session_id: uuid.UUID | None,
    user_id: uuid.UUID,
    current_query: str = "",
) -> MemoryContext:
    """
    Build a MemoryContext for the current turn.

    Reads from:
      - ChatMessage table (last N messages)
      - chat_memory (C8 structured memory)

    Returns an empty MemoryContext if session_id is None or DB fails.
    Never raises.
    """
    if session_id is None:
        return MemoryContext(resolved_query=current_query)

    try:
        # 1. Load C8 memory
        mem = await _mem.get_memory(db, session_id, user_id)

        # 2. Load last N messages from DB
        msg_stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role.in_(["user", "assistant"]),
            )
            .order_by(desc(ChatMessage.created_at))
            .limit(RECENT_MSG_LIMIT)
        )
        rows = (await db.execute(msg_stmt)).scalars().all()
        rows = list(reversed(rows))  # oldest first

        recent_messages = [
            {
                "role":    r.role,
                "snippet": _sanitize_for_summary(r.content or "")[:SNIPPET_MAX_CHARS],
            }
            for r in rows
        ]

        # 3. Build active_entities from C8 recent_symbols + any industry context
        active_entities: list[ResolvedEntity] = []
        for sym in mem.get("recent_symbols", [])[:4]:
            active_entities.append(ResolvedEntity(
                type   = "stock",
                name   = sym.get("name", sym.get("symbol", "")),
                code   = sym.get("symbol", ""),
                market = sym.get("market", ""),
            ))

        # C32.3.2: Fallback — if recent_symbols produced nothing, scan recent
        # user-message snippets for known stock names / codes.
        # C32.3-fix: SKIP the current query's own snippet to avoid self-referential
        # extraction. Round 2 "那它和五粮液相比呢？" is committed before this runs
        # (Phase 1 commits user message before Phase 4 calls build_memory_context),
        # so without this guard the fallback would find 五粮液 from the current query
        # and use it as context — causing "它"→"五粮液" coreference, leaving only
        # 1 distinct candidate (五粮液 vs 五粮液) and triggering the "need 2 stocks" error.
        if not active_entities:
            _cur_snippet_prefix = _sanitize_for_summary(current_query)[:25].strip()
            for recent in reversed(recent_messages):
                if recent.get("role") == "user":
                    snippet = recent.get("snippet", "")
                    # Skip the current query itself
                    if _cur_snippet_prefix and snippet[:25].strip() == _cur_snippet_prefix:
                        continue
                    from app.services.security_entity_resolver import security_entity_resolver  # noqa: PLC0415
                    entity = await security_entity_resolver.resolve_one(db, snippet, min_confidence=0.78)
                    if entity is not None:
                        active_entities.append(ResolvedEntity(
                            type="stock",
                            name=entity.short_name or entity.symbol,
                            code=entity.symbol,
                            market=entity.market,
                        ))
                        break  # only the most recent prior user-mentioned stock
        # Add industry from recent intents if applicable
        for intent in mem.get("recent_intents", [])[:2]:
            if "industry" in (intent.get("intent") or ""):
                # Extract industry name from recent messages
                for msg in reversed(recent_messages):
                    if msg["role"] == "user":
                        # Light heuristic: look for industry keywords
                        snippet = msg["snippet"]
                        for keyword in ["行业", "板块", "赛道"]:
                            if keyword in snippet:
                                # Take the 6 chars before the keyword as industry name
                                idx = snippet.index(keyword)
                                candidate = snippet[max(0, idx - 6):idx + len(keyword)]
                                candidate = candidate.strip()
                                if len(candidate) >= 2:
                                    active_entities.append(ResolvedEntity(
                                        type = "industry",
                                        name = candidate,
                                    ))
                                break
                        break

        # 4. Read extended memory fields (C32 additions)
        session_summary = mem.get("session_summary", "")
        last_intent     = ""
        if mem.get("recent_intents"):
            last_intent = mem["recent_intents"][0].get("intent", "")

        # 5. User preferences
        user_preferences = {
            "output_language": mem.get("last_output_language", "zh-CN"),
            "last_report_id":  mem.get("last_report_id"),
        }

        # 6. Resolve coreferences
        ctx = MemoryContext(
            recent_messages  = recent_messages,
            session_summary  = session_summary,
            active_entities  = active_entities,
            last_intent      = last_intent,
            user_preferences = user_preferences,
            resolved_query   = current_query,
        )
        resolved, needs_clarification, clarification_hint = resolve_coreferences(
            current_query, ctx
        )
        ctx.resolved_query      = resolved
        ctx.needs_clarification  = needs_clarification
        ctx.clarification_hint   = clarification_hint

        return ctx

    except Exception as exc:
        try:
            await db.rollback()
        except Exception as rollback_exc:  # noqa: BLE001
            log.warning(
                "conversation_memory_service.build_memory_context: rollback failed for session %s error_class=%s",
                session_id,
                type(rollback_exc).__name__,
            )
        log.warning(
            "conversation_memory_service.build_memory_context: failed for session %s error_class=%s (non-fatal)",
            session_id,
            type(exc).__name__,
        )
        return MemoryContext(resolved_query=current_query)


# ── Update memory after message round ─────────────────────────────────────────

async def update_memory_after_message(
    db: AsyncSession,
    session_id: uuid.UUID | None,
    user_id: uuid.UUID,
    user_msg: str,
    assistant_answer: str,
) -> None:
    """
    Update active_entities and trigger summarization if needed.
    Fire-and-forget: never raises.
    """
    if session_id is None:
        return
    try:
        mem = await _mem.get_memory(db, session_id, user_id)

        # Count total messages to trigger summarization
        msg_count_stmt = select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.role.in_(["user", "assistant"]),
        )
        rows = (await db.execute(msg_count_stmt)).scalars().all()
        msg_count = len(rows)

        # Trigger lazy summarization once threshold exceeded
        if msg_count > SUMMARY_TRIGGER and not mem.get("session_summary"):
            messages_snapshot = [
                {"role": item.role, "content": item.content or ""}
                for item in rows[-RECENT_MSG_LIMIT:]
            ]
            asyncio.create_task(
                _trigger_summarization_with_new_session(session_id, user_id, messages_snapshot)
            )

    except Exception as exc:
        try:
            await db.rollback()
        except Exception as rollback_exc:  # noqa: BLE001
            log.warning(
                "conversation_memory_service.update_memory_after_message: rollback failed for session %s error_class=%s",
                session_id,
                type(rollback_exc).__name__,
            )
        log.warning(
            "conversation_memory_service.update_memory_after_message: failed for session %s error_class=%s",
            session_id,
            type(exc).__name__,
        )


async def _trigger_summarization_with_new_session(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    messages: list,
) -> None:
    async with AsyncSessionLocal() as db:
        try:
            await _trigger_summarization(db, session_id, user_id, messages)
        except Exception as exc:
            try:
                await db.rollback()
            except Exception as rollback_exc:  # noqa: BLE001
                log.warning(
                    "conversation_memory_service._trigger_summarization: rollback failed for session %s error_class=%s",
                    session_id,
                    type(rollback_exc).__name__,
                )
            log.warning(
                "conversation_memory_service._trigger_summarization: failed for session %s error_class=%s",
                session_id,
                type(exc).__name__,
            )


async def _trigger_summarization(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    messages: list,
) -> None:
    """
    Generate a compact session summary using DeepSeek and store in memory.
    Called lazily — only when message count exceeds SUMMARY_TRIGGER.
    """
    try:
        # Build a text block from recent messages for summarization
        text_parts: list[str] = []
        for m in messages[-RECENT_MSG_LIMIT:]:
            role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
            role_label = "用户" if role == "user" else "AI"
            snippet = _sanitize_for_summary(content or "")[:100]
            if snippet:
                text_parts.append(f"{role_label}：{snippet}")

        if not text_parts:
            return

        conversation_text = "\n".join(text_parts)

        # Use DeepSeek to summarize
        try:
            from app.llm.deepseek_client import create_client  # noqa: PLC0415
            client = create_client()
            prompt = (
                "以下是一段金融研究对话记录。请用中文写一句话总结对话主题（最多50字），"
                "不要包含：具体数字、价格、API参数、内部标识符。\n\n"
                f"{conversation_text}"
            )
            response = await client.chat_completion([
                {"role": "user", "content": prompt}
            ], max_tokens=80, temperature=0.3)
            summary = response.get("content", "")[:SUMMARY_MAX_CHARS]
            summary = _sanitize_for_summary(summary)
        except Exception:
            # Fallback: rule-based summary from most recent user message
            last_user = next(
                (m for m in reversed(messages) if (m.get("role") if isinstance(m, dict) else getattr(m, "role", "")) == "user"), None
            )
            if last_user:
                last_user_content = last_user.get("content") if isinstance(last_user, dict) else getattr(last_user, "content", "")
                summary = _sanitize_for_summary(last_user_content or "")[:60]
            else:
                return

        if not summary:
            return

        # Store in memory
        session_obj, mem = await _mem._load(db, session_id, user_id)
        if session_obj is None:
            return
        mem["session_summary"] = summary
        await _mem._save(db, session_obj, mem)
        await db.commit()

    except Exception:
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        log.warning(
            "conversation_memory_service._trigger_summarization: failed for session %s",
            session_id,
        )


# ── Build LLM messages with memory context ────────────────────────────────────

def build_llm_messages_with_memory(
    system_prompt: str,
    memory_context: "MemoryContext",
    current_query: str,
    max_recent_messages: int = 8,
) -> list[dict]:
    """
    Build an OpenAI/DeepSeek-compatible messages list that includes
    conversation history from memory_context.

    Output structure:
      [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": "[会话记忆] …"},   # only when non-empty
        {"role": "user",   "content": "…历史用户消息…"},  # last N turns
        {"role": "assistant", "content": "…历史回答摘要…"},
        {"role": "user",   "content": current_query},     # always last
      ]

    Safety rules (enforced here):
      • Memory block is pre-sanitised (no UUIDs / SQL / tokens / tracebacks)
      • Each historical message truncated to MSG_HISTORY_MAX chars
      • Memory used ONLY for pronoun/context understanding
      • Real-time data (prices, financials) must be re-fetched via tools
      • max_recent_messages caps history; never unbounded concatenation
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Inject memory as a second system message
    if not memory_context.is_empty():
        block = memory_context.to_prompt_block()
        if block:
            messages.append({
                "role": "system",
                "content": (
                    "【会话记忆】以下是本次会话的上下文摘要，仅用于理解代词指代和会话连续性。"
                    "涉及价格/财务/估值/新闻等实时数据时，必须重新调用工具或声明数据时效性，"
                    "严禁将记忆中的旧数据当作当前行情。\n\n" + block
                ),
            })

    # Add recent message history (oldest first, capped)
    recent = (memory_context.recent_messages or [])[-max_recent_messages:]
    for msg in recent:
        role = msg.get("role", "user")
        if role not in ("user", "assistant"):
            continue
        # Use snippet (already sanitised & truncated in build_memory_context)
        text = str(msg.get("snippet") or msg.get("content") or "")
        if len(text) > MSG_HISTORY_MAX:
            text = text[:MSG_HISTORY_MAX] + "…"
        if text:
            messages.append({"role": role, "content": text})

    # Current query is always the final user message
    messages.append({"role": "user", "content": current_query})
    return messages


# ── Public: get summary (read-only) ───────────────────────────────────────────

async def get_session_summary(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> str:
    """Return current session_summary or '' if not yet generated."""
    try:
        mem = await _mem.get_memory(db, session_id, user_id)
        return mem.get("session_summary", "")
    except Exception:
        return ""
