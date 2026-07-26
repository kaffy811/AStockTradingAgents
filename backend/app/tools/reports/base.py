"""
app/tools/reports/base.py — Report discovery tool base class + shared schemas

统一 Candidate 格式：
{
  "title": str,
  "stock_code": str,           # e.g. "600519"
  "company_name": str,
  "report_type": str,          # annual/semi/q1/q3
  "report_year": int,
  "period": str,               # YYYYMMDD e.g. "20241231"
  "ann_date": str,             # YYYYMMDD e.g. "20250430"
  "source": str,               # cninfo/sse/szse
  "source_url": str,           # announcement page URL
  "pdf_url": str,              # direct PDF URL
  "confidence": float,         # 0.0-1.0
  "match_reasons": list[str],
  "warnings": list[str],
}
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

# Request rate limit — 1 request per tool per second (low-frequency, not a crawler)
_RATE_LIMIT_SECONDS = 1.5
# HTTP timeout for discovery requests
_TIMEOUT_SECONDS = 10
# Max retries on network error (not on 4xx/5xx)
_MAX_RETRIES = 2

# Report type keywords for confidence scoring
_ANNUAL_KEYWORDS = ["年度报告", "年报", "annual report"]
_SEMI_KEYWORDS = ["半年度报告", "半年报", "interim", "semi-annual"]
_Q1_KEYWORDS = ["第一季度", "一季报", "季度报告（第一季度）", "q1"]
_Q3_KEYWORDS = ["第三季度", "三季报", "季度报告（第三季度）", "q3"]
_SKIP_KEYWORDS = ["摘要", "审计报告", "社会责任", "问询函", "关注函", "督导", "异议", "独立", "监事会", "董事会决议"]

CANDIDATE_SCHEMA_KEYS = [
    "title", "stock_code", "company_name", "report_type", "report_year",
    "period", "ann_date", "source", "source_url", "pdf_url",
    "confidence", "match_reasons", "warnings",
]


def score_candidate(
    title: str,
    stock_code: str,
    company_name: str,
    report_type: str,
    report_year: int,
    ann_date_str: str,
    source: str,
) -> tuple[float, list[str], list[str]]:
    """
    Score a report candidate and return (confidence, match_reasons, warnings).

    confidence:
      - Base: 0.5
      - stock_code in title: +0.15
      - company_name in title: +0.10
      - report_type keyword matches: +0.15
      - year matches: +0.10
      - is summary ("摘要"): -0.25 + warning
      - skip keywords present: -0.50 (disqualify)
    """
    title_lower = title.lower()
    reasons = []
    warnings = []
    score = 0.50

    # Skip non-periodic reports outright
    for kw in _SKIP_KEYWORDS:
        if kw in title:
            if kw == "摘要":
                score -= 0.25
                warnings.append(f"标题含「摘要」，可能为报告摘要版（非完整版），置信度降低")
            else:
                score -= 0.50
                reasons.append(f"跳过：标题含「{kw}」（非定期报告）")
                return max(0.0, score), reasons, warnings

    # Stock code in title
    if stock_code in title:
        score += 0.15
        reasons.append(f"stock_code {stock_code} matched in title")

    # Company name in title (partial)
    if company_name and len(company_name) >= 2:
        short_name = company_name[:4]
        if short_name in title or company_name in title:
            score += 0.10
            reasons.append(f"company_name {company_name!r} matched in title")

    # Report type keyword match
    type_keywords = {
        "annual": _ANNUAL_KEYWORDS,
        "semi":   _SEMI_KEYWORDS,
        "q1":     _Q1_KEYWORDS,
        "q3":     _Q3_KEYWORDS,
    }.get(report_type, [])

    for kw in type_keywords:
        if kw in title_lower or kw in title:
            score += 0.15
            reasons.append(f"report_type keyword {kw!r} matched")
            break

    # Year match
    year_str = str(report_year)
    if year_str in title:
        score += 0.10
        reasons.append(f"report_year {report_year} matched in title")

    if not reasons:
        warnings.append("标题无法确认与目标股票/报告类型匹配，请人工确认")

    return min(1.0, max(0.0, round(score, 3))), reasons, warnings


class BaseReportSearchTool:
    """Base class for report search tools. Subclass and implement search()."""
    source_name: str = "unknown"

    async def search(
        self,
        stock_code: str,
        company_name: str,
        report_type: str,
        report_year: int,
    ) -> list[dict]:
        """Return list of candidates (partial/empty on error, never raises)."""
        raise NotImplementedError

    def _make_candidate(
        self,
        title: str,
        stock_code: str,
        company_name: str,
        report_type: str,
        report_year: int,
        period: str,
        ann_date: str,
        source_url: str,
        pdf_url: str,
    ) -> dict:
        confidence, reasons, warnings = score_candidate(
            title=title,
            stock_code=stock_code,
            company_name=company_name,
            report_type=report_type,
            report_year=report_year,
            ann_date_str=ann_date,
            source=self.source_name,
        )
        return {
            "title":         title,
            "stock_code":    stock_code,
            "company_name":  company_name,
            "report_type":   report_type,
            "report_year":   report_year,
            "period":        period,
            "ann_date":      ann_date,
            "source":        self.source_name,
            "source_url":    source_url,
            "pdf_url":       pdf_url,
            "confidence":    confidence,
            "match_reasons": reasons,
            "warnings":      warnings,
        }
