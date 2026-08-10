"""Shared formatting and output guards for specialist analysis agents."""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, TypedDict

_MISSING = "数据缺失"

# Two-alternative pattern for numeric tokens:
#   Alt-1: comma-thousands  "1,315.90" — REQUIRES ≥1 comma group so plain
#           numbers like "1315.90" do NOT mis-match as "131" + "5.90".
#   Alt-2: plain integer/decimal "1315.90", "19.8%", "+100"
# Leading + is captured for canonicalization; lookbehind prevents matching
# within identifiers so "MA5" does not produce a spurious "5" match.
_NUMERIC_RE = re.compile(
    r"(?<![A-Za-z_])[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?"  # comma-thousands (≥1 comma)
    r"|(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?%?"                  # plain number
)

# Only match multi-segment Unix absolute paths (≥2 segments).
# Single /word tokens like /MA5, /day, /v2 are NOT matched.
# Correct: /usr/lib/python3, /app/data/report.pdf
# Ignored: /MA5, /data, MA5/cross (not starting with /)
_ABS_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.])(?:/[A-Za-z0-9_.@-]+){2,}")
_CREDENTIAL_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*\S+")
_CREDENTIAL_WORD_RE = re.compile(r"(?i)api[_-]?key|secret|token|password")

_BANNED_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("强烈买入", "不提供买卖指令"),
    ("强烈卖出", "不提供买卖指令"),
    ("最值得买", "不提供买卖指令"),
    ("更值得买入", "不提供买卖指令"),
    ("买入", "关注"),
    ("卖出", "观察"),
    ("满仓", "控制风险"),
    ("梭哈", "控制风险"),
    ("抄底", "低位观察"),
    ("清仓", "降低风险暴露"),
    ("必涨", "存在不确定性"),
    ("必跌", "存在不确定性"),
    ("稳赚", "存在风险"),
    ("一定上涨", "存在不确定性"),
    ("一定下跌", "存在不确定性"),
    ("确定上涨", "存在不确定性"),
    ("确定下跌", "存在不确定性"),
    ("chain of thought", "推理过程"),
)


def is_missing(value: Any) -> bool:
    """Return True only for unavailable values. Numeric 0 is valid."""
    if value is None:
        return True
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return True
    if isinstance(value, str) and value.strip().lower() in {"nan", "inf", "+inf", "-inf", "none", "null"}:
        return True
    return False


def format_number(value: Any, *, precision: int = 2, suffix: str = "", signed: bool = False) -> str:
    if is_missing(value):
        return _MISSING
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        sign = "+" if signed and value > 0 else ""
        if isinstance(value, int) or float(value).is_integer():
            return f"{sign}{int(value)}{suffix}"
        return f"{sign}{float(value):.{precision}f}{suffix}"
    return str(value)


def format_percent(value: Any, *, precision: int = 2, signed: bool = False) -> str:
    return format_number(value, precision=precision, suffix="%", signed=signed)


def format_money_cny(value: Any, *, precision: int = 2) -> str:
    if is_missing(value):
        return _MISSING
    if isinstance(value, (int, float)):
        return f"{value / 1e8:.{precision}f} 亿元"
    return str(value)


def format_date(value: Any) -> str:
    if is_missing(value):
        return _MISSING
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _canonicalize_number(token: str) -> str:
    """Return a normalized form for numeric comparison.

    Handles: comma thousands separators, leading +, trailing zeros.
    Examples:
        "1,315.90" → "1315.9"
        "+19.80%"  → "19.8%"
        "100.00"   → "100.0"
        "1315.9"   → "1315.9"
    """
    t = token.replace(",", "").lstrip("+")
    is_pct = t.endswith("%")
    num_str = t[:-1] if is_pct else t
    try:
        val = float(num_str)
        # Remove unnecessary trailing zeros via Python float repr
        canon = f"{val:g}"
        return f"{canon}%" if is_pct else canon
    except ValueError:
        return t


def evidence_numbers(text: str) -> set[str]:
    """Extract all numeric tokens from *text* as raw strings."""
    return set(_NUMERIC_RE.findall(text or ""))


def _build_allowed_set(evidence_text: str) -> set[str]:
    """Build the set of permitted numeric tokens from evidence."""
    allowed: set[str] = set()
    for token in evidence_numbers(evidence_text):
        allowed.add(token)
        allowed.add(_canonicalize_number(token))
        # Also add the comma-stripped form so "1,315.90" ↔ "1315.90"
        allowed.add(token.replace(",", ""))
    return allowed


def remove_unsupported_numbers(text: str, evidence_text: str) -> str:
    """Replace numeric claims not traceable to evidence text.

    FAIL-CLOSED CONTRACT:
    - When *evidence_text* is empty or absent → return *text* unchanged.
      We must never globally corrupt output just because evidence wasn't
      threaded through (e.g. empty evidence → replaces every digit).
    - Uses re.sub(callback) to avoid partial-match corruption such as
      replacing "5.90" inside "1315.90" and producing "1315未提供数字".
    - Handles canonical equivalence: "1315.90" == "1315.9", "+19.80%" == "19.8%".
    """
    if not text:
        return ""
    # Fail-closed: if no evidence was provided, do NOT replace anything.
    if not evidence_text or not evidence_text.strip():
        return text

    allowed = _build_allowed_set(evidence_text)

    def _replace(m: re.Match) -> str:
        token = m.group(0)
        if token in allowed:
            return token
        if _canonicalize_number(token) in allowed:
            return token
        return "未提供数字"

    return _NUMERIC_RE.sub(_replace, text)


