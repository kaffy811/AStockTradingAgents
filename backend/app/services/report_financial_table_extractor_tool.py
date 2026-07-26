"""Deterministic financial table extraction for indexed official reports.

The tool extracts common annual-report metrics from parsed report text/chunks.
It is intentionally rule-based: LLMs may map column labels elsewhere, but this
tool never invents values and always returns source provenance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "revenue": ("营业收入", "营业总收入"),
    "operating_profit": ("营业利润",),
    "total_profit": ("利润总额",),
    "parent_net_profit": ("归属于上市公司股东的净利润", "归母净利润"),
    "deducted_parent_net_profit": ("扣除非经常性损益后的归属于上市公司股东的净利润", "扣非归母净利润"),
    "operating_cashflow": ("经营活动产生的现金流量净额", "经营活动现金流量净额"),
    "total_assets": ("总资产", "资产总计"),
    "parent_equity": ("归属于上市公司股东的净资产", "归属于母公司股东权益合计"),
    "eps": ("基本每股收益", "基本每股收益（元/股）"),
    "roe": ("加权平均净资产收益率", "净资产收益率"),
}

_SOURCE_TABLE_KEYWORDS = (
    "主要会计数据和财务指标",
    "合并利润表",
    "合并资产负债表",
    "合并现金流量表",
    "非经常性损益",
    "分季度主要财务数据",
)

_NUMBER_RE = r"([-+]?\d[\d,，]*(?:\.\d+)?)"
_UNIT_RE = r"(亿元|万元|元|%|％|元/股)?"


def _clean_number(value: str) -> float | None:
    try:
        return float(value.replace(",", "").replace("，", "").strip())
    except (TypeError, ValueError):
        return None


def _unit_scale(unit: str | None) -> float:
    if unit == "亿元":
        return 1e8
    if unit == "万元":
        return 1e4
    return 1.0


def _period_from_text(text: str, fallback_year: int | None = None) -> str:
    match = re.search(r"(20\d{2})\s*年\s*(?:12\s*月\s*31\s*日|年度|年报)", text)
    if match:
        return f"{match.group(1)}-12-31"
    if fallback_year:
        return f"{int(fallback_year)}-12-31"
    return ""


@dataclass(frozen=True)
class ExtractedFinancialField:
    field: str
    label: str
    report_id: int | str
    source_document_id: int | str | None
    source_chunk_id: int | str | None
    page: int | None
    table_name: str
    raw_text: str
    raw_value: str
    normalized_value: float
    unit: str
    period_end: str
    previous_period_value: float | None
    yoy: float | None
    confidence: float
    extraction_method: str = "regex_table_text"

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "label": self.label,
            "report_id": self.report_id,
            "source_document_id": self.source_document_id,
            "source_chunk_id": self.source_chunk_id,
            "page": self.page,
            "table_name": self.table_name,
            "raw_text": self.raw_text,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "unit": self.unit,
            "period_end": self.period_end,
            "previous_period_value": self.previous_period_value,
            "yoy": self.yoy,
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
        }


class ReportFinancialTableExtractorTool:
    """Extract structured metrics from parsed official report chunks."""

    cache_version = "v1"

    def extract_from_chunks(
        self,
        *,
        report_id: int | str,
        chunks: list[dict[str, Any]],
        report_year: int | None = None,
        source_document_id: int | str | None = None,
    ) -> dict[str, Any]:
        fields: dict[str, dict[str, Any]] = {}
        for chunk in chunks:
            text = str(chunk.get("content") or chunk.get("text") or "")
            section = str(chunk.get("section_title") or "")
            if not text.strip():
                continue
            extracted = self.extract_from_text(
                text=text,
                report_id=report_id,
                report_year=report_year,
                source_document_id=source_document_id or chunk.get("rag_document_id"),
                source_chunk_id=chunk.get("chunk_id") or chunk.get("id"),
                page=chunk.get("page_start") or chunk.get("page"),
                table_name=self._table_name(section, text),
            )
            for item in extracted:
                current = fields.get(item.field)
                if current is None or item.confidence > float(current.get("confidence") or 0):
                    fields[item.field] = item.to_dict()
        return {
            "report_id": report_id,
            "source_document_id": source_document_id,
            "fields": fields,
            "field_count": len(fields),
            "extraction_method": "regex_table_text",
            "cache_key": f"report_financial_fields:{report_id}:{self.cache_version}",
        }

    def extract_from_text(
        self,
        *,
        text: str,
        report_id: int | str,
        report_year: int | None = None,
        source_document_id: int | str | None = None,
        source_chunk_id: int | str | None = None,
        page: int | None = None,
        table_name: str | None = None,
    ) -> list[ExtractedFinancialField]:
        period_end = _period_from_text(text, report_year)
        table = table_name or self._table_name("", text)
        results: list[ExtractedFinancialField] = []
        for field, labels in _FIELD_LABELS.items():
            for label in labels:
                pattern = re.compile(
                    rf"{re.escape(label)}[^\n\r\d-]{{0,30}}{_NUMBER_RE}\s*{_UNIT_RE}"
                    rf"(?:[^\n\r\d-]{{0,30}}{_NUMBER_RE}\s*{_UNIT_RE})?"
                    rf"(?:[^\n\r%+-]{{0,30}}([-+]?\d+(?:\.\d+)?)\s*[%％])?",
                    re.IGNORECASE,
                )
                match = pattern.search(text)
                if not match:
                    continue
                raw_value = match.group(1)
                unit = match.group(2) or ("%" if field == "roe" else "元")
                raw_number = _clean_number(raw_value)
                if raw_number is None:
                    continue
                normalized = raw_number if unit in {"%", "％", "元/股"} else raw_number * _unit_scale(unit)
                previous_value = None
                if match.group(3):
                    prev_num = _clean_number(match.group(3))
                    prev_unit = match.group(4) or unit
                    previous_value = None if prev_num is None else (
                        prev_num if prev_unit in {"%", "％", "元/股"} else prev_num * _unit_scale(prev_unit)
                    )
                yoy = _clean_number(match.group(5)) if match.group(5) else None
                start, end = match.span()
                raw_text = text[max(0, start - 80): min(len(text), end + 120)].strip()
                results.append(ExtractedFinancialField(
                    field=field,
                    label=label,
                    report_id=report_id,
                    source_document_id=source_document_id,
                    source_chunk_id=source_chunk_id,
                    page=page,
                    table_name=table,
                    raw_text=re.sub(r"\s+", " ", raw_text)[:500],
                    raw_value=raw_value,
                    normalized_value=normalized,
                    unit="%" if unit == "％" else unit,
                    period_end=period_end,
                    previous_period_value=previous_value,
                    yoy=yoy,
                    confidence=0.9 if table in _SOURCE_TABLE_KEYWORDS else 0.75,
                ))
                break
        return results

    def _table_name(self, section_title: str, text: str) -> str:
        haystack = f"{section_title}\n{text}"
        for keyword in _SOURCE_TABLE_KEYWORDS:
            if keyword in haystack:
                return keyword
        return section_title or "report_text"


report_financial_table_extractor_tool = ReportFinancialTableExtractorTool()

