"""
app/services/cninfo_org_resolver.py — CNINFO orgId 解析服务（Phase 6T-A）

CNINFO（巨潮资讯）公告查询接口在某些调用中需要 orgId。
本服务负责：
1. 本地缓存优先（内存 + Redis）
2. CNINFO 搜索接口自动查询
3. 手动 seed mapping 兜底
4. 失败时返回 ORG_ID_NOT_FOUND

安全原则：
- orgId 只用于发往 CNINFO 官方接口，不对外暴露
- 不把 orgId 写入 API 响应
- 失败时优雅降级（直接用 stock_code 查询，无 orgId）
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

ORG_ID_NOT_FOUND = "ORG_ID_NOT_FOUND"

# ── 已知 orgId 种子映射（常用标的，减少网络查询）───────────────────────────────
# 格式：stock_code → orgId
# 来源：公开 CNINFO 公告 URL 中的 orgId 字段
_SEED_ORG_MAP: dict[str, str] = {
    # 沪深 300 / 常见标的
    "600519": "9900002978",   # 贵州茅台
    "000858": "9900004896",   # 五粮液
    "601318": "9900004941",   # 中国平安
    "600036": "9900003855",   # 招商银行
    "000725": "9900006247",   # 京东方A
    "601012": "9900045066",   # 隆基绿能
    "300750": "9900033484",   # 宁德时代
    "601688": "9900010003",   # 华泰证券
    "601686": "9900006256",   # 友发集团（已上市）
    "600186": "9900007026",   # 荷花泡泡
    "000100": "9900002984",   # TCL科技
}

# ── 内存缓存 ──────────────────────────────────────────────────────────────────
_MEMORY_CACHE: dict[str, tuple[str, float]] = {}  # stock_code → (org_id, cached_at)
_CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days
_FAIL_TTL_SECONDS = 24 * 3600       # 1 day for not-found

# ── CNINFO 股票搜索接口 ────────────────────────────────────────────────────────
_CNINFO_SEARCH_URL = "http://www.cninfo.com.cn/new/information/topSearch/detailOfQuery"
_TIMEOUT = 8.0
_USER_AGENT = (
    "Mozilla/5.0 (compatible; TradingAgentsResearch/1.0; "
    "Public financial data research)"
)
_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Referer": "http://www.cninfo.com.cn/",
    "Accept": "application/json, */*; q=0.01",
}


def _is_cached(stock_code: str) -> tuple[str | None, bool]:
    """返回 (org_id_or_none, is_valid)"""
    entry = _MEMORY_CACHE.get(stock_code)
    if not entry:
        return None, False
    org_id, cached_at = entry
    ttl = _FAIL_TTL_SECONDS if org_id == ORG_ID_NOT_FOUND else _CACHE_TTL_SECONDS
    if time.monotonic() - cached_at > ttl:
        return None, False
    return org_id, True


def _cache_set(stock_code: str, org_id: str) -> None:
    _MEMORY_CACHE[stock_code] = (org_id, time.monotonic())


async def _query_cninfo(stock_code: str) -> str | None:
    """
    通过 CNINFO 股票搜索接口查询 orgId。
    返回 orgId 字符串，未找到时返回 None。
    """
    params = {"keyWord": stock_code, "matchType": "accurate"}
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT) as client:
            resp = await client.get(_CNINFO_SEARCH_URL, params=params)
            if resp.status_code != 200:
                log.debug("CNINFO org search HTTP %d for %s", resp.status_code, stock_code)
                return None
            data = resp.json()
            # Response: {"data": [{"orgId": "...", "stockCode": "...", "orgName": "..."}]}
            items = data.get("data") or []
            for item in items:
                if item.get("stockCode") == stock_code:
                    org_id = str(item.get("orgId") or "").strip()
                    if org_id:
                        return org_id
            if items:
                org_id = str(items[0].get("orgId") or "").strip()
                if org_id:
                    log.debug("CNINFO orgId fuzzy match for %s: %s", stock_code, org_id)
                    return org_id
    except httpx.TimeoutException:
        log.debug("CNINFO org search timeout for %s", stock_code)
    except Exception as exc:
        log.debug("CNINFO org search error for %s: %s", stock_code, exc)
    return None


async def resolve_org_id(stock_code: str) -> str:
    """
    解析 stock_code 对应的 CNINFO orgId。

    优先级：
    1. 内存缓存
    2. 本地 seed mapping
    3. CNINFO 搜索接口
    4. 失败 → ORG_ID_NOT_FOUND

    Returns:
        orgId 字符串，或 "ORG_ID_NOT_FOUND"
    """
    code = stock_code.strip().lstrip("0") or stock_code.strip()
    # Some codes need leading zeros preserved
    code = stock_code.strip()

    # 1. 内存缓存
    cached, valid = _is_cached(code)
    if valid and cached:
        return cached

    # 2. Seed mapping
    seed = _SEED_ORG_MAP.get(code)
    if seed:
        _cache_set(code, seed)
        log.debug("OrgId from seed for %s: %s", code, seed)
        return seed

    # 3. CNINFO 搜索
    org_id = await _query_cninfo(code)
    if org_id:
        _cache_set(code, org_id)
        log.info("OrgId resolved for %s: %s", code, org_id)
        return org_id

    # 4. 失败
    _cache_set(code, ORG_ID_NOT_FOUND)
    log.debug("OrgId not found for %s", code)
    return ORG_ID_NOT_FOUND


async def resolve_cninfo_stock(
    market: str,
    symbol: str,
    company_name: str | None = None,
) -> dict[str, Any]:
    """
    Resolve the CNINFO stock query identity used by report discovery.

    The API can still search by stock code when orgId is missing, so failure is
    represented as a structured fallback instead of an exception.
    """
    code = symbol.split(".")[0].strip()
    org_id = await resolve_org_id(code)
    return {
        "market": market.upper(),
        "symbol": code,
        "company_name": company_name or "",
        "org_id": None if org_id == ORG_ID_NOT_FOUND else org_id,
        "org_id_status": "not_found" if org_id == ORG_ID_NOT_FOUND else "resolved",
        "stock_query": code,
    }


def seed_org_id(stock_code: str, org_id: str) -> None:
    """手动注入 orgId（用于测试或批量 seed）。"""
    _MEMORY_CACHE[stock_code.strip()] = (org_id, time.monotonic())


def get_cache_snapshot() -> dict[str, Any]:
    """返回当前缓存快照（用于 Debug 和诊断）。"""
    now = time.monotonic()
    return {
        code: {
            "org_id": org_id,
            "age_seconds": int(now - cached_at),
            "source": "seed" if code in _SEED_ORG_MAP else "resolved",
        }
        for code, (org_id, cached_at) in _MEMORY_CACHE.items()
    }