class NumericValidationResult(TypedDict):
    """Structured result of numeric claim validation.

    Fields
    ------
    valid : bool
        True only when all numeric tokens in *text* are traceable to evidence
        and evidence itself was available.
    reason : str
        One of:
        - "ok"                        — all numbers verified
        - "numeric_evidence_missing"  — no evidence; numbers cannot be verified
        - "unsupported_numbers_found" — evidence present but contains un-sourced numbers
    unsupported_tokens : list[str]
        Tokens in *text* that could not be matched to evidence (empty when
        evidence is absent, because we cannot enumerate them without replacing).
    evidence_available : bool
        Whether *evidence_text* was non-empty.
    replaced_count : int
        Number of tokens that were replaced / cannot be verified (0 when
        evidence is absent, because fail-closed returns text unchanged).
    """
    valid: bool
    reason: str
    unsupported_tokens: list
    evidence_available: bool
    replaced_count: int


def validate_numeric_claims(text: str, evidence_text: str) -> NumericValidationResult:
    """Validate every numeric token in *text* against *evidence_text*.

    FAIL-CLOSED: when *evidence_text* is absent, returns ``valid=False`` with
    ``reason="numeric_evidence_missing"`` if the text contains any numeric tokens.
    This prevents callers from publishing a ``success`` status for responses that
    cannot be verified.

    Use this function to gate status assignment::

        vr = validate_numeric_claims(final_text, evidence_text)
        status = "success" if vr["valid"] else "partial_success"
    """
    if not text:
        return NumericValidationResult(
            valid=True,
            reason="ok",
            unsupported_tokens=[],
            evidence_available=bool(evidence_text and evidence_text.strip()),
            replaced_count=0,
        )

    evidence_available = bool(evidence_text and evidence_text.strip())

    if not evidence_available:
        # No evidence: cannot verify any number in the text.
        numeric_tokens = _NUMERIC_RE.findall(text)
        if numeric_tokens:
            return NumericValidationResult(
                valid=False,
                reason="numeric_evidence_missing",
                unsupported_tokens=[],   # can't enumerate without replacement pass
                evidence_available=False,
                replaced_count=0,
            )
        # Text has no numerics — trivially ok even without evidence
        return NumericValidationResult(
            valid=True,
            reason="ok",
            unsupported_tokens=[],
            evidence_available=False,
            replaced_count=0,
        )

    # Evidence is available — check each token against the allowed set
    allowed = _build_allowed_set(evidence_text)
    unsupported: list[str] = []
    for m in _NUMERIC_RE.finditer(text):
        token = m.group(0)
        if token not in allowed and _canonicalize_number(token) not in allowed:
            unsupported.append(token)

    if unsupported:
        return NumericValidationResult(
            valid=False,
            reason="unsupported_numbers_found",
            unsupported_tokens=unsupported,
            evidence_available=True,
            replaced_count=len(unsupported),
        )
    return NumericValidationResult(
        valid=True,
        reason="ok",
        unsupported_tokens=[],
        evidence_available=True,
        replaced_count=0,
    )


def has_sanitization_artifacts(text: str) -> bool:
    """Return True when *text* contains sanitization markers left by output guards.

    These markers indicate incomplete evidence coverage or path-redaction side
    effects in the final answer, and callers should downgrade status accordingly::

        if has_sanitization_artifacts(answer):
            status = "partial_success"

    Markers checked:
    - ``未提供数字``  — numeric claim had no evidence match
    - ``[path]``       — absolute filesystem path was redacted
    """
    return "未提供数字" in text or "[path]" in text


def sanitize_specialist_output(text: str, *, evidence_text: str = "") -> str:
    text = text or ""
    text = re.sub(r"\b(?:None|null|NaN|nan|inf|\+inf|-inf)\b", _MISSING, text)
    text = _CREDENTIAL_RE.sub(r"\1=[redacted]", text)
    text = _CREDENTIAL_WORD_RE.sub("credential", text)
    text = _ABS_PATH_RE.sub("[path]", text)
    for phrase, replacement in _BANNED_REPLACEMENTS:
        text = text.replace(phrase, replacement)
    return remove_unsupported_numbers(text, evidence_text)


def detect_focus(question: str | None, default: str = "wide") -> str:
    q = (question or "").strip()
    if not q:
        return default
    if re.search(r"ROE|净资产收益率", q, re.IGNORECASE) and re.search(r"同行|对比|比较|比", q):
        return "roe_peer"
    patterns = {
        "cashflow": r"现金流|经营现金",
        "valuation": r"估值|PE|PB|市盈率|市净率",
        "profitability": r"ROE|毛利率|净利率|盈利|利润",
        "volume": r"成交量|量能|放量|缩量",
        "regulatory_news": r"监管|处罚|问询|立案|公告",
    }
    for focus, pattern in patterns.items():
        if re.search(pattern, q, re.IGNORECASE):
            return focus
    if len(q) <= 18:
        return "narrow"
    return default


def build_boundary_instruction(focus: str = "wide") -> str:
    narrow = focus not in {"", "wide"}
    scope_line = (
        "当前问题为窄问题，只输出与 focus 直接相关的章节，不填充无关模板。"
        if narrow else
        "当前问题为宽问题，可输出完整结构。"
    )
    return f"""\
【统一回答边界】
请把回答清晰区分为四层：
1. observed_facts：仅来自当前输入数据，不得加入新事实。
2. analysis：只能解释 observed_facts，不得添加未提供事实。
3. limitations：说明缺失字段、时间范围、数据质量和方法限制。
4. watch_items：后续观察变量，不得写成预测或买卖指令。
{scope_line}

禁止使用模型记忆补股票数据、估算缺失字段、混用不同日期/股票/market、虚构来源或页码、输出 chain of thought、直接买卖指令或确定性涨跌预测。"""
