"""
app/datasource/cninfo_provider.py — CNINFO 巨潮资讯公告数据访问层（Phase 6T-A）

提供对 CNINFO 公告查询接口的结构化封装：
1. search_announcements  — 按股票代码/日期/类目查询公告列表
2. discover_annual_reports — 批量发现历年年报
3. resolve_pdf_url        — 从公告记录提取 PDF URL
4. validate_pdf_url       — URL 安全校验（白名单、HTTPS、PDF 后缀）

安全原则：
- PDF URL host 必须在白名单内
- URL 必须 HTTPS（生产）/ HTTP 仅 static.cninfo.com.cn（允许，该域无 HTTPS）
- URL 必须以 .PDF / .pdf 结尾
- 不允许 file:// / ftp:// / 内网地址
- 不直接枚举 /finalpage/ 路径
- 不暴力猜 PDF ID
- 每次请求 rate limit 1.5s
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

# ── 白名单域名 ───────────────────────────────────────────────────────────────
_ALLOWED_PDF_HOSTS = frozenset([
    "static.cninfo.com.cn",
    "www.cninfo.com.cn",
    "cninfo.com.cn",
])

# ── CNINFO API ──────────────────────────────────────────────────────────────
_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
_FULLTEXT_URL = "http://www.cninfo.com.cn/new/fulltextSearch/full"
_PDF_BASE = "https://static.cninfo.com.cn/"
_TIMEOUT_SECONDS = 10.0
_RATE_LIMIT_SECONDS = 1.5
_MAX_RETRIES = 2

_USER_AGENT = (
    "Mozilla/5.0 (compatible; TradingAgentsResearch/1.0; "
    "Public financial data research)"
)
_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Referer": "http://www.cninfo.com.cn/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
}

# ── 报告类型过滤关键词 ────────────────────────────────────────────────────────
# 注意：annual 的排除词必须包含"半年"，防止"半年度报告"误匹配为"年度报告"
_ANNUAL_INCLUDE = ["年度报告", "年报", "annual report"]
_ANNUAL_EXCLUDE = [
    "摘要", "summary", "更正", "取消", "社会责任", "esg报告", "esg report",
    "审计报告", "监事会", "独立", "英文版",
    "半年",  # 防止"半年度报告"误匹配为年报
]

_SEMI_INCLUDE = ["半年度报告", "半年报", "中期报告"]
_SEMI_EXCLUDE = ["摘要", "更正", "取消", "社会责任", "英文版"]

_Q1_INCLUDE = ["第一季度报告", "一季报", "第1季度"]
_Q1_EXCLUDE = ["摘要", "更正", "取消", "英文版"]

_Q3_INCLUDE = ["第三季度报告", "三季报", "第3季度"]
_Q3_EXCLUDE = ["摘要", "更正", "取消", "英文版"]

# 全局排除词（适用所有报告类型）
# Phase 6T-E: "英文版"不作为中文主报告；"已取消"公告不展示
_GLOBAL_EXCLUDE = [
    "债券", "可转债", "公司债", "理财产品", "非公开发行", "配股",
    "股票期权", "定向增发", "承诺事项", "英文版",
]

# ── CNINFO 报告类目编码（可配置） ─────────────────────────────────────────────
# 上交所后缀 _sse，深交所后缀 _szsh
# 注意：q1 和 q3 用相同的 category_yjdbg（一季/三季报混合类目）
_CATEGORY_MAP: dict[str, list[str]] = {
    "annual":      ["category_ndbg_szsh", "category_ndbg_sse"],
    "semi_annual": ["category_bndbg_szsh", "category_bndbg_sse"],
    "q1":          ["category_yjdbg_szsh", "category_yjdbg_sse"],
    "q3":          ["category_sjdbg_szsh", "category_sjdbg_sse"],
}

# 向后兼容旧版 _CATEGORY_MAP 用法（单字符串接口）
_CATEGORY_COMPAT: dict[str, str] = {
    "annual": "category_ndbg_szsh",
    "semi":   "category_bndbg_szsh",
    "q1":     "category_yjdbg_szsh",
    "q3":     "category_sjdbg_szsh",
}

# 报告类型配置
_REPORT_TYPE_CONFIG: dict[str, dict] = {
    "annual": {
        "include_kws": _ANNUAL_INCLUDE,
        "exclude_kws": _ANNUAL_EXCLUDE,
        "categories": _CATEGORY_MAP["annual"],
        "display": "年度报告",
        "icon": "annual",
    },
    "semi_annual": {
        "include_kws": _SEMI_INCLUDE,
        "exclude_kws": _SEMI_EXCLUDE,
        "categories": _CATEGORY_MAP["semi_annual"],
        "display": "半年度报告",
        "icon": "semi",
    },
    "q1": {
        "include_kws": _Q1_INCLUDE,
        "exclude_kws": _Q1_EXCLUDE,
        "categories": _CATEGORY_MAP["q1"],
        "display": "第一季度报告",
        "icon": "quarterly",
    },
    "q3": {
        "include_kws": _Q3_INCLUDE,
        "exclude_kws": _Q3_EXCLUDE,
        "categories": _CATEGORY_MAP["q3"],
        "display": "第三季度报告",
        "icon": "quarterly",
    },
}


def _exchange_column(stock_code: str) -> str:
    if stock_code.startswith(("6", "5")):
        return "sse"
    elif stock_code.startswith(("0", "3", "2")):
        return "szse"
    elif stock_code.startswith(("4", "8", "9")):
        return "bj"
    return "sse"


def _is_annual_report(title: str) -> bool:
    """判断标题是否为完整年报（非摘要/社会责任等）。"""
    title_low = title.lower()
    has_annual = any(kw.lower() in title_low for kw in _ANNUAL_INCLUDE)
    has_exclude = any(kw.lower() in title_low for kw in _ANNUAL_EXCLUDE)
    return has_annual and not has_exclude


def _clean_cninfo_title(title: str) -> str:
    """Remove CNINFO search highlight tags and normalize whitespace."""
    cleaned = re.sub(r"</?em>", "", title or "", flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def classify_report_type(title: str) -> str | None:
    """
    从标题识别报告类型。
    Returns: "annual" | "semi_annual" | "q1" | "q3" | None（无法识别）
    """
    title_low = title.lower()
    # 全局排除
    if any(kw in title for kw in _GLOBAL_EXCLUDE):
        return None
    # 按优先级检测（年报 > 半年报 > 一季报 > 三季报）
    for rtype in ("annual", "semi_annual", "q1", "q3"):
        cfg = _REPORT_TYPE_CONFIG[rtype]
        has_include = any(kw.lower() in title_low for kw in cfg["include_kws"])
        has_exclude = any(kw.lower() in title_low for kw in cfg["exclude_kws"])
        if has_include and not has_exclude:
            return rtype
    return None


def _is_report_of_type(title: str, report_type: str) -> bool:
    """检查标题是否匹配指定报告类型。"""
    if report_type not in _REPORT_TYPE_CONFIG:
        return False
    cfg = _REPORT_TYPE_CONFIG[report_type]
    title_low = title.lower()
    has_include = any(kw.lower() in title_low for kw in cfg["include_kws"])
    has_exclude = any(kw.lower() in title_low for kw in cfg["exclude_kws"])
    return has_include and not has_exclude


def validate_pdf_url(url: str) -> tuple[bool, str]:
    """
    校验 PDF URL 是否安全合规。

    Returns:
        (is_valid: bool, reason: str)
    """
    if not url:
        return False, "empty URL"
    parsed = urlparse(url)
    # Scheme check
    if parsed.scheme not in ("http", "https"):
        return False, f"scheme {parsed.scheme!r} not allowed"
    # Host whitelist
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_PDF_HOSTS:
        return False, f"host {host!r} not in whitelist"
    # Must look like PDF
    path_upper = (parsed.path or "").upper()
    if not path_upper.endswith(".PDF"):
        return False, "URL does not end with .PDF"
    # Block internal/loopback
    if re.match(r"^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", host or ""):
        return False, "internal address blocked"
    return True, "ok"


def resolve_pdf_url(announcement: dict[str, Any]) -> str | None:
    """
    从公告记录中提取 PDF URL。
    仅处理 adjunctType=PDF 的附件。
    """
    adj_url = announcement.get("adjunctUrl") or ""
    adj_type = (announcement.get("adjunctType") or "").upper()
    if not adj_url or adj_type != "PDF":
        return None
    # Build full URL from base + relative path
    if adj_url.startswith("http"):
        full_url = adj_url
    else:
        full_url = _PDF_BASE + adj_url.lstrip("/")
    valid, reason = validate_pdf_url(full_url)
    if not valid:
        log.debug("Invalid PDF URL %r: %s", full_url, reason)
        return None
    return full_url


def extract_report_metadata(
    announcement: dict[str, Any],
    stock_code: str,
    report_year: int,
    report_type: str = "annual",
) -> dict[str, Any]:
    """
    从公告记录中提取结构化元数据。

    Parameters:
        announcement: CNINFO 返回的公告记录
        stock_code:   6位股票代码
        report_year:  报告年份
        report_type:  报告类型 "annual" | "semi_annual" | "q1" | "q3"
    """
    title = _clean_cninfo_title(announcement.get("announcementTitle") or "")
    org_id = str(announcement.get("orgId") or "")
    ann_id = str(announcement.get("announcementId") or "")
    ann_time_ms = announcement.get("announcementTime") or 0
    ann_date = ""
    if ann_time_ms:
        try:
            dt = datetime.fromtimestamp(ann_time_ms / 1000, tz=timezone.utc)
            ann_date = dt.strftime("%Y-%m-%d")
        except (OSError, OverflowError, ValueError):
            pass
    pdf_url = resolve_pdf_url(announcement)
    adjunct_url = announcement.get("adjunctUrl") or ""
    source_url = (
        f"http://www.cninfo.com.cn/new/disclosure/detail"
        f"?announcementId={ann_id}&orgId={org_id}"
        if ann_id and org_id else ""
    )
    ts_suffix = ".SH" if stock_code.startswith(("6", "5")) else (
        ".SZ" if stock_code.startswith(("0", "3", "2")) else ".BJ"
    )
    ts_code = f"{stock_code}{ts_suffix}"

    # 自动从标题识别真实报告类型（比参数更准确）
    detected_type = classify_report_type(title)
    actual_type = detected_type or report_type

    # Phase 6T-E: 报告年份以标题中的年份为准（如"2023年年度报告"），
    # 防止公告发布年份（announcement year）被错误赋值为 report_year。
    title_year_match = re.search(r"(19|20)\d{2}", title)
    if title_year_match:
        title_year = int(title_year_match.group(0))
        if 1990 <= title_year <= 2100:
            report_year = title_year

    is_correct_type = _is_report_of_type(title, actual_type)
    is_summary = any(kw.lower() in title.lower() for kw in ["摘要", "summary"])
    is_correction = any(kw in title for kw in ["更正", "取消"])

    # 置信度评分
    if pdf_url and is_correct_type and not is_summary:
        confidence = 0.92
    elif pdf_url and is_correct_type:
        confidence = 0.72
    elif pdf_url:
        confidence = 0.50
    else:
        confidence = 0.20

    return {
        "symbol": stock_code,
        "ts_code": ts_code,
        "report_year": report_year,
        "report_type": actual_type,
        "title": title,
        "announcement_date": ann_date,
        "pdf_url": pdf_url,
        "adjunct_url": adjunct_url,
        "source": "cninfo",
        "source_host": "static.cninfo.com.cn" if pdf_url else "",
        "source_url": source_url,
        "org_id": org_id,
        "is_summary": is_summary,
        "is_correction": is_correction,
        "is_annual": _is_annual_report(title),
        "confidence": confidence,
        "discovery_method": "cninfo_announcement_query",
    }


async def search_announcements(
    symbol: str,
    *,
    org_id: str | None = None,
    start_date: str = "",
    end_date: str = "",
    category: str = "category_ndbg_szsh",
    page: int = 1,
    page_size: int = 20,
) -> list[dict[str, Any]]:
    """
    调用 CNINFO 公告查询接口，返回原始公告记录列表。

    Parameters:
        symbol:     6位股票代码（无交易所后缀）
        org_id:     CNINFO 内部机构 ID（可选，提高匹配精度）
        start_date: 开始日期 YYYY-MM-DD
        end_date:   结束日期 YYYY-MM-DD
        category:   公告类目编码
        page:       页码（1-indexed）
        page_size:  每页条数

    Returns:
        原始公告 dict 列表（可能为空）
    """
    column = _exchange_column(symbol)
    form_data: dict[str, str] = {
        "stock":     symbol,
        "tabName":   "fulltext",
        "pageNum":   str(page),
        "pageSize":  str(page_size),
        "column":    column,
        "category":  category,
        "isHLtitle": "true",
    }
    if org_id and org_id != "ORG_ID_NOT_FOUND":
        form_data["orgId"] = org_id
    if start_date and end_date:
        form_data["seDate"] = f"{start_date}~{end_date}"

    await asyncio.sleep(_RATE_LIMIT_SECONDS)
    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(
                headers=_HEADERS,
                timeout=_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                resp = await client.post(_QUERY_URL, data=form_data)
                if resp.status_code == 404:
                    log.debug("CNINFO 404 for %s", symbol)
                    return []
                resp.raise_for_status()
                data = resp.json()
                return data.get("announcements") or []
        except httpx.HTTPStatusError as e:
            log.warning("CNINFO HTTP %d for %s", e.response.status_code, symbol)
            return []
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
                continue
            log.warning("CNINFO timeout/connect for %s: %s", symbol, e)
            return []
        except Exception as e:
            log.warning("CNINFO unexpected error for %s: %s", symbol, e)
            return []
    return []


async def fulltext_search_announcements(
    symbol: str,
    *,
    report_year: int,
    report_type: str,
    page: int = 1,
) -> list[dict[str, Any]]:
    """
    Query CNINFO fulltext search as a fallback when historical announcement
    category queries return empty. This still discovers PDFs through official
    CNINFO announcement JSON and `adjunctUrl`; it never enumerates static IDs.
    """
    label = {
        "annual": "年度报告",
        "semi_annual": "半年度报告",
        "q1": "第一季度报告",
        "q3": "第三季度报告",
    }.get(report_type, "年度报告")
    params = {
        "searchkey": f"{symbol} {report_year}年{label}",
        "pageNum": str(page),
    }
    await asyncio.sleep(0.5)
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = await client.get(_FULLTEXT_URL, params=params)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            return data.get("announcements") or []
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        log.warning("CNINFO fulltext timeout/connect for %s: %s", symbol, exc)
    except Exception as exc:
        log.warning("CNINFO fulltext unexpected error for %s: %s", symbol, exc)
    return []


async def discover_annual_reports(
    symbol: str,
    *,
    start_year: int,
    end_year: int,
    org_id: str | None = None,
    report_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    批量发现指定年份范围的年报。

    Parameters:
        symbol:      6位股票代码
        start_year:  起始年份（含）
        end_year:    结束年份（含）
        org_id:      CNINFO orgId（可选）
        report_types: 报告类型列表（默认 ["annual"]）

    Returns:
        结构化年报记录列表，按年份降序排列
    """
    report_types = report_types or ["annual"]
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for year in range(end_year, start_year - 1, -1):
        for rtype in report_types:
            # 使用新的多类目 map，兼容旧版单字符串
            categories = _CATEGORY_MAP.get(rtype)
            if not categories:
                categories = [_CATEGORY_COMPAT.get(rtype, "category_ndbg_szsh")]
            # 只用第一个（按交易所选择在 search_announcements 内部处理）
            category = categories[0]
            # Date range: year+1-01-01 to year+2-12-31 (announcement may come next year)
            search_start = f"{year}-01-01"
            search_end = f"{year + 2}-12-31"
            announcements = await search_announcements(
                symbol,
                org_id=org_id,
                start_date=search_start,
                end_date=search_end,
                category=category,
                page_size=20,
            )
            for ann in announcements:
                meta = extract_report_metadata(ann, symbol, year, rtype)
                if not meta.get("is_annual"):
                    continue
                pdf_url = meta.get("pdf_url") or ""
                if pdf_url and pdf_url in seen_urls:
                    continue
                if pdf_url:
                    seen_urls.add(pdf_url)
                results.append(meta)

    # Sort by year desc, confidence desc
    results.sort(key=lambda r: (-(r.get("report_year") or 0), -(r.get("confidence") or 0)))
    return results


