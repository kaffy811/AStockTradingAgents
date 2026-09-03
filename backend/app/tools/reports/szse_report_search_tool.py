"""
app/tools/reports/szse_report_search_tool.py — 深交所（SZSE）定期报告搜索工具

SZSE 官方披露查询：https://www.szse.cn/
使用公开 JSON API 接口，低频访问，非爬虫。
仅适用于深交所股票：代码以 0、2、3 开头。
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.tools.reports.base import BaseReportSearchTool, _RATE_LIMIT_SECONDS, _TIMEOUT_SECONDS, _MAX_RETRIES

log = logging.getLogger(__name__)

# SZSE announcement search API
_SZSE_SEARCH_URL = "http://www.szse.cn/api/search/announcement"
_SZSE_PDF_BASE = "https://disc.szse.cn/download"

_USER_AGENT = (
    "Mozilla/5.0 (compatible; TradingAgentsResearch/1.0; "
    "Public financial data research)"
)

_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Referer": "https://www.szse.cn/",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}

# SZSE category codes for report types
_SZSE_CATEGORIES = {
    "annual": "category_ndbg_szsh",
    "semi":   "category_bndbg_szsh",
    "q1":     "category_yjdbg_szsh",
    "q3":     "category_yjdbg_szsh",
}

_SZSE_TYPE_KEYWORDS = {
    "annual": "年度报告",
    "semi":   "半年度报告",
    "q1":     "第一季度",
    "q3":     "第三季度",
}


def _period_from_type_year(report_type: str, report_year: int) -> str:
    period_map = {
        "annual": f"{report_year}1231",
        "semi":   f"{report_year}0630",
        "q1":     f"{report_year}0331",
        "q3":     f"{report_year}0930",
    }
    return period_map.get(report_type, f"{report_year}1231")


class SZSEReportSearchTool(BaseReportSearchTool):
    source_name = "szse"

    async def search(
        self,
        stock_code: str,
        company_name: str,
        report_type: str,
        report_year: int,
    ) -> list[dict]:
        """
        Search SZSE (Shenzhen Stock Exchange) for periodic reports.
        Only applicable for 深市 stocks (code starting with 0, 2, 3).
        """
        if not stock_code.startswith(("0", "2", "3")):
            log.debug("SZSE tool skipping non-SZSE stock: %s", stock_code)
            return []

        await asyncio.sleep(_RATE_LIMIT_SECONDS)

        period = _period_from_type_year(report_type, report_year)
        keyword = _SZSE_TYPE_KEYWORDS.get(report_type, "年度报告")

        payload = {
            "secCode": stock_code,
            "keyword": f"{report_year} {keyword}",
            "pageNum": 1,
            "pageSize": 10,
        }

        data: dict | list = {}
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    headers=_HEADERS,
                    timeout=_TIMEOUT_SECONDS,
                    follow_redirects=True,
                ) as client:
                    resp = await client.post(_SZSE_SEARCH_URL, json=payload)
                    resp.raise_for_status()
                    try:
                        data = resp.json()
                    except Exception:
                        log.warning("SZSE: non-JSON response for %s", stock_code)
                        return []
                break
            except httpx.HTTPStatusError as e:
                # HTTP 400 is common when SZSE rejects the query format;
                # don't retry and keep at DEBUG to reduce log noise.
                if e.response.status_code == 400:
                    log.debug("SZSE HTTP 400 (query rejected) [%s]: %s", stock_code, e)
                else:
                    log.warning("SZSE HTTP error [%s]: %s", stock_code, e)
                return []
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
                    continue
                log.warning("SZSE timeout/connect [%s]: %s", stock_code, e)
                return []
            except Exception as e:
                log.warning("SZSE unexpected error [%s]: %s", stock_code, e)
                return []

        # Parse SZSE response (structure varies by API version)
        items = []
        if isinstance(data, dict):
            items = (
                data.get("data") or
                data.get("result") or
                data.get("announcements") or
                data.get("list") or
                []
            )
        elif isinstance(data, list):
            items = data

        if not items:
            log.info("SZSE: no results for %s %s %d", stock_code, report_type, report_year)
            return []

        candidates = []
        for item in items[:10]:
            title = (
                item.get("ANNOUNCEMENT_TITLE") or
                item.get("title") or
                item.get("announcementTitle") or
                ""
            )
            if not title:
                continue

            # Try to find PDF URL in various response field names
            pdf_path = (
                item.get("ATTACHED_FILE_URL") or
                item.get("attachedFileUrl") or
                item.get("filePath") or
                item.get("pdfUrl") or
                ""
            )
            if pdf_path and not pdf_path.startswith("http"):
                pdf_url = _SZSE_PDF_BASE + "/" + pdf_path.lstrip("/")
            elif pdf_path:
                pdf_url = pdf_path
            else:
                continue  # Skip if no PDF found

            ann_date = (
                item.get("ANNOUNCEMENT_DATE") or
                item.get("announcementDate") or
                item.get("publishDate") or
                ""
            )
            if ann_date:
                ann_date = ann_date.replace("-", "")[:8]

            source_url = item.get("detailUrl") or pdf_url

            candidate = self._make_candidate(
                title=title,
                stock_code=stock_code,
                company_name=company_name,
                report_type=report_type,
                report_year=report_year,
                period=period,
                ann_date=ann_date,
                source_url=source_url,
                pdf_url=pdf_url,
            )
            candidates.append(candidate)

        candidates.sort(key=lambda c: c["confidence"], reverse=True)
        return candidates


szse_tool = SZSEReportSearchTool()
