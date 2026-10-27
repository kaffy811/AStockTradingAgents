"""A reader-facing report uses only supported evidence, without a missing-field inventory."""
from __future__ import annotations

import re
from app.agents.language_utils import OUTPUT_LANGUAGE_LABELS

BEGINNER_SYSTEM = """你是面向 A 股入门读者的股票研究讲解员。只使用输入中的已有证据，先说人话，再给少量数字。
不补资料、不猜缺失数值、不计算新的财务指标、不预测涨跌或目标价、不提供买卖指令。
没有可靠数据的字段和维度直接不写，不生成空章节，也不列“未获取、数据缺失、无法评价”的清单。
不得输出占位符、provider/SDK/内部字段、覆盖评分、复杂执行记录。
先用 2–3 句说明已经知道的情况，再挑最多 3 个有证据支持的重点。每个重点最多 2 句话。
术语尽量不用；必须出现时马上用一句白话解释。例如均线是“最近一段时间的平均价格”。
把价格变化说成价格变化，把公司经营说成经营，不强行解释股价原因。
只写已经发生的事实和温和解释，禁止从相对低点推演后续下跌路径。
同行数据只有报告期、单位和统计口径一致时才能比较；否则整个比较不写，不绕道排名。
如果输入涉及银行负债数据，不能按制造企业的标准判断银行风险；输入不涉及的项目不要额外科普。
收入和利润增长只代表这两项增长，不扩大为公司整体稳健或经营平稳。
只保留支持实际解读所需的日期、统计窗口和来源；重要的时期差异不能隐去后继续比较。
根据可用事实选择自然标题，如“先看懂这几点”“最近股价怎么走”“公司生意怎么样”“值得留意的事”。
不要照搬所有标题，不必重复同一数字，不生成长篇风险与数据限制章节。不要写“这里只有哪些数据”“其他方面暂不展开”等旁白。
全文约 350–600 个中文字（其他语言同等阅读长度），结尾仅一句“仅供了解和研究，不构成投资建议。”。
"""

SPECIALIST_SYSTEM = """你是一名面向股票新手的研究讲解员，只能使用本次输入已有的真实证据。
仅分析指定维度，不借用其他维度或模型记忆补充信息。没有数据的字段直接跳过，不列缺失清单、不生成空章节。
输入中的占位符、未提供数字、null、不可用、来源异常都不是可分析事实，不得复述或据此判断公司优劣。
写 2–4 个简短要点：已经发生了什么、普通读者该怎样理解。不要机械输出 observed_facts/analysis/limitations/watch_items。
不提供买卖建议或目标价、不预测涨跌、不新增指标计算或单位换算。银行负债不能按制造业风险标准解读。
同行数据报告期、单位、口径不一致时不做数值比较、排名或相对优劣判断。
新闻仅使用能确认属于目标公司的内容，证券代码歧义或截断片段不能作为公司事件。
只保留引用事实的日期和必要来源；用日常语言，少用缩写，必要术语附一句白话解释。
若指定维度根本没有真实事实，返回空字符串，不编造内容或输出“没有获取数据”。
"""

_MISSING = re.compile(r'暂不展开|其他方面|暂无|数据不足|未提供数字|\[缺失\]|\[不可用\]|数据缺失|字段缺失|未获取|未返回|无法评估|无法评价|不可用|missing|unavailable|\bnull\b', re.I)
_UNCOMPARABLE = re.compile(r'报告期不一致|报告期.*不同|报告期.*不匹配|period.*mismatch|different reporting period|inconsistent.*period|target.*Q3.*peer.*H1', re.I)


def clean_evidence(text: str) -> str:
    if not text or text.lstrip().startswith('['):
        return ''
    # Remove affected sentences, not just the missing number inside a claim.
    parts = re.split(r'(?<=[。！？])|\n|(?<=[.!?])\s+(?=[A-Z])', text)
    kept = [p.strip() for p in parts if p.strip() and not _MISSING.search(p)]
    def heading(value):
        return bool(re.fullmatch(r'#{1,6} .+|\*\*[^*]+\*\*', value))
    return '\n\n'.join(value for index, value in enumerate(kept)
                        if not (heading(value) and (index + 1 == len(kept) or heading(kept[index + 1]))))


