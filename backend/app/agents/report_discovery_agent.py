"""
app/agents/report_discovery_agent.py — 定期报告自动发现 Agent（Phase 6D）

职责：
  - 接收 stock_code, company_name, report_type, report_year
  - 并发调用 CNINFO / SSE / SZSE 搜索工具
  - 合并候选、去重（by pdf_url）、按置信度排序
  - 返回候选列表（不直接入库，不下载 PDF）
  - 不编造结果；找不到时返回空列表 + reason

安全边界：
  - 不绕过验证码/登录
  - 只查询公开公告平台
  - 低频（每个来源 1.5s rate limit）
  - 不生成投资建议
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.tools.reports.cninfo_report_search_tool import cninfo_tool
from app.tools.reports.sse_report_search_tool import sse_tool
from app.tools.reports.szse_report_search_tool import szse_tool

log = logging.getLogger(__name__)

# Minimum confidence to include in results
_MIN_CONFIDENCE = 0.35
# High confidence threshold for auto-insert
HIGH_CONFIDENCE_THRESHOLD = 0.75


class ReportDiscoveryAgent:
    """
    定期报告发现 Agent。

    并发调用多个数据源，合并、去重、打分，返回候选报告列表。
    """

    async def discover(
        self,
        stock_code: str,
        company_name: str,
        report_type: str,
        report_year: int,
    ) -> dict[str, Any]:
        """
        Search for periodic reports across all available sources.

        Returns:
            {
              "candidates": list[dict],   # scored candidates
              "total_found": int,
              "sources_searched": list[str],
              "high_confidence": list[dict],  # confidence >= 0.75
              "errors": list[str],
              "partial": bool,
            }
        """
        log.info(
            "ReportDiscoveryAgent: searching %s %s %s %d",
            stock_code, company_name, report_type, report_year,
        )

        # Run all three tools concurrently
        tasks = {
            "cninfo": cninfo_tool.search(stock_code, company_name, report_type, report_year),
            "sse":    sse_tool.search(stock_code, company_name, report_type, report_year),
            "szse":   szse_tool.search(stock_code, company_name, report_type, report_year),
        }

        results = {}
        errors = []
        for source, coro in tasks.items():
            try:
                results[source] = await coro
            except Exception as e:
                log.warning("ReportDiscovery: %s failed: %s", source, e)
                errors.append(f"{source}: {e}")
                results[source] = []

        # Merge and deduplicate by pdf_url
        seen_urls: set[str] = set()
        all_candidates: list[dict] = []

        for source, candidates in results.items():
            for c in candidates:
                pdf_url = c.get("pdf_url") or ""
                if pdf_url and pdf_url in seen_urls:
                    continue
                if pdf_url:
                    seen_urls.add(pdf_url)
                if c.get("confidence", 0) >= _MIN_CONFIDENCE:
                    all_candidates.append(c)

        # Sort by confidence desc
        all_candidates.sort(key=lambda c: c.get("confidence", 0), reverse=True)

        high_confidence = [c for c in all_candidates if c.get("confidence", 0) >= HIGH_CONFIDENCE_THRESHOLD]
        sources_searched = [s for s, r in results.items() if r is not None]

        return {
            "candidates":       all_candidates,
            "total_found":      len(all_candidates),
            "sources_searched": sources_searched,
            "high_confidence":  high_confidence,
            "errors":           errors,
            "partial":          len(all_candidates) == 0,
        }

    async def discover_latest(
        self,
        stock_code: str,
        company_name: str,
        report_year: int,
    ) -> dict[str, Any]:
        """
        Discover the most recent report of each type for the given year.
        Runs all 4 report types concurrently.
        """
        report_types = ["annual", "semi", "q1", "q3"]
        tasks = [
            self.discover(stock_code, company_name, rt, report_year)
            for rt in report_types
        ]

        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        all_candidates = []
        all_errors = []
        for rt, result in zip(report_types, all_results):
            if isinstance(result, Exception):
                all_errors.append(f"{rt}: {result}")
                continue
            # Take only the top candidate per type
            hc = result.get("high_confidence") or []
            if hc:
                all_candidates.append(hc[0])
            all_errors.extend(result.get("errors") or [])

        return {
            "candidates":  all_candidates,
            "total_found": len(all_candidates),
            "errors":      all_errors,
            "partial":     len(all_candidates) == 0,
        }


report_discovery_agent = ReportDiscoveryAgent()