async def discover_reports(
    symbol: str,
    *,
    start_year: int,
    end_year: int,
    org_id: str | None = None,
    report_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    批量发现指定年份范围的所有类型报告（年报/季报/半年报）。

    这是 discover_annual_reports 的多类型扩展版本。

    Parameters:
        symbol:       6位股票代码
        start_year:   起始年份（含）
        end_year:     结束年份（含）
        org_id:       CNINFO orgId（可选）
        report_types: 报告类型列表（默认 ["annual", "semi_annual", "q1", "q3"]）

    Returns:
        结构化报告记录列表，按年份/类型/置信度降序排列
    """
    import random
    report_types = report_types or ["annual", "semi_annual", "q1", "q3"]
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for rtype in report_types:
        cfg = _REPORT_TYPE_CONFIG.get(rtype)
        if not cfg:
            continue
        categories = cfg["categories"]

        for year in range(end_year, start_year - 1, -1):
            # 年末期和发布期窗口
            search_start = f"{year}-01-01"
            search_end = f"{year + 1}-12-31"
            matched_from_his_query = False

            for category in categories:
                # 随机延迟 0.5-2s（防止过快请求）
                await asyncio.sleep(0.5 + random.random() * 1.5)
                announcements = await search_announcements(
                    symbol,
                    org_id=org_id,
                    start_date=search_start,
                    end_date=search_end,
                    category=category,
                    page_size=30,
                )
                for ann in announcements:
                    meta = extract_report_metadata(ann, symbol, year, rtype)
                    # 过滤：标题必须匹配当前报告类型
                    if not _is_report_of_type(meta.get("title") or "", rtype):
                        continue
                    # 过滤摘要/社会责任等
                    if meta.get("is_summary"):
                        continue
                    pdf_url = meta.get("pdf_url") or ""
                    if pdf_url and pdf_url in seen_urls:
                        continue
                    if pdf_url:
                        seen_urls.add(pdf_url)
                    results.append(meta)
                    matched_from_his_query = True

            if not matched_from_his_query:
                announcements = await fulltext_search_announcements(symbol, report_year=year, report_type=rtype)
                for ann in announcements:
                    meta = extract_report_metadata(ann, symbol, year, rtype)
                    if not _is_report_of_type(meta.get("title") or "", rtype):
                        continue
                    if meta.get("is_summary"):
                        continue
                    pdf_url = meta.get("pdf_url") or ""
                    if pdf_url and pdf_url in seen_urls:
                        continue
                    if pdf_url:
                        seen_urls.add(pdf_url)
                    meta["discovery_method"] = "cninfo_fulltext_search"
                    results.append(meta)

    # 去重（同年同类型只保留一份 canonical：正文优先于摘要，其次置信度最高）
    # Phase 6T-E: 输出 canonical_report / dedup_key / version / is_latest_version /
    # supersedes_report_id / filter_reason 字段。
    best: dict[str, dict] = {}
    duplicates_by_key: dict[str, int] = {}
    for r in results:
        key = f"{r.get('symbol')}:{r.get('report_year')}:{r.get('report_type')}"
        current = best.get(key)
        if current is None:
            best[key] = r
            continue
        duplicates_by_key[key] = duplicates_by_key.get(key, 0) + 1
        # 正文优先于摘要；同为正文时置信度高者优先
        r_rank = (0 if r.get("is_summary") else 1, r.get("confidence", 0))
        c_rank = (0 if current.get("is_summary") else 1, current.get("confidence", 0))
        if r_rank > c_rank:
            best[key] = r

    final = sorted(best.values(), key=lambda r: (
        -(r.get("report_year") or 0),
        r.get("report_type") or "",
        -(r.get("confidence") or 0),
    ))
    for r in final:
        key = f"{r.get('symbol')}:{r.get('report_year')}:{r.get('report_type')}"
        r["dedup_key"] = key
        r["canonical_report"] = True
        r["version"] = 1
        r["is_latest_version"] = True
        r["supersedes_report_id"] = None
        r["filter_reason"] = ""
        r["duplicate_candidates_removed"] = duplicates_by_key.get(key, 0)
    return final
