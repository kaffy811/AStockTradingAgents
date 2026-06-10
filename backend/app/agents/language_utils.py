"""
language_utils — Agent-level 输出语言支持工具。

提供：
  - VALID_OUTPUT_LANGUAGES  frozenset
  - OUTPUT_LANGUAGE_LABELS  dict
  - normalize_output_language()
  - build_output_language_instruction()

用法：
    from app.agents.language_utils import build_output_language_instruction

注意：
  - 该模块不 import 任何 app.agents 子模块，避免循环依赖。
  - zh-CN 返回空指令（保持原有行为，不注入任何额外 token）。
"""

from __future__ import annotations

VALID_OUTPUT_LANGUAGES: frozenset[str] = frozenset({
    "zh-CN", "en-US", "zh-TW", "ja-JP", "ko-KR", "es-ES",
})

OUTPUT_LANGUAGE_LABELS: dict[str, str] = {
    "zh-CN": "简体中文",
    "en-US": "English (US)",
    "zh-TW": "繁體中文",
    "ja-JP": "日本語",
    "ko-KR": "한국어",
    "es-ES": "Español",
}


def normalize_output_language(output_language: str | None) -> str:
    """
    校验并返回合法的语言代码，未知值 fallback 到 'zh-CN'。

    >>> normalize_output_language("en-US")
    'en-US'
    >>> normalize_output_language(None)
    'zh-CN'
    >>> normalize_output_language("xx-XX")
    'zh-CN'
    """
    if output_language in VALID_OUTPUT_LANGUAGES:
        return output_language
    return "zh-CN"


# ── Report section label registry ────────────────────────────────────────────
#
# 13 keys used by exportMarkdown.js / PrintReportView.vue and any future caller
# that needs localised section headings.
#
# Keys:
#   scope_*            — report title for each analysis_scope value
#   section_*          — sub-report heading shown in export / print
#   agent_status       — "Agent 执行状态" heading
#   data_quality       — "数据质量提示" heading
#   no_warnings        — empty-warnings placeholder text

REPORT_SECTION_LABELS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "scope_comprehensive":         "综合分析报告",
        "scope_technical_only":        "技术面分析报告",
        "scope_fundamental_only":      "基本面分析报告",
        "scope_peer_only":             "同行对比分析报告",
        "scope_news_only":             "新闻面分析报告",
        "scope_technical_fundamental": "技术面与基本面分析报告",
        "section_technical":           "技术面分析",
        "section_fundamental":         "基本面分析",
        "section_peer_comparison":     "同行对比分析",
        "section_news":                "新闻面分析",
        "agent_status":                "Agent 执行状态",
        "data_quality":                "数据质量提示",
        "no_warnings":                 "暂无数据质量提示。",
    },
    "en-US": {
        "scope_comprehensive":         "Comprehensive Analysis Report",
        "scope_technical_only":        "Technical Analysis Report",
        "scope_fundamental_only":      "Fundamental Analysis Report",
        "scope_peer_only":             "Peer Comparison Report",
        "scope_news_only":             "News Analysis Report",
        "scope_technical_fundamental": "Technical & Fundamental Report",
        "section_technical":           "Technical Analysis",
        "section_fundamental":         "Fundamental Analysis",
        "section_peer_comparison":     "Peer Comparison",
        "section_news":                "News Analysis",
        "agent_status":                "Agent Execution Status",
        "data_quality":                "Data Quality Notes",
        "no_warnings":                 "No data quality issues.",
    },
    "zh-TW": {
        "scope_comprehensive":         "綜合分析報告",
        "scope_technical_only":        "技術面分析報告",
        "scope_fundamental_only":      "基本面分析報告",
        "scope_peer_only":             "同行對比分析報告",
        "scope_news_only":             "新聞面分析報告",
        "scope_technical_fundamental": "技術面與基本面分析報告",
        "section_technical":           "技術面分析",
        "section_fundamental":         "基本面分析",
        "section_peer_comparison":     "同行對比分析",
        "section_news":                "新聞面分析",
        "agent_status":                "Agent 執行狀態",
        "data_quality":                "數據質量提示",
        "no_warnings":                 "暫無數據質量提示。",
    },
    "ja-JP": {
        "scope_comprehensive":         "総合分析レポート",
        "scope_technical_only":        "テクニカル分析レポート",
        "scope_fundamental_only":      "ファンダメンタル分析レポート",
        "scope_peer_only":             "同業比較レポート",
        "scope_news_only":             "ニュース分析レポート",
        "scope_technical_fundamental": "テクニカル・ファンダメンタル分析レポート",
        "section_technical":           "テクニカル分析",
        "section_fundamental":         "ファンダメンタル分析",
        "section_peer_comparison":     "同業比較",
        "section_news":                "ニュース分析",
        "agent_status":                "エージェント実行状況",
        "data_quality":                "データ品質メモ",
        "no_warnings":                 "データ品質の問題はありません。",
    },
    "ko-KR": {
        "scope_comprehensive":         "종합 분석 보고서",
        "scope_technical_only":        "기술 분석 보고서",
        "scope_fundamental_only":      "기본 분석 보고서",
        "scope_peer_only":             "동종 비교 보고서",
        "scope_news_only":             "뉴스 분석 보고서",
        "scope_technical_fundamental": "기술·기본 분석 보고서",
        "section_technical":           "기술 분석",
        "section_fundamental":         "기본 분석",
        "section_peer_comparison":     "동종 비교",
        "section_news":                "뉴스 분석",
        "agent_status":                "에이전트 실행 상태",
        "data_quality":                "데이터 품질 메모",
        "no_warnings":                 "데이터 품질 문제 없음.",
    },
    "es-ES": {
        "scope_comprehensive":         "Informe de Análisis Integral",
        "scope_technical_only":        "Informe de Análisis Técnico",
        "scope_fundamental_only":      "Informe de Análisis Fundamental",
        "scope_peer_only":             "Informe de Comparación entre Pares",
        "scope_news_only":             "Informe de Análisis de Noticias",
        "scope_technical_fundamental": "Informe Técnico y Fundamental",
        "section_technical":           "Análisis Técnico",
        "section_fundamental":         "Análisis Fundamental",
        "section_peer_comparison":     "Comparación entre Pares",
        "section_news":                "Análisis de Noticias",
        "agent_status":                "Estado de los Agentes",
        "data_quality":                "Notas de Calidad de Datos",
        "no_warnings":                 "Sin problemas de calidad de datos.",
    },
}


