"""
Thinking Sanitizer — C28.4.

sanitize_thinking_content() filters and truncates "thinking" / "reasoning"
content before it is emitted to the frontend.

Goals:
  1. Remove internal prompt artefacts that should never be visible to users.
  2. Remove stack traces and exception text.
  3. Apply a lightweight financial-safety filter (no price targets, no
     hard trading directives in raw reasoning content).
  4. Hard-cap at max_chars so long reasoning chains don't overwhelm the UI.
"""
from __future__ import annotations

import re

# ── Internal artefact patterns to strip ───────────────────────────────────────

_INTERNAL_LINE_PATTERNS: list[re.Pattern] = [
    # System prompt / tool argument leakage
    re.compile(r"系统提示[:：].*$",               re.MULTILINE | re.IGNORECASE),
    re.compile(r"tool[\s_]args?[:：].*$",         re.MULTILINE | re.IGNORECASE),
    re.compile(r"<tool_call>.*?</tool_call>",     re.DOTALL    | re.IGNORECASE),
    re.compile(r"<system>.*?</system>",           re.DOTALL    | re.IGNORECASE),
    # Stack traces
    re.compile(
        r"Traceback \(most recent call last\):.*?(?=\n\n|\Z)",
        re.DOTALL,
    ),
    re.compile(r"^\s+File \".*?\", line \d+.*$",  re.MULTILINE),
]

# Lines starting with any of these prefixes are fully removed
_STRIP_LINE_PREFIXES: tuple[str, ...] = (
    "Traceback",
    'File "',
    "  File ",
    "    raise ",
    "During handling",
    "  __",   # internal __traceback__ etc.
)

# ── Lightweight financial-safety filter ───────────────────────────────────────

# ── Skill name → Chinese label (C28.1) ────────────────────────────────────────

_SKILL_NAME_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bgeneral_financial_answer_skill\b"), "智能问答"),
    (re.compile(r"\breport_explanation_skill\b"),       "报告解读"),
    (re.compile(r"\bindustry_hotspot_skill\b"),         "行业热点分析"),
    (re.compile(r"\bstock_anomaly_skill\b"),            "股票异动分析"),
    (re.compile(r"\brisk_first_skill\b"),               "风险优先分析"),
    (re.compile(r"\bnews_catalyst_skill\b"),            "新闻催化分析"),
    (re.compile(r"\bwatchlist_review_skill\b"),         "自选股研究"),
    (re.compile(r"\banalysis_run_skill\b"),             "AI研报生成"),
    (re.compile(r"\bfinancial_rag_search\b"),           "金融知识库检索"),
    (re.compile(r"\buniversal_market_search\b"),        "市场热点搜索"),
    (re.compile(r"\bofficial_report_search\b"),         "官方财报检索"),
]

_FINANCE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Hard price targets
    (re.compile(r"目标价\s*[\d.]+\s*元?",           re.IGNORECASE), "目标价[已过滤]"),
    (re.compile(r"target\s+price\s+[\$¥]?[\d.]+", re.IGNORECASE), "[price target filtered]"),
    # Absolute certainty phrases
    (re.compile(r"(一定|肯定|必然|百分之百)\s*(上涨|涨|大涨|暴涨)", re.IGNORECASE), "存在上行研究线索"),
    (re.compile(r"(一定|肯定|必然|百分之百)\s*(下跌|跌|暴跌)",      re.IGNORECASE), "存在下行压力"),
]


def sanitize_thinking_content(
    content: str,
    source: str = "agent_step",
    max_chars: int = 500,
) -> str:
    """
    Filter and cap a raw thinking/reasoning string.

    Parameters
    ----------
    content : str
        Raw thinking content from model or agent.
    source : str
        Event source — used for future per-source tuning.
    max_chars : int
        Maximum output length in characters (default 500).

    Returns
    -------
    str
        Cleaned, truncated content.  May be empty string if everything was
        filtered — callers should skip emitting empty events.
    """
    if not content or not isinstance(content, str):
        return ""

    text = content

    # Strip regex-matched internal artefacts
    for pat in _INTERNAL_LINE_PATTERNS:
        text = pat.sub("", text)

    # Strip lines starting with known bad prefixes
    clean_lines: list[str] = []
    for line in text.splitlines():
        if any(line.startswith(p) for p in _STRIP_LINE_PREFIXES):
            continue
        clean_lines.append(line)
    text = "\n".join(clean_lines)

    # Apply lightweight financial safety to thinking content
    for pat, replacement in _FINANCE_PATTERNS:
        text = pat.sub(replacement, text)

    # Apply skill name → Chinese label mapping
    for pat, replacement in _SKILL_NAME_PATTERNS:
        text = pat.sub(replacement, text)

    # Collapse excessive blank lines (3+ → 2)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Trim whitespace
    text = text.strip()

    # Hard cap — add ellipsis to signal truncation
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…"

    return text


# ─────────────────────────────────────────────────────────────────────────────
# C30.6 — DeepSeek reasoning_content → public thinking summary
# ─────────────────────────────────────────────────────────────────────────────

