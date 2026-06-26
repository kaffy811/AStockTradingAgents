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
# 25 keys used by exportMarkdown.js / PrintReportView.vue and any future caller
# that needs localised section headings.
#
# Keys:
#   scope_*            — report title for each analysis_scope value
#   section_*          — sub-report heading shown in export / print
#   agent_status       — "Agent 执行状态" heading
#   data_quality       — "数据质量提示" heading
#   no_warnings        — empty-warnings placeholder text
#   M51 additions:
#   h_summary_conclusion  — single-agent "摘要结论" section heading
#   h_synthesis_card      — comprehensive "综合结论卡片" section heading
#   h_four_dimensions     — comprehensive "四面结论汇总" section heading
#   card_overall          — "综合判断" card field label
#   card_one_line         — "一句话结论" card field label
#   card_contradiction    — "核心矛盾" card field label
#   card_positive         — "正面因素" card field label
#   card_risks            — "主要风险" card field label
#   card_followup         — "后续观察重点" card field label
#   card_completeness     — "数据完整度" card field label
#   agent_conclusion      — "本面结论" single-agent card field label
#   agent_credibility     — "数据可信度" single-agent card field label

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
        # M51 additions
        "h_summary_conclusion":        "摘要结论",
        "h_synthesis_card":            "综合结论卡片",
        "h_four_dimensions":           "四面结论汇总",
        "card_overall":                "综合判断",
        "card_one_line":               "一句话结论",
        "card_contradiction":          "核心矛盾",
        "card_positive":               "正面因素",
        "card_risks":                  "主要风险",
        "card_followup":               "后续观察重点",
        "card_completeness":           "数据完整度",
        "agent_conclusion":            "本面结论",
        "agent_credibility":           "数据可信度",
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
        # M51 additions
        "h_summary_conclusion":        "Summary Conclusion",
        "h_synthesis_card":            "Synthesis Conclusion Card",
        "h_four_dimensions":           "Four-Dimension Summary",
        "card_overall":                "Overall Judgment",
        "card_one_line":               "One-line Conclusion",
        "card_contradiction":          "Key Contradiction",
        "card_positive":               "Positive Factors",
        "card_risks":                  "Main Risks",
        "card_followup":               "Follow-up Focus",
        "card_completeness":           "Data Completeness",
        "agent_conclusion":            "Dimension Conclusion",
        "agent_credibility":           "Data Credibility",
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
        # M51 additions
        "h_summary_conclusion":        "摘要結論",
        "h_synthesis_card":            "綜合結論卡片",
        "h_four_dimensions":           "四面結論彙總",
        "card_overall":                "綜合判斷",
        "card_one_line":               "一句話結論",
        "card_contradiction":          "核心矛盾",
        "card_positive":               "正面因素",
        "card_risks":                  "主要風險",
        "card_followup":               "後續觀察重點",
        "card_completeness":           "數據完整度",
        "agent_conclusion":            "本面結論",
        "agent_credibility":           "數據可信度",
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
        # M51 additions
        "h_summary_conclusion":        "要約結論",
        "h_synthesis_card":            "総合結論カード",
        "h_four_dimensions":           "四次元結論サマリー",
        "card_overall":                "総合判断",
        "card_one_line":               "一言結論",
        "card_contradiction":          "主要矛盾",
        "card_positive":               "プラス要因",
        "card_risks":                  "主なリスク",
        "card_followup":               "フォローアップ重点",
        "card_completeness":           "データ完全性",
        "agent_conclusion":            "次元結論",
        "agent_credibility":           "データ信頼性",
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
        # M51 additions
        "h_summary_conclusion":        "요약 결론",
        "h_synthesis_card":            "종합 결론 카드",
        "h_four_dimensions":           "4차원 결론 요약",
        "card_overall":                "종합 판단",
        "card_one_line":               "한 줄 결론",
        "card_contradiction":          "핵심 모순",
        "card_positive":               "긍정적 요인",
        "card_risks":                  "주요 위험",
        "card_followup":               "후속 관찰 중점",
        "card_completeness":           "데이터 완전성",
        "agent_conclusion":            "차원 결론",
        "agent_credibility":           "데이터 신뢰성",
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
        # M51 additions
        "h_summary_conclusion":        "Conclusión Resumida",
        "h_synthesis_card":            "Tarjeta de Conclusión Integral",
        "h_four_dimensions":           "Resumen de Cuatro Dimensiones",
        "card_overall":                "Juicio General",
        "card_one_line":               "Conclusión en Una Línea",
        "card_contradiction":          "Contradicción Clave",
        "card_positive":               "Factores Positivos",
        "card_risks":                  "Riesgos Principales",
        "card_followup":               "Enfoque de Seguimiento",
        "card_completeness":           "Completitud de Datos",
        "agent_conclusion":            "Conclusión Dimensional",
        "agent_credibility":           "Credibilidad de Datos",
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
