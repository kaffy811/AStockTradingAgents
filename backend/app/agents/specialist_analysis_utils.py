"""Shared formatting and output guards for specialist analysis agents."""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

_MISSING = "数据缺失"
_NUMERIC_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?")
_ABS_PATH_RE = re.compile(r"(/[A-Za-z0-9_.@-]+)+")
_CREDENTIAL_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*\S+")
_CREDENTIAL_WORD_RE = re.compile(r"(?i)api[_-]?key|secret|token|password")

_BANNED_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("强烈买入", "不提供买卖指令"),
    ("强烈卖出", "不提供买卖指令"),
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


def evidence_numbers(text: str) -> set[str]:
    return set(_NUMERIC_RE.findall(text or ""))


def remove_unsupported_numbers(text: str, evidence_text: str) -> str:
    """Replace numeric claims not traceable to evidence text.

    This is intentionally simple. It protects against obvious hallucinated
    precise numbers while preserving section headings because Chinese markdown
    headings here are not numeric.
    """
    allowed = evidence_numbers(evidence_text)
    if not text or not allowed:
        return _NUMERIC_RE.sub("未提供数字", text or "")
    for token in sorted(evidence_numbers(text), key=len, reverse=True):
        if token not in allowed:
            text = text.replace(token, "未提供数字")
    return text


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
    patterns = {
        "cashflow": r"现金流|经营现金",
        "valuation": r"估值|PE|PB|市盈率|市净率",
        "profitability": r"ROE|毛利率|净利率|盈利|利润",
        "volume": r"成交量|量能|放量|缩量",
        "regulatory_news": r"监管|处罚|问询|立案|公告",
        "roe_peer": r"ROE|净资产收益率",
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
