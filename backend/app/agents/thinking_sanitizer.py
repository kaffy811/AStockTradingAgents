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