def beginner_messages(sections: dict[str, str], identity: str, language: str) -> list[dict]:
    usable = {}
    for key, value in sections.items():
        if key == 'peer_comparison' and _UNCOMPARABLE.search(value or ''):
            continue
        if key == 'news' and re.search(r'代码歧义|000001\.SH|code ambiguity', value or '', re.I):
            continue
        cleaned = clean_evidence(value)
        if cleaned:
            usable[key] = cleaned[:2400]
    if not usable:
        return []
    label = OUTPUT_LANGUAGE_LABELS.get(language, '简体中文')
    evidence = '\n\n'.join(f'【{key}】\n{value}' for key, value in usable.items())
    return [
        {'role': 'system', 'content': BEGINNER_SYSTEM},
        {'role': 'user', 'content': f'股票：{identity}\n使用{label}，标题也使用该语言。\n只讲以下已有事实；未列项目完全跳过：\n{evidence}'},
    ]


def beginner_fallback(sections: dict[str, str], identity: str, language: str) -> str:
    messages = beginner_messages(sections, identity, language)
    if not messages:
        return ''
    facts = messages[-1]['content'].split('只讲以下已有事实；未列项目完全跳过：\n', 1)[-1]
    labels = ({'technical':'股价变化', 'fundamental':'公司生意', 'peer_comparison':'同行公司', 'news':'新闻动态'}
              if language.startswith('zh') else
              {'technical':'Price changes', 'fundamental':'Company results', 'peer_comparison':'Peers', 'news':'News'})
    for key, label in labels.items():
        facts = facts.replace(f'【{key}】', f'## {label}')
    # Retain actual specialist prose, not an invented synthesis when the model fails.
    footer = '仅供了解和研究，不构成投资建议。' if language.startswith('zh') else 'For information and research only; not investment advice.'
    return f'# {identity}\n\n' + facts + '\n\n' + footer


def has_financial_evidence(snapshot: dict) -> bool:
    import math
    def numeric(value):
        if isinstance(value, bool) or value is None:
            return False
        if isinstance(value, dict):
            return any(numeric(v) for v in value.values())
        try:
            return math.isfinite(float(value))
        except (ValueError, TypeError):
            return False
    return any(numeric(snapshot.get(key)) for key in (
        'valuation', 'profitability', 'growth', 'cashflow', 'financial_health'))


def peers_have_matching_periods(snapshot: dict) -> bool:
    peers = snapshot.get('peers') or []
    dates = snapshot.get('data_quality', {}).get('latest_report_dates') or {}
    values = list(dates.values())
    return bool(peers) and len(values) >= len(peers) + 1 and all(values) and len(set(values)) == 1


def supported_reader_report(report: str, sections: dict[str, str]) -> str:
    """Keep exact evidence guards while allowing equivalent human-readable dates/declines.

    Protect only the *specific* supported downward phrase, never add an unsigned
    magnitude globally (which would also permit an unsupported upward claim).
    """
    from app.agents.specialist_analysis_utils import sanitize_specialist_output
    evidence = '\n'.join(sections.values())
    protected = {}
    def protect(value):
        marker = chr(0xE000 + len(protected))
        protected[marker] = value
        return marker
    for year, month, day in re.findall(r'(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)', evidence):
        natural = f'{year}年{int(month)}月{int(day)}日'
        report = report.replace(natural, protect(natural)) if natural in report else report
    negatives = {float(number) for number in re.findall(r'[-−](\d+(?:\.\d+)?)%', evidence)}
    def decline(match):
        return protect(match.group(0)) if float(match.group(1)) in negatives else match.group(0)
    report = re.sub(r'(?:下跌|下降|减少|回落|降低|跌)[^\d\n]{0,3}(\d+(?:\.\d+)?)%', decline, report)
    report = sanitize_specialist_output(report, evidence_text=evidence)
    for marker, value in protected.items():
        report = report.replace(marker, value)
    return clean_evidence(report)
