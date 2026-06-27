"""
Unified Financial Safety Post-Processing Layer (C26)

All final_answer outputs must pass through sanitize_financial_answer()
before reaching the frontend. This module provides deterministic rule-based
cleaning — no LLM calls, no I/O, pure text transforms.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# C26.2  Unverified financial metrics
# ---------------------------------------------------------------------------

# Metric types that require verified tool data before numbers can appear
_METRIC_PATTERNS: dict[str, list[re.Pattern]] = {
    "pe": [
        re.compile(r"市盈率[（(]?[Pp][Ee][）)]?\s*[约为是：:]\s*\d[\d.]*[xX倍]?"),
        re.compile(r"[Pp][Ee]\s*[约为是：:]\s*\d[\d.]*"),
        re.compile(r"市盈率约?\s*\d[\d.]*"),
    ],
    "pb": [
        re.compile(r"市净率[（(]?[Pp][Bb][）)]?\s*[约为是：:]\s*\d[\d.]*[xX倍]?"),
        re.compile(r"[Pp][Bb]\s*[约为是：:]\s*\d[\d.]*"),
        re.compile(r"市净率约?\s*\d[\d.]*"),
    ],
    "revenue": [
        re.compile(r"营[业收].*?收入.*?约?\s*\d[\d.]*\s*[亿万元百千]+"),
        re.compile(r"总营收.*?约?\s*\d[\d.]*\s*[亿万元百千]+"),
    ],
    "profit": [
        re.compile(r"净利润.*?约?\s*\d[\d.]*\s*[亿万元百千]+"),
        re.compile(r"归母净利润.*?约?\s*\d[\d.]*\s*[亿万元百千]+"),
    ],
    "dividend_yield": [
        re.compile(r"股息率约?为?\s*\d[\d.]*\s*%"),
        re.compile(r"股息率约?\s*\d[\d.]*\s*%"),
        re.compile(r"派息率约?为?\s*\d[\d.]*\s*%"),
        re.compile(r"分红率约?为?\s*\d[\d.]*\s*%"),
        re.compile(r"对应约\s*\d[\d.]*\s*%(?:的股息率)?"),
        re.compile(r"按当前[股]?价粗算.*?股息率"),
        re.compile(r"以当前[股]?价[格]?(?:粗)?计算.*?股息率"),
        re.compile(r"简单计算.*?股息率"),
        re.compile(r"股息率.*?对应.*?\d[\d.]*\s*%"),
        # Raw arithmetic that constitutes implicit calculation: e.g. "28.024 ÷ 1168.63"
        re.compile(r"\d[\d.]*\s*[÷/]\s*\d[\d.]*\s*(?:=|≈|约)?\s*\d[\d.]*\s*%"),
        # Explicit calculation phrases
        re.compile(r"(?:按|以)当前股价计算"),
        re.compile(r"粗算(?:股息率|收益率|派息率)"),
    ],
    "price": [
        re.compile(r"目标价(?:位)?约?\s*\d[\d.]*\s*元"),
        re.compile(r"合理估值约?\s*\d[\d.]*\s*元"),
    ],
}

_METRIC_REPLACEMENT = {
    "pe": "（市盈率数据需通过工具获取，此处不自行估算）",
    "pb": "（市净率数据需通过工具获取，此处不自行估算）",
    "revenue": "（营收数据需通过工具获取，此处不自行估算）",
    "profit": "（净利润数据需通过工具获取，此处不自行估算）",
    "dividend_yield": "（工具未返回完整公告原文或相关比率字段，因此不计算具体股息率、派息率或收益率）",
    "price": "（目标价需通过工具获取，此处不自行估算）",
}

# context keys indicating verified data is present
_METRIC_CONTEXT_KEYS: dict[str, list[str]] = {
    "pe": ["pe_ratio", "pe", "valuation"],
    "pb": ["pb_ratio", "pb", "valuation"],
    "revenue": ["revenue", "income_statement", "financials"],
    "profit": ["net_profit", "profit", "income_statement", "financials"],
    "dividend_yield": ["dividend_yield", "dividend", "dividends"],
    "price": ["target_price", "analyst_target"],
}


def has_verified_metric(context: dict | None, metric_type: str) -> bool:
    """Return True if the context contains verified data for this metric type."""
    if not context:
        return False
    keys = _METRIC_CONTEXT_KEYS.get(metric_type, [])
    for k in keys:
        if k in context and context[k] not in (None, "", [], {}):
            return True
    return False


def sanitize_unverified_financial_metrics(text: str, context: dict | None = None) -> str:
    """Remove or replace financial metric numbers that are not backed by tool data."""
    for metric_type, patterns in _METRIC_PATTERNS.items():
        if has_verified_metric(context, metric_type):
            continue  # data was actually fetched — leave it
        replacement = _METRIC_REPLACEMENT[metric_type]
        for pat in patterns:
            text = pat.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# C26.3  Investment advice
# ---------------------------------------------------------------------------

_ADVICE_BAN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"(?:建议|推荐|可以|适合|值得)[买入购\s]*(?:该股|该股票|这只股票|此股)"),
        "（本系统不提供买入建议，请结合自身风险偏好判断）",
    ),
    (
        re.compile(r"(?:建议|推荐|可以|适合)[卖出抛售\s]*(?:该股|该股票|这只股票|此股)"),
        "（本系统不提供卖出建议，请结合自身风险偏好判断）",
    ),
    (
        re.compile(r"(?:建议|推荐)(?:持有|继续持有)(?:该股|该股票|这只股票|此股)"),
        "（本系统不提供持有建议，请结合自身风险偏好判断）",
    ),
    (
        re.compile(r"(?:强烈)?建议(?:立即|尽快)?(?:买入|购入|抄底|加仓)"),
        "（本系统不提供操作建议）",
    ),
    (
        re.compile(r"(?:强烈)?建议(?:立即|尽快)?(?:卖出|清仓|减仓|止损)"),
        "（本系统不提供操作建议）",
    ),
    (
        re.compile(r"(?:可以|适合)(?:长期|短期)?(?:投资|布局|配置)(?:该股|该股票|这只股票)"),
        "（本系统不提供投资建议，仅供研究参考）",
    ),
]

_ADVICE_COMPLIANCE = "\n\n_仅供研究参考，不构成投资建议。_"


def sanitize_investment_advice(text: str, context: dict | None = None) -> str:
    """Replace direct buy/sell/hold recommendations with compliance statements.

    Note: The compliance footer (_仅供研究参考) is NOT appended here because
    this function is called on individual text fields of dict payloads where
    the dict already has a dedicated 'disclaimer' key.  The footer is appended
    at the top-level str branch of sanitize_financial_answer instead.
    """
    for pat, replacement in _ADVICE_BAN_PATTERNS:
        text = pat.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# C26.4  Certainty claims / internal enums / tool error messages
# ---------------------------------------------------------------------------

_CERTAINTY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?:必然|肯定|一定会?|稳赚|包赚|稳涨|必涨|稳跌|必跌)(?:上涨|下跌|涨|跌|盈利|亏损|赚|赔)?"), "（走势存在不确定性）"),
    (re.compile(r"(?:没有|没有任何)风险"), "（任何投资均存在风险）"),
    (re.compile(r"零风险"), "（任何投资均存在风险）"),
    (re.compile(r"百分之百(?:确定|保证|盈利)"), "（不存在百分之百确定的投资结果）"),
]

_ENUM_REPLACEMENTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bget_stock_quote_tool\b"), "实时行情工具"),
    (re.compile(r"\bget_news_tool\b"), "新闻搜索工具"),
    (re.compile(r"\bget_financials_tool\b"), "财务数据工具"),
    (re.compile(r"\bget_fundamental_data_tool\b"), "基本面数据工具"),
    (re.compile(r"\bget_recent_reports_tool\b"), "历史报告工具"),
    (re.compile(r"\bwatchlist_list_tool\b"), "自选股工具"),
    (re.compile(r"\breport_list_tool\b"), "报告列表工具"),
    (re.compile(r"\bfinancial_rag_search_tool\b"), "金融知识库工具"),
    (re.compile(r"\buniversal_market_search_tool\b"), "市场综合搜索工具"),
    (re.compile(r"\bsearch_realtime_news_tool\b"), "实时新闻工具"),
    # SkillResult / internal type names
    (re.compile(r"\bSkillResult\b"), "分析结果"),
    (re.compile(r"\bAgentResponse\b"), "Agent响应"),
    (re.compile(r"\bGeneralFinancialAnswerSkill\b"), "金融问答"),
    (re.compile(r"\bReportExplanationSkill\b"), "报告解读"),
]

_TOOL_ERROR_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"(?:工具)?调用失败[：:][^\n。]*"),
        "（数据获取暂时失败，请稍后重试）",
    ),
    (
        re.compile(r"(?:API|接口)(?:错误|异常|超时)[：:][^\n。]*"),
        "（数据接口暂时不可用）",
    ),
    (
        re.compile(r"Traceback \(most recent call last\)[\s\S]*?(?=\n\n|\Z)"),
        "（内部错误，请稍后重试）",
    ),
    (
        re.compile(r"JSONDecodeError[：:][^\n]*"),
        "（数据解析异常，请稍后重试）",
    ),
    (
        re.compile(r"ConnectionError[：:][^\n]*"),
        "（网络连接异常，请稍后重试）",
    ),
    (
        re.compile(r"TimeoutError[：:][^\n]*"),
        "（请求超时，请稍后重试）",
    ),
]


def sanitize_certainty_claims(text: str) -> str:
    """Replace certainty claims (必涨/稳赚 etc.) with uncertainty acknowledgements."""
    for pat, replacement in _CERTAINTY_PATTERNS:
        text = pat.sub(replacement, text)
    return text


def sanitize_internal_enums(text: str) -> str:
    """Replace internal tool/class names with user-friendly Chinese labels."""
    for pat, replacement in _ENUM_REPLACEMENTS:
        text = pat.sub(replacement, text)
    return text


def sanitize_tool_error_messages(text: str) -> str:
    """Replace raw technical error strings with user-friendly messages."""
    for pat, replacement in _TOOL_ERROR_PATTERNS:
        text = pat.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# C26.5  News over-interpretation (always-on) + C28.2 dividend & theme filters
# ---------------------------------------------------------------------------

_NEWS_OVERINFERENCE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Pattern: "新闻标题说'X只股名单'但下文推断某股在列"
    (
        re.compile(r"(?:根据|由于|因为)?(?:该|上述)?新闻(?:标题)?(?:提到|显示|表明|说明)[^。\n]*名单[^。\n]*"
                   r"(?:可以|可见|因此|所以|表明|说明)[^。\n]*(?:在列|入围|包含在|属于)"),
        "（新闻标题仅提及名单存在，工具未返回完整名单正文，无法确认具体股票是否入围）",
    ),
    (
        re.compile(r"(?:上述|该)新闻中的[^。\n]*名单[^。\n]*(?:包括|包含|含有|涵盖)[^。\n]*该股"),
        "（工具未返回完整名单正文，无法确认该股票是否在列）",
    ),
    # Direct inference: "XXX在该分红名单中"
    (
        re.compile(r"\S+(?:在该|在上述|在此)(?:分红|名单|列表)[^。\n]*(?:中|内|之列)"),
        "（工具未返回完整名单正文，无法确认该股票是否在列）",
    ),
    # "可以推断XXX也将分红"
    (
        re.compile(r"(?:可以|可能|因此|所以)?推断[^。\n]*(?:也将|将会|应该会?)[分红派息]"),
        "（根据新闻标题无法推断其他股票是否分红，需查看完整公告）",
    ),
]


# C28.2/C28.3: dividend over-inference — only applies when verified news detail / financial data absent
_DIVIDEND_OVERINFERENCE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"(?:高额|大额|大规模|超额)分红"),
        "分红（注：大额分红判断需有完整公告数据支撑）",
    ),
    (
        re.compile(r"(?:已)?实施(?:了)?(?:大额|高额|超额|大规模)?大[额规模]+分红"),
        "（注：分红实施情况需有完整公告数据确认）",
    ),
    (
        re.compile(r"现金分红(?:能力)?(?:较强|充沛|强劲)"),
        "（工具仅返回新闻标题，无法确认现金分红能力，请查阅完整公告）",
    ),
    (
        re.compile(r"(?:反映|体现|表明|说明)[^。\n]{0,30}(?:盈利稳定|现金流充沛|财务健康)"),
        "（注：财务状况判断需有完整财报数据支撑，当前仅有新闻标题）",
    ),
    (
        re.compile(r"(?:表明|说明|意味着)公司(?:具备|拥有)?[^。\n]{0,20}分红(?:能力|意愿)"),
        "（工具仅返回新闻标题，无法确认公司分红能力，请查阅完整公告）",
    ),
    (
        re.compile(r"基于前期利润(?:分配|支撑|水平)?"),
        "（注：利润分配情况需有财报数据确认）",
    ),
    # C28.3: additional patterns observed in browser validation
    (
        re.compile(r"历史(?:高|丰厚|稳定)?分红(?:延续|继续|传统|惯例|记录)"),
        "（注：历史分红规律需有历年财报数据支撑，工具仅返回新闻标题）",
    ),
    (
        re.compile(r"留存收益(?:充足|较多|丰富|充裕)"),
        "（注：留存收益情况需有财报数据确认，工具仅返回新闻标题）",
    ),
    (
        re.compile(r"分红现金(?:较高|较大|充足)[^，。\n]{0,20}说明"),
        "（工具仅返回新闻标题，无法通过分红金额推断财务状况）",
    ),
    (
        re.compile(r"分红(?:体现|说明|反映)[^，。\n]{0,30}(?:盈利|利润|现金流|财务)"),
        "（工具仅返回新闻标题，无法通过分红新闻推断盈利或现金流状况）",
    ),
    (
        re.compile(r"(?:盈利质量|现金流状况)[^，。\n]{0,30}(?:较好|较强|充裕|良好|优质)"),
        "（注：盈利质量和现金流状况需财报数据支撑，工具仅返回新闻标题）",
    ),
    (
        re.compile(r"前期利润(?:支撑|支持|积累)[^，。\n]{0,20}分红"),
        "（注：利润支撑判断需有财报数据，工具仅返回新闻标题）",
    ),
]

_DIVIDEND_DISCLAIMER = (
    "\n\n_工具仅返回新闻标题，未提供完整公告原文或财务数据，"
    "因此不能进一步判断分红能力、盈利质量或现金流状况。_"
)

# C28.2/C28.3: AI/theme strong-attribution patterns — only applies when no verified_theme_classification
_THEME_ATTRIBUTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Generic strong-attribution terms
    (re.compile(r"核心供应商"),   "关联供应商（需公告或研报确认）"),
    (re.compile(r"关键耗材"),     "相关耗材（需公告或研报确认）"),
    (re.compile(r"主力供应商"),   "供应商（需公告或研报确认）"),
    (re.compile(r"核心标的"),     "相关个股（需公告或研报确认）"),
    (re.compile(r"直接受益(?:方|者)?"), "可能关联受益方（需公告或研报确认）"),
    (re.compile(r"强相关(?:个股|标的|公司)?"), "存在初步关联（需公告或研报确认）"),
    # C28.3: AI chip / device specific strong attributions observed in browser validation
    (
        re.compile(r"AI终端设备核心部件(?:供应商|制造商)?"),
        "可能与AI终端显示或部件存在间接关联（需公告、研报或主题标签进一步确认）",
    ),
    (
        re.compile(r"AI可穿戴(?:设备)?[^，。\n]{0,10}(?:材料|供应商|制造商)"),
        "可能与可穿戴设备材料环节存在间接关联（需公告或研报确认）",
    ),
    (
        re.compile(r"AI芯片基材"),
        "可能与半导体基材材料环节存在间接关联（需公告或研报确认）",
    ),
    (
        re.compile(r"AI芯片封装"),
        "可能与封测环节存在间接关联（需公告或研报确认）",
    ),
    (
        re.compile(r"AI芯片后道环节"),
        "可能与芯片后道工序存在间接关联（需公告或研报确认）",
    ),
    (
        re.compile(r"AI(?:上游|下游)[^，。\n]{0,15}(?:材料|设备|需求预期)"),
        "可能与AI产业链上下游存在间接关联（需公告或研报确认）",
    ),
    (
        re.compile(r"AI芯片(?:制造)?上游"),
        "可能与AI芯片制造上游材料或设备存在间接关联（需公告或研报确认）",
    ),
    (
        re.compile(r"AI设备直接关联"),
        "可能与AI设备产业链存在间接关联（需公告或研报确认）",
    ),
]

_THEME_DISCLAIMER = (
    "\n\n_当前结果主要基于热门股榜单和一般行业认知初步归类，"
    "不代表这些公司已被工具确认为AI设备主题股；"
    "需进一步通过公告或研报确认具体产业链关系。_"
)


def sanitize_dividend_overinference(text: str, context: dict | None = None) -> str:
    """
    C28.2/C28.3: Filter dividend over-inferences when only news titles are available.

    Skipped (returns text unchanged) when context has:
      - verified_news_detail=True  (full article body retrieved), OR
      - verified_financial_data=True (financial report data retrieved)

    When any pattern fires, appends _DIVIDEND_DISCLAIMER if not already present.
    """
    if context and (
        context.get("verified_news_detail") or context.get("verified_financial_data")
    ):
        return text
    modified = False
    for pat, replacement in _DIVIDEND_OVERINFERENCE_PATTERNS:
        new_text = pat.sub(replacement, text)
        if new_text != text:
            modified = True
            text = new_text
    # C28.3: append boundary disclaimer when any dividend over-inference was filtered
    if modified and _DIVIDEND_DISCLAIMER.strip() not in text:
        text = text + _DIVIDEND_DISCLAIMER
    return text


def sanitize_theme_attribution(text: str, context: dict | None = None) -> str:
    """
    C28.2: Downgrade strong AI-theme attributions when theme classification is unverified.

    If context.verified_theme_classification is True, returns text unchanged.
    Otherwise replaces "核心供应商 / 关键耗材 / 主力供应商 / 核心标的 / 直接受益 / 强相关"
    with softer alternatives and appends a boundary disclaimer if any substitution occurred.
    """
    if context and context.get("verified_theme_classification"):
        return text
    modified = False
    for pat, replacement in _THEME_ATTRIBUTION_PATTERNS:
        new_text = pat.sub(replacement, text)
        if new_text != text:
            modified = True
            text = new_text
    # T10: ensure boundary disclaimer is present when any attribution was downgraded
    if modified and _THEME_DISCLAIMER.strip() not in text:
        text = text + _THEME_DISCLAIMER
    return text


def sanitize_news_overinterpretation(text: str, context: dict | None = None) -> str:
    """Prevent over-inference from news titles when full article body is unavailable."""
    for pat, replacement in _NEWS_OVERINFERENCE_PATTERNS:
        text = pat.sub(replacement, text)
    # C28.2: dividend-specific over-inference (context-aware)
    text = sanitize_dividend_overinference(text, context)
    return text


# ---------------------------------------------------------------------------
# C26.1  Main entry point
# ---------------------------------------------------------------------------

_PRESERVE_FIELD_NAMES = {
    "sources", "data_quality", "cards", "tool_trace",
    "session_id", "event_type", "step_key", "step_label",
    "status", "error", "metadata",
}


def _sanitize_text(text: str, context: dict | None, append_footer: bool = False) -> str:
    """Apply all sanitization passes to a plain text string.

    append_footer should be True only when sanitizing a top-level str answer,
    not when sanitizing individual fields of a dict payload that already has
    a dedicated 'disclaimer' key.
    """
    text = sanitize_tool_error_messages(text)
    text = sanitize_internal_enums(text)
    text = sanitize_certainty_claims(text)
    text = sanitize_unverified_financial_metrics(text, context)
    text = sanitize_news_overinterpretation(text, context)
    text = sanitize_theme_attribution(text, context)  # C28.2
    text = sanitize_investment_advice(text, context)
    if append_footer and "_仅供研究参考" not in text:
        text = text + _ADVICE_COMPLIANCE
    return text


def sanitize_financial_answer(
    answer: str | dict | list | Any,
    context: dict | None = None,
) -> str | dict | list | Any:
    """
    Main entry point for the unified financial safety post-processing layer.

    Accepts:
      - str  → sanitizes and returns str
      - dict → sanitizes recognized text fields, preserves structural fields
      - list → recursively sanitizes each element
      - other → returned unchanged

    Args:
        answer:  The final_answer payload (str, dict, or list).
        context: Optional tool-call context dict. Keys like "dividend_yield",
                 "pe_ratio", etc. indicate which data is verified from tools.
    """
    if isinstance(answer, str):
        return _sanitize_text(answer, context, append_footer=True)

    if isinstance(answer, list):
        return [sanitize_financial_answer(item, context) for item in answer]

    if isinstance(answer, dict):
        result: dict = {}
        for k, v in answer.items():
            if k in _PRESERVE_FIELD_NAMES:
                result[k] = v  # structural fields — do not touch
            elif isinstance(v, str):
                # All string fields inside a dict are subfields — no footer
                result[k] = _sanitize_text(v, context, append_footer=False)
            elif isinstance(v, (dict, list)):
                result[k] = sanitize_financial_answer(v, context)
            else:
                result[k] = v
        return result

    return answer
