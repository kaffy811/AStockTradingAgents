"""
app/services/cninfo_annual_report_agent.py — CNINFO 年报发现 Agent（Phase 6T-A）

基于 CNINFO 公告查询接口，发现 A 股历年年报 PDF URL。

重要原则：
1. 不直接枚举 static.cninfo.com.cn/finalpage/ 路径
2. 不暴力猜 PDF ID
3. 通过 CNINFO 公告查询接口获取合法公告记录
4. 只保存白名单域名的 PDF URL
5. 支持多年份并发（含 rate limit）
6. 支持缓存（Redis + 内存）
7. 失败时结构化输出，不抛异常

使用方式：
    agent = CninfoAnnualReportAgent()
    result = await agent.discover(
        symbol="601686",
        start_year=2015,
        end_year=2025,
        force_refresh=False,
    )
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date
from typing import Any

from app.datasource.cninfo_provider import discover_annual_reports, validate_pdf_url
from app.services.cninfo_org_resolver import ORG_ID_NOT_FOUND, resolve_org_id

log = logging.getLogger(__name__)

# 默认发现最近 10 年
_DEFAULT_YEARS_BACK = 10
# 内存缓存
_MEMORY_CACHE: dict[str, tuple[list[dict], float]] = {}
_CACHE_TTL = 30 * 24 * 3600       # 30 days for success
_FAIL_TTL = 1 * 24 * 3600         # 1 day for failed/empty


class CninfoAnnualReportAgent:
    """
    CNINFO 年报发现 Agent。

    职责：
    - 解析 orgId
    - 调用 CNINFO 公告查询接口发现年报
    - 过滤、去重、校验 PDF URL
    - 缓存结果
    - 结构化错误输出
    """

    def _cache_key(self, symbol: str, start_year: int, end_year: int) -> str:
        return f"cninfo_reports:{symbol}:{start_year}:{end_year}"

    def _get_cache(self, key: str) -> list[dict] | None:
        entry = _MEMORY_CACHE.get(key)
        if not entry:
            return None
        items, cached_at = entry
        ttl = _CACHE_TTL if items else _FAIL_TTL
        if time.monotonic() - cached_at > ttl:
            return None
        return items

    def _set_cache(self, key: str, items: list[dict]) -> None:
        _MEMORY_CACHE[key] = (items, time.monotonic())

    async def discover(
        self,
        symbol: str,
        *,
        start_year: int | None = None,
        end_year: int | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """
        发现指定股票的历年年报 PDF URL。

        Parameters:
            symbol:       6位股票代码（如 "601686"）
            start_year:   起始年份（默认 end_year - 10）
            end_year:     结束年份（默认当前年份 - 1）
            force_refresh: 忽略缓存，强制重新查询

        Returns:
            {
              "symbol": str,
              "start_year": int,
              "end_year": int,
              "org_id": str,
              "org_id_source": str,
              "reports": list[dict],      # 已发现的年报记录
              "total_found": int,
              "errors": list[str],
              "from_cache": bool,
              "discovery_method": "cninfo_announcement_query"
            }
        """
        current_year = date.today().year
        if end_year is None:
            end_year = current_year - 1
        if start_year is None:
            start_year = max(2000, end_year - _DEFAULT_YEARS_BACK)
        end_year = min(end_year, current_year)
        start_year = max(2000, start_year)

        cache_key = self._cache_key(symbol, start_year, end_year)
        if not force_refresh:
            cached = self._get_cache(cache_key)
            if cached is not None:
                return {
                    "symbol": symbol,
                    "start_year": start_year,
                    "end_year": end_year,
                    "org_id": "cached",
                    "org_id_source": "cache",
                    "reports": cached,
                    "total_found": len(cached),
                    "errors": [],
                    "from_cache": True,
                    "discovery_method": "cninfo_announcement_query",
                }

        errors: list[str] = []
        org_id = ORG_ID_NOT_FOUND
        org_id_source = "not_found"

        # 1. 解析 orgId
        try:
            org_id = await asyncio.wait_for(resolve_org_id(symbol), timeout=8.0)
            if org_id == ORG_ID_NOT_FOUND:
                org_id_source = "not_found"
                log.debug("orgId not found for %s, will search without it", symbol)
            else:
                org_id_source = "resolved"
        except asyncio.TimeoutError:
            errors.append("orgId resolution timed out, searching without orgId")
        except Exception as exc:
            errors.append(f"orgId resolution failed: {exc}")

        # 2. 发现年报
        reports: list[dict] = []
        try:
            raw_reports = await asyncio.wait_for(
                discover_annual_reports(
                    symbol,
                    start_year=start_year,
                    end_year=end_year,
                    org_id=org_id if org_id != ORG_ID_NOT_FOUND else None,
                ),
                timeout=min(60.0, (end_year - start_year + 1) * 8.0),
            )
            # 3. 过滤与校验
            for rec in raw_reports:
                pdf_url = rec.get("pdf_url") or ""
                if pdf_url:
                    valid, reason = validate_pdf_url(pdf_url)
                    if not valid:
                        errors.append(f"Skipped invalid URL {pdf_url!r}: {reason}")
                        rec = {**rec, "pdf_url": None, "confidence": 0.10}
                reports.append(rec)
        except asyncio.TimeoutError:
            errors.append(f"CNINFO discovery timed out for {symbol} [{start_year}-{end_year}]")
        except Exception as exc:
            errors.append(f"CNINFO discovery failed: {exc}")

        # 4. 缓存
        self._set_cache(cache_key, reports)

        return {
            "symbol": symbol,
            "start_year": start_year,
            "end_year": end_year,
            "org_id": org_id if org_id != ORG_ID_NOT_FOUND else None,
            "org_id_source": org_id_source,
            "reports": reports,
            "total_found": len([r for r in reports if r.get("pdf_url")]),
            "errors": errors,
            "from_cache": False,
            "discovery_method": "cninfo_announcement_query",
        }

    async def discover_latest(
        self,
        symbol: str,
        *,
        years_back: int = 3,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """发现最近 N 年的年报（快速版）。"""
        end_year = date.today().year - 1
        start_year = end_year - years_back + 1
        return await self.discover(
            symbol, start_year=start_year, end_year=end_year, force_refresh=force_refresh
        )


# 单例
cninfo_annual_report_agent = CninfoAnnualReportAgent()
