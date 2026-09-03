"""
app/tools/reports/cninfo_report_search_tool.py — 巨潮资讯定期报告搜索工具

CNINFO (巨潮资讯) 是中国上市公司信息披露官方平台，支持所有 A 股公告查询。
不需要登录，不需要 API Key，使用公开 JSON API。

Rate limit: 1.5 秒/次请求，非爬虫用途。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.datasource.cninfo_provider import (
    categories_for_report_type,
    extract_report_metadata,
    normalize_report_type,
    period_from_type_year,
    search_announcements_with_diagnostics,
    validate_pdf_url,
)
from app.tools.reports.base import BaseReportSearchTool, _RATE_LIMIT_SECONDS

log = logging.getLogger(__name__)

class CninfoReportSearchTool(BaseReportSearchTool):
    source_name = "cninfo"

    async def search(
        self,
        stock_code: str,
        company_name: str,
        report_type: str,
        report_year: int,
    ) -> list[dict]:
        """
        Search CNINFO for a specific report type and year.
        Returns list of candidates (may be empty). Never raises.
        """
        await asyncio.sleep(_RATE_LIMIT_SECONDS)

        canonical_type = normalize_report_type(report_type)
        categories = categories_for_report_type(canonical_type)
        if not categories:
            log.warning("CNINFO: unsupported report_type %s", report_type)
            return []

        period = period_from_type_year(canonical_type, report_year)

        # Build search date range: 1 year after report period
        start_year = report_year
        end_year = report_year + 1

        announcements: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        for category in categories:
            result = await search_announcements_with_diagnostics(
                stock_code,
                start_date=f"{start_year}-01-01",
                end_date=f"{end_year + 1}-12-31",
                category=category,
                page_size=10,
            )
            diagnostics.append(result.get("diagnostics") or {})
            announcements.extend(result.get("announcements") or [])
        if not announcements:
            log.info(
                "CNINFO: no announcements found for %s/%s/%d diagnostics=%s",
                stock_code,
                report_type,
                report_year,
                diagnostics,
            )
            return []

        candidates = []
        for ann in announcements:
            meta = extract_report_metadata(ann, stock_code, report_year, canonical_type)
            title = meta.get("title") or ""
            pdf_url = meta.get("pdf_url") or ""
            valid_url, _reason = validate_pdf_url(pdf_url)
            if not valid_url:
                continue
            ann_date_str = (meta.get("announcement_date") or "").replace("-", "")

            candidate = self._make_candidate(
                title=title,
                stock_code=stock_code,
                company_name=company_name,
                report_type=report_type,
                report_year=int(meta.get("report_year") or report_year),
                period=period,
                ann_date=ann_date_str,
                source_url=meta.get("source_url") or "",
                pdf_url=pdf_url,
            )
            candidate["provider_status"] = "success"
            candidate["canonical_report_type"] = meta.get("report_type")
            candidates.append(candidate)

        # Sort by confidence desc
        candidates.sort(key=lambda c: c["confidence"], reverse=True)
        return candidates


cninfo_tool = CninfoReportSearchTool()