def report_label(output_language: str | None, key: str) -> str:
    """
    Retrieve a localised section label from REPORT_SECTION_LABELS.

    Falls back to zh-CN if the language is not found.
    Falls back to the key itself if the key is missing in both.

    >>> report_label("en-US", "scope_comprehensive")
    'Comprehensive Analysis Report'
    >>> report_label(None, "scope_comprehensive")
    '综合分析报告'
    """
    lang = normalize_output_language(output_language)
    lang_labels = REPORT_SECTION_LABELS.get(lang, REPORT_SECTION_LABELS["zh-CN"])
    return lang_labels.get(key, REPORT_SECTION_LABELS["zh-CN"].get(key, key))


def build_output_language_instruction(output_language: str | None) -> str:
    """
    构建追加到 Agent user prompt 末尾的语言指令。

    - zh-CN 返回空字符串，不注入任何指令（保持原有 token 量）。
    - 其余语言返回【输出语言要求】块，说明目标语言。
    - 股票名称、股票代码、公司专有名词、新闻标题、财务指标缩写
      （PE、PB、ROE、MACD、RSI、MA5、MA10、MA20、MA60）允许保留原文。
    - 其余解释、章节标题、摘要、数据说明、风险提示使用目标语言。
    - 严禁投资建议性措辞，仅供研究参考。

    Returns:
        str — 空字符串（zh-CN）或语言指令块（其他语言）。
    """
    lang = normalize_output_language(output_language)
    if lang == "zh-CN":
        return ""
    label = OUTPUT_LANGUAGE_LABELS[lang]
    return (
        f"\n\n【输出语言要求】\n"
        f"请使用 {label} 撰写本次分析内容。\n"
        f"以下内容允许保留原文：股票名称、股票代码、公司专有名词、新闻标题、"
        f"财务指标缩写（如 PE、PB、ROE、MACD、RSI、MA5、MA10、MA20、MA60）。\n"
        f"其余解释、章节标题、摘要、数据说明、风险提示均应使用 {label}。\n"
        f"本报告仅供研究参考，不构成投资建议。"
    )