# Maps each of the 5 public thinking steps to extraction heuristics
_STEP_HINTS = [
    ("问题分析",     re.compile(r"问题|理解|判断|请求类型|intent|用户意图",    re.IGNORECASE)),
    ("关键数据检索", re.compile(r"检索|查询|数据|获取|工具|搜索|找到|API",      re.IGNORECASE)),
    ("深度思考",     re.compile(r"思考|分析|比较|评估|权衡|推理|考虑|综合",      re.IGNORECASE)),
    ("风险审查",     re.compile(r"风险|审查|合规|建议|不确定|边界|注意|警告",    re.IGNORECASE)),
    ("回答生成",     re.compile(r"回答|生成|总结|输出|最终|结论|基于",           re.IGNORECASE)),
]

# Max chars to take from a single sentence for public display
_STEP_EXCERPT_MAX = 80


def convert_reasoning_to_public_summary(
    reasoning_content: str,
    intent: str = "general",
    *,
    max_chars: int = 2000,
) -> list[dict]:
    """
    C30.6: Convert DeepSeek reasoning_content to a list of public thinking-step
    summaries.  Raw chain-of-thought is NEVER passed through intact.

    Args:
        reasoning_content: raw text from DeepSeek's reasoning_content field
        intent:            detected intent (from intent_decision_agent)
        max_chars:         cap on reasoning_content before processing

    Returns:
        List of dicts: [{title, content, status}] — the "visible steps" for
        ChatThinkingMiniPanel, in business-level language.
        Falls back to template steps when reasoning_content is empty/None.
    """
    from app.agents.intent_decision_agent import classify_intent  # local import to avoid cycle

    # Sanitize first — removes raw artefacts, tool args, system prompts
    sanitized = sanitize_thinking_content(reasoning_content or "", max_chars=max_chars)

    if not sanitized.strip():
        # No usable reasoning → return template-based steps
        return _template_steps_for_intent(intent)

    # Extract one representative sentence per step from the sanitized text
    sentences = re.split(r"[。！？\n]+", sanitized)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    steps: list[dict] = []
    for step_title, hint_re in _STEP_HINTS:
        # Find a sentence that matches the hint pattern
        excerpt = next(
            (s[:_STEP_EXCERPT_MAX] for s in sentences if hint_re.search(s)),
            None,
        )
        if excerpt is None and sentences:
            # No hint match — use position-based fallback
            idx = len(steps) * max(1, len(sentences) // 5)
            excerpt = sentences[min(idx, len(sentences) - 1)][:_STEP_EXCERPT_MAX]
        if excerpt:
            steps.append({"title": step_title, "content": excerpt, "status": "done"})

    # Pad with template steps for missing positions
    template = _template_steps_for_intent(intent)
    for i, tpl in enumerate(template):
        if i >= len(steps):
            steps.append({**tpl, "status": "done"})

    return steps[:5]  # always exactly 5 steps


def _template_steps_for_intent(intent: str) -> list[dict]:
    """Return template 5-step summaries for a given intent (fallback)."""
    _TEMPLATES: dict[str, list[tuple[str, str]]] = {
        "financial_report": [
            ("问题分析",     "我正在理解你的问题，判断这是财报分析类请求。"),
            ("关键数据检索", "我会优先检索官方财报、行情数据和知识库资料。"),
            ("深度思考",     "我会比较已获取数据，避免编造未验证的财务指标。"),
            ("风险审查",     "我会检查是否存在买卖建议或无来源估值数字。"),
            ("回答生成",     "我会基于已验证信息生成最终回答。"),
        ],
        "hot_stocks": [
            ("问题分析",     "我正在理解你的问题，判断这是市场热点类请求。"),
            ("关键数据检索", "我会检索市场热点、行业线索和相关股票涨幅数据。"),
            ("深度思考",     "我会区分短期热度和真实产业链关联。"),
            ("风险审查",     "我会检查是否存在买卖建议或无来源估值数字。"),
            ("回答生成",     "我会基于已验证信息生成最终回答。"),
        ],
        "industry_research": [
            ("问题分析",     "我正在理解你的问题，判断这是行业研究类请求。"),
            ("关键数据检索", "我会检索行业热度数据和代表性公司列表。"),
            ("深度思考",     "我会分析行业机会与风险，不直接等同于买入推荐。"),
            ("风险审查",     "我会说明数据边界，避免过度推断。"),
            ("回答生成",     "我会提供行业概览和代表公司供参考。"),
        ],
        "report_generation": [
            ("问题分析",     "我正在理解你的问题，判断这是报告生成任务请求。"),
            ("关键数据检索", "我会创建分析任务，配置分析范围和参数。"),
            ("深度思考",     "我会根据任务状态判断报告是否真正生成完成。"),
            ("风险审查",     "我会验证任务提交状态，不误报已完成任务。"),
            ("回答生成",     "我会持续跟踪报告状态，完成后提供查看链接。"),
        ],
    }
    raw = _TEMPLATES.get(intent, _TEMPLATES.get("general_research", [
        ("问题分析",     "我正在理解你的问题，判断所需信息类型。"),
        ("关键数据检索", "我会检索相关数据，优先使用官方来源。"),
        ("深度思考",     "我会综合已获取信息，区分事实与待确认内容。"),
        ("风险审查",     "我会检查是否存在买卖建议或无来源推断。"),
        ("回答生成",     "我会基于已验证信息生成最终回答。"),
    ]))
    return [{"title": t, "content": c, "status": "done"} for t, c in raw]
