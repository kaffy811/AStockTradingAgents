"""
app/tools/reports/sse_report_search_tool.py — 上交所（SSE）定期报告搜索工具

SSE 官方披露查询：https://www.sse.com.cn/
使用公开 JSON API 接口，低频访问，非爬虫。
仅适用于上交所（沪市）股票：代码以 6 开头。
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.tools.reports.base import BaseReportSearchTool, _RATE_LIMIT_SECONDS, _TIMEOUT_SECONDS, _MAX_RETRIES

log = logging.getLogger(__name__)

# Phase 6N-8B: Per-key debug dedup (same symbol/year/type only logged once per process run)
_sse_logged: set[str] = set()

def _sse_log_once(stock_code: str, report_year: int, report_type: str, msg: str) -> None:
    key = f"{stock_code}:{report_year}:{report_type}"
    if key not in _sse_logged:
        _sse_logged.add(key)
        log.debug("SSE [%s]: %s", key, msg)

# SSE public announcement search API
_SSE_SEARCH_URL = "https://query.sse.com.cn/search/getSearchList.do"
_SSE_PDF_BASE = "https://www.sse.com.cn"

_USER_AGENT = (
    "Mozilla/5.0 (compatible; TradingAgentsResearch/1.0; "
    "Public financial data research)"
)

_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Referer": "https://www.sse.com.cn/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# SSE report type search keywords
_SSE_SEARCH_TERMS = {
    "annual": "年度报告",
    "semi":   "半年度报告",
    "q1":     "第一季度报告",
    "q3":     "第三季度报告",
}


def _period_from_type_year(report_type: str, report_year: int) -> str:
    period_map = {
        "annual": f"{report_year}1231",
        "semi":   f"{report_year}0630",
        "q1":     f"{report_year}0331",
        "q3":     f"{report_year}0930",
    }
    return period_map.get(report_type, f"{report_year}1231")


class SSEReportSearchTool(BaseReportSearchTool):
    source_name = "sse"

    async def search(
        self,
        stock_code: str,
        company_name: str,
        report_type: str,
        report_year: int,
    ) -> list[dict]:
        """
        Search SSE (Shanghai Stock Exchange) for periodic reports.
        Only applicable for 沪市 stocks (code starting with 6).
        """
        # SSE only covers Shanghai-listed stocks
        if not stock_code.startswith(("6", "5")):
            log.debug("SSE tool skipping non-SSE stock: %s", stock_code)
            return []

        await asyncio.sleep(_RATE_LIMIT_SECONDS)

        search_term = _SSE_SEARCH_TERMS.get(report_type, "年度报告")
        query_str = f"{stock_code} {report_year} {search_term}"
        period = _period_from_type_year(report_type, report_year)

        params = {
            "inpDate": "",
            "keyWord": query_str,
            "page": "1",
            "perpage": "10",
            "channelCode": "",
        }

        data: dict | list = {}
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    headers=_HEADERS,
                    timeout=_TIMEOUT_SECONDS,
                    follow_redirects=True,
                ) as client:
                    resp = await client.get(_SSE_SEARCH_URL, params=params)
                    # Phase 6N-8B: SSE 404 → no retry, return empty immediately
                    if resp.status_code == 404:
                        log.debug("SSE 404 for %s/%d — no retry", stock_code, report_year)
                        return []
                    resp.raise_for_status()
                    try:
                        data = resp.json()
                    except Exception:
                        log.warning("SSE: non-JSON response for %s", stock_code)
                        return []
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Phase 6N-8B: SSE 404 is expected for non-existent reports — no retry
                    log.debug("SSE HTTP 404 [%s/%d] — skip", stock_code, report_year)
                else:
                    log.warning("SSE HTTP error [%s]: %s", stock_code, e)
                return []
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
                    continue
                log.warning("SSE timeout/connect [%s]: %s", stock_code, e)
                return []
            except Exception as e:
                log.warning("SSE unexpected error [%s]: %s", stock_code, e)
                return []

        # SSE response structure varies; try to parse common formats
        items = []
        if isinstance(data, dict):
            items = (
                data.get("data") or
                data.get("result") or
                data.get("list") or
                []
            )
        elif isinstance(data, list):
            items = data

        if not items:
            log.info("SSE: no results for %s %s %d", stock_code, report_type, report_year)
            return []

        candidates = []
        for item in items[:10]:
            title = item.get("title") or item.get("announcementTitle") or item.get("TITLE") or ""
            if not title:
                continue

            # Try to find PDF URL
            pdf_url = item.get("filePath") or item.get("pdfUrl") or item.get("FILE_PATH") or ""
            if pdf_url and not pdf_url.startswith("http"):
                pdf_url = _SSE_PDF_BASE + pdf_url

            source_url = item.get("url") or item.get("detailUrl") or pdf_url or ""
            if source_url and not source_url.startswith("http"):
                source_url = _SSE_PDF_BASE + source_url

            ann_date = item.get("publishDate") or item.get("PUB_DATE") or ""
            if ann_date:
                ann_date = ann_date.replace("-", "")[:8]

            if not pdf_url:
                continue  # Skip if no PDF URL found

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


sse_tool = SSEReportSearchTool()
