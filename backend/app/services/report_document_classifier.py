"""Canonical report-document classification for CNINFO-style announcements."""
from __future__ import annotations

import re
from dataclasses import dataclass


CLASSIFICATION_VERSION = "report_kind_v1"

KIND_ANNUAL_FULL = "annual_full"
KIND_ANNUAL_SUMMARY = "annual_summary"
KIND_SEMI_ANNUAL_FULL = "semi_annual_full"
KIND_QUARTERLY = "quarterly"
KIND_CORRECTION = "correction"
KIND_INQUIRY_REPLY = "inquiry_reply"
KIND_RISK_WARNING = "risk_warning"
KIND_DELAYED_DISCLOSURE = "delayed_disclosure"
KIND_AUDIT_REPORT = "audit_report"
KIND_BOARD_RESOLUTION = "board_resolution"
KIND_OTHER = "other_announcement"

_CHINESE_DIGITS = {
    "〇": "0",
    "零": "0",
    "一": "1",
    "二": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
}

_EXCLUSION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (KIND_INQUIRY_REPLY, ("问询函", "问询", "回复", "反馈意见")),
    (KIND_RISK_WARNING, ("风险提示", "退市风险", "其他风险警示", "被警示")),
    (KIND_DELAYED_DISCLOSURE, ("延期", "延迟披露", "推迟披露", "延期披露")),
    (KIND_CORRECTION, ("更正", "修订", "补充", "取消")),
    (KIND_AUDIT_REPORT, ("审计报告",)),
    (KIND_BOARD_RESOLUTION, ("董事会决议", "监事会决议", "股东大会决议")),
    (KIND_OTHER, ("披露提示性公告", "提示性公告", "英文版")),
)


@dataclass(frozen=True)
class ReportDocumentClassification:
    report_document_kind: str
    classification_version: str
    classification_reason: str
    report_year: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "report_document_kind": self.report_document_kind,
            "classification_version": self.classification_version,
            "classification_reason": self.classification_reason,
            "classified_report_year": self.report_year,
        }


def _normalize_title(title: str | None) -> str:
    return re.sub(r"\s+", "", str(title or ""))


def _chinese_year_to_int(text: str) -> int | None:
    digits = "".join(_CHINESE_DIGITS.get(ch, "") for ch in text)
    if len(digits) == 4 and digits.startswith("20"):
        return int(digits)
    return None


def extract_report_year_from_title(title: str | None) -> int | None:
    """Prefer the year directly attached to the report phrase, not any first year."""
    normalized = _normalize_title(title)
    patterns = (
        r"(20\d{2})年年度报告",
        r"(20\d{2})年度报告",
        r"(20\d{2})年半年度报告",
        r"(20\d{2})年(?:第一|一|第三|三)季度报告",
        r"(20\d{2})年报",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return int(match.group(1))
    match = re.search(r"([二〇零一二三四五六七八九]{4})年年度报告", normalized)
    if match:
        return _chinese_year_to_int(match.group(1))
    return None


def classify_report_document(
    title: str | None,
    *,
    report_type: str | None = None,
    category: str | None = None,
    first_page_text: str | None = None,
) -> ReportDocumentClassification:
    title_text = _normalize_title(title)
    haystack = _normalize_title(" ".join(str(v or "") for v in (category, title, first_page_text)))
    year = extract_report_year_from_title(title)

    if "年度报告摘要" in haystack or ("年度报告" in haystack and "摘要" in haystack):
        return ReportDocumentClassification(KIND_ANNUAL_SUMMARY, CLASSIFICATION_VERSION, "title_contains_annual_summary", year)

    for kind, tokens in _EXCLUSION_RULES:
        hit = next((token for token in tokens if token in haystack), "")
        if hit:
            return ReportDocumentClassification(kind, CLASSIFICATION_VERSION, f"title_excludes_full_report:{hit}", year)

    if "半年度报告" in haystack or str(report_type or "").lower() in {"semi", "semi_annual"}:
        if "摘要" in haystack:
            return ReportDocumentClassification(KIND_OTHER, CLASSIFICATION_VERSION, "semi_annual_summary_or_notice", year)
        return ReportDocumentClassification(KIND_SEMI_ANNUAL_FULL, CLASSIFICATION_VERSION, "title_contains_semi_annual_report", year)

    if any(token in haystack for token in ("季度报告", "一季报", "三季报")) or str(report_type or "").lower() in {"q1", "q3", "quarterly"}:
        return ReportDocumentClassification(KIND_QUARTERLY, CLASSIFICATION_VERSION, "title_contains_quarterly_report", year)

    annual_title = (
        "年度报告" in title_text
        or bool(re.search(r"(20\d{2})年报$", title_text))
        or bool(re.search(r"[二〇零一二三四五六七八九]{4}年年度报告", title_text))
    )
    if annual_title or str(report_type or "").lower() == "annual":
        if "年度报告" in title_text and year:
            return ReportDocumentClassification(KIND_ANNUAL_FULL, CLASSIFICATION_VERSION, "title_contains_full_annual_report", year)
        if annual_title:
            return ReportDocumentClassification(KIND_ANNUAL_FULL, CLASSIFICATION_VERSION, "title_contains_annual_report", year)
        if str(report_type or "").lower() == "annual":
            return ReportDocumentClassification(KIND_ANNUAL_FULL, CLASSIFICATION_VERSION, "metadata_report_type_annual_no_exclusion", year)

    return ReportDocumentClassification(KIND_OTHER, CLASSIFICATION_VERSION, "no_full_report_signal", year)


def is_annual_full_report(title: str | None, *, report_type: str | None = None, category: str | None = None) -> bool:
    return classify_report_document(title, report_type=report_type, category=category).report_document_kind == KIND_ANNUAL_FULL
