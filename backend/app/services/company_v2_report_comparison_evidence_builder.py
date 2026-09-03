"""Comparison evidence matrix for Company V2 explicit cross-report QA."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ComparisonTopic:
    key: str
    label: str
    aliases: tuple[str, ...]
    expects_numeric: bool = True


TOPICS: tuple[ComparisonTopic, ...] = (
    ComparisonTopic("revenue", "营业收入", ("营业收入", "主营业务收入", "收入")),
    ComparisonTopic("net_profit_parent", "归母净利润", ("归属于上市公司股东的净利润", "归母净利润", "净利润")),
    ComparisonTopic("operating_cash_flow", "经营活动现金流", ("经营活动产生的现金流量净额", "经营活动现金流", "经营现金流", "现金流量净额")),
    ComparisonTopic("risk", "主要风险", ("主要风险", "风险因素", "风险"), expects_numeric=False),
    ComparisonTopic("business", "主营业务", ("主营业务", "主要业务", "业务介绍"), expects_numeric=False),
    ComparisonTopic("management_discussion", "管理层讨论", ("管理层讨论", "董事会报告", "经营情况讨论", "讨论与分析"), expects_numeric=False),
)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def detect_topics(question: str, comparison_mode: str | None = None) -> list[ComparisonTopic]:
    lowered = question or ""
    topics: list[ComparisonTopic] = []
    if comparison_mode == "metric_change":
        for topic in TOPICS:
            if topic.expects_numeric:
                topics.append(topic)
        return topics[:3]
    for topic in TOPICS:
        if any(alias in lowered for alias in topic.aliases):
            topics.append(topic)
    if not topics:
        if comparison_mode == "risk_change":
            return [TOPICS[3]]
        if comparison_mode == "business_change":
            return [TOPICS[4]]
        if comparison_mode == "management_discussion_change":
            return [TOPICS[5]]
        return [TOPICS[0], TOPICS[1], TOPICS[2]]
    return topics


def topic_query(topic: ComparisonTopic, question: str, report_year: int | None, report_type: str | None) -> str:
    if topic.expects_numeric:
        exact_label = {
            "revenue": "营业收入",
            "net_profit_parent": "归属于上市公司股东的净利润",
            "operating_cash_flow": "经营活动产生的现金流量净额",
        }.get(topic.key, topic.label)
        return f"{report_year or ''}年主要会计数据中的{exact_label}是多少？"
    if topic.key == "risk":
        return f"{report_year or ''}年{topic.label}披露有哪些？"
    if topic.key == "business":
        return f"{report_year or ''}年{topic.label}是什么？"
    return f"{report_year or ''}年{topic.label}相关披露"


def _first_number(text: str) -> tuple[str | None, float | None]:
    match = re.search(r"(?<!\d)(-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?)(?!\d)", text)
    if not match:
        return None, None
    raw = match.group(1)
    try:
        return raw, float(raw.replace(",", ""))
    except ValueError:
        return raw, None


def _extract_unit(text: str) -> str | None:
    match = re.search(r"(亿元|万元|元|%|百分点)", text)
    return match.group(1) if match else None


def _page_value(chunk: dict[str, Any]) -> int | str:
    start = int(chunk.get("page_start") or 0)
    end = int(chunk.get("page_end") or start)
    return start if start == end else f"{start}-{end}"


def _find_chunk_for_topic(chunks: list[dict[str, Any]], topic: ComparisonTopic) -> dict[str, Any] | None:
    if not chunks:
        return None

    def score(chunk: dict[str, Any]) -> tuple[int, int, int]:
        text = chunk.get("text_excerpt") or ""
        page_start = int(chunk.get("page_start") or 0)
        alias_hit = 1 if any(alias in text for alias in topic.aliases) else 0
        section_boost = 0
        if any(marker in text for marker in ("主要会计数据", "主要财务指标", "分季度主要财务数据", "主要风险", "主营业务", "管理层讨论")):
            section_boost += 2
        if page_start and page_start <= 30:
            section_boost += 1
        numeric_boost = 0
        if topic.expects_numeric:
            for alias in topic.aliases:
                if re.search(rf"{re.escape(alias)}.{{0,80}}?(?:元|万元|亿元)", text):
                    numeric_boost += 3
                    break
                if re.search(rf"{re.escape(alias)}.{{0,80}}?(?:%|百分点)", text):
                    numeric_boost += 1
                    break
        return (alias_hit, numeric_boost + section_boost, -page_start)

    return sorted(chunks, key=score, reverse=True)[0]


def _extract_topic_evidence(chunk: dict[str, Any] | None, topic: ComparisonTopic, report_id: int, report_year: int | None, report_type: str | None) -> dict[str, Any]:
    if not chunk:
        return {
            "report_id": report_id,
            "report_year": report_year,
            "report_type": report_type,
            "value": None,
            "numeric_value": None,
            "unit": None,
            "period_basis": report_type or "unknown",
            "evidence_pages": [],
            "excerpt": "",
            "comparable": False,
            "warning": "insufficient_evidence",
        }
    text = _normalize_whitespace(chunk.get("text_excerpt") or "")
    alias_pos = min((text.find(alias) for alias in topic.aliases if text.find(alias) >= 0), default=-1)
    window = text[alias_pos : alias_pos + 120] if alias_pos >= 0 else text
    raw_value, numeric_value = _first_number(window)
    unit = _extract_unit(window) or _extract_unit(text)
    return {
        "report_id": report_id,
        "report_year": report_year,
        "report_type": report_type,
        "value": raw_value,
        "numeric_value": numeric_value,
        "unit": unit,
        "period_basis": "annual" if report_type == "annual" else "quarterly_cumulative",
        "evidence_pages": [_page_value(chunk)],
        "excerpt": text[:500],
        "comparable": bool(raw_value) if topic.expects_numeric else True,
        "warning": None if raw_value or not topic.expects_numeric else "insufficient_evidence",
    }


def build_comparison_evidence_matrix(
    *,
    selected_report_ids: list[int],
    per_report_results: list[dict[str, Any]],
    question: str,
    comparison_mode: str | None = None,
) -> dict[str, Any]:
    topics = detect_topics(question, comparison_mode)
    report_lookup = {int(item["report_id"]): item for item in per_report_results}
    matrix: list[dict[str, Any]] = []
    warnings: list[str] = []

    for topic in topics:
        topic_rows: list[dict[str, Any]] = []
        for report_id in selected_report_ids:
            result = report_lookup.get(int(report_id))
            if not result:
                topic_rows.append(
                    {
                        "report_id": report_id,
                        "report_year": None,
                        "report_type": None,
                        "value": None,
                        "numeric_value": None,
                        "unit": None,
                        "period_basis": "unknown",
                        "evidence_pages": [],
                        "excerpt": "",
                        "comparable": False,
                        "warning": "insufficient_evidence",
                    }
                )
                continue
            chunk = _find_chunk_for_topic(result.get("chunks") or [], topic)
            evidence = _extract_topic_evidence(chunk, topic, report_id, result.get("report_year"), result.get("report_type"))
            if evidence["warning"]:
                warnings.append(str(evidence["warning"]))
            topic_rows.append(evidence)
        matrix.append(
            {
                "topic": topic.label,
                "topic_key": topic.key,
                "reports": topic_rows,
                "comparable": all(row.get("comparable") for row in topic_rows if row.get("report_id") in selected_report_ids and row.get("value") is not None),
                "comparison_warnings": sorted(set(warnings)),
            }
        )

    return {
        "selected_report_ids": selected_report_ids,
        "topics": matrix,
        "comparison_warnings": sorted(set(warnings)),
    }


def infer_comparison_mode(question: str) -> str:
    lowered = question or ""
    if any(term in lowered for term in ("营业收入", "净利润", "现金流", "经营活动产生的现金流量净额")):
        return "metric_change"
    if any(term in lowered for term in ("风险", "风险因素")):
        return "risk_change"
    if any(term in lowered for term in ("主营业务", "业务")):
        return "business_change"
    if any(term in lowered for term in ("管理层讨论", "董事会报告", "经营情况讨论")):
        return "management_discussion_change"
    return "generic_comparison"
