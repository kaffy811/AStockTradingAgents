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

import httpx

from app.tools.reports.base import BaseReportSearchTool, _RATE_LIMIT_SECONDS, _TIMEOUT_SECONDS, _MAX_RETRIES

log = logging.getLogger(__name__)

# CNINFO announcement query API (public, no auth required)
_CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
# CNINFO static PDF base URL
_CNINFO_PDF_BASE = "http://static.cninfo.com.cn/"

# CNINFO category codes for different report types
_CNINFO_CATEGORIES = {
    "annual": "category_ndbg_szsh",     # 年度报告
    "semi":   "category_bndbg_szsh",    # 半年度报告
    "q1":     "category_yjdbg_szsh",    # 季度报告（含一、三季度）
    "q3":     "category_yjdbg_szsh",    # 季度报告（含一、三季度）
}

_USER_AGENT = (
    "Mozilla/5.0 (compatible; TradingAgentsResearch/1.0; "
    "Public financial data research; +https://github.com/)"
)

_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Referer": "http://www.cninfo.com.cn/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
}


def _exchange_column(stock_code: str) -> str:
    """Determine CNINFO column (exchange) from stock code."""
    if stock_code.startswith(("6", "5")):
        return "sse"
    elif stock_code.startswith(("0", "3", "2")):
        return "szse"
    elif stock_code.startswith(("4", "8", "9")):
        return "bj"
    return "sse"


def _period_from_type_year(report_type: str, report_year: int) -> str:
    """Derive period end date string from report_type + year."""
    period_map = {
        "annual": f"{report_year}1231",
        "semi":   f"{report_year}0630",
        "q1":     f"{report_year}0331",
        "q3":     f"{report_year}0930",
    }
    return period_map.get(report_type, f"{report_year}1231")


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

        category = _CNINFO_CATEGORIES.get(report_type)
        if not category:
            log.warning("CNINFO: unsupported report_type %s", report_type)
            return []

        column = _exchange_column(stock_code)
        period = _period_from_type_year(report_type, report_year)

        # Build search date range: 1 year after report period
        start_year = report_year
        end_year = report_year + 1

        form_data = {
            "stock":     stock_code,
            "tabName":   "fulltext",
            "pageNum":   "1",
            "pageSize":  "10",
            "column":    column,
            "category":  category,
            "seDate":    f"{start_year}-01-01~{end_year + 1}-12-31",
            "startDate": "",
            "endDate":   "",
            "isHLtitle": "true",
        }

        data: Any = {}
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    headers=_HEADERS,
                    timeout=_TIMEOUT_SECONDS,
                    follow_redirects=True,
                ) as client:
                    resp = await client.post(_CNINFO_QUERY_URL, data=form_data)
                    resp.raise_for_status()
                    data = resp.json()
                break
            except httpx.HTTPStatusError as e:
                log.warning("CNINFO HTTP error [%s/%d/%s]: %s", stock_code, report_year, report_type, e)
                return []
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
                    continue
                log.warning("CNINFO timeout/connect [%s]: %s", stock_code, e)
                return []
            except Exception as e:
                log.warning("CNINFO unexpected error [%s]: %s", stock_code, e)
                return []

        announcements = data.get("announcements") or []
        if not announcements:
            log.info("CNINFO: no announcements found for %s/%s/%d", stock_code, report_type, report_year)
            return []

        candidates = []
        for ann in announcements:
            title = ann.get("announcementTitle") or ""
            adjunct_url = ann.get("adjunctUrl") or ""
            if not adjunct_url or ann.get("adjunctType", "").upper() != "PDF":
                continue

            pdf_url = _CNINFO_PDF_BASE + adjunct_url.lstrip("/")
            source_url = (
                f"http://www.cninfo.com.cn/new/disclosure/detail"
                f"?announcementId={ann.get('announcementId', '')}&orgId={ann.get('orgId', '')}"
            )

            # Parse ann_date from timestamp (ms)
            ann_time_ms = ann.get("announcementTime") or 0
            if ann_time_ms:
                from datetime import datetime, timezone
                ann_dt = datetime.fromtimestamp(ann_time_ms / 1000, tz=timezone.utc)
                ann_date_str = ann_dt.strftime("%Y%m%d")
            else:
                ann_date_str = ""

            candidate = self._make_candidate(
                title=title,
                stock_code=stock_code,
                company_name=company_name,
                report_type=report_type,
                report_year=report_year,
                period=period,
                ann_date=ann_date_str,
                source_url=source_url,
                pdf_url=pdf_url,
            )
            candidates.append(candidate)

        # Sort by confidence desc
        candidates.sort(key=lambda c: c["confidence"], reverse=True)
        return candidates


cninfo_tool = CninfoReportSearchTool()
