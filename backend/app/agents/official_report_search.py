"""
official_report_search.py — Phase 2B: Official Financial Report Search & Verification.

Public API
----------
official_financial_report_search(...)  async — search official sources for a report
verify_financial_report_candidate(...)  sync  — verify a candidate's authenticity
classify_source_authority(url)          sync  — return (source_level, authority_score)
parse_financial_analysis_intent(query)  sync  — enhanced intent parser for report+kline

Source Authority Levels
-----------------------
  A — official_exchange   : sse.com.cn, szse.cn, cninfo.com.cn, hkexnews.hk, sec.gov
  A — official_company    : company IR page (heuristic)
  B — authoritative_media : eastmoney, 10jqka, xueqiu, yahoo finance, nasdaq.com
  C — general             : everything else

Safety
------
  Only verified (source_official=True, authority_score≥0.8, period_match=True,
  company_match=True) candidates should enter LLM as core financial data.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

log = logging.getLogger(__name__)

# ── Source authority registry ──────────────────────────────────────────────────

# (source_level, base_authority_score, human-readable name)
_OFFICIAL_DOMAINS: dict[str, tuple[str, float, str]] = {
    # CN — A-share exchanges + official disclosure
    "sse.com.cn":      ("official_exchange", 0.98, "上海证券交易所"),
    "www.sse.com.cn":  ("official_exchange", 0.98, "上海证券交易所"),
    "szse.cn":         ("official_exchange", 0.98, "深圳证券交易所"),
    "www.szse.cn":     ("official_exchange", 0.98, "深圳证券交易所"),
    "cninfo.com.cn":   ("official_exchange", 0.96, "巨潮资讯"),
    "www.cninfo.com.cn": ("official_exchange", 0.96, "巨潮资讯"),
    "static.cninfo.com.cn": ("official_exchange", 0.96, "巨潮资讯"),
    # HK
    "hkexnews.hk":     ("official_exchange", 0.97, "香港联交所披露平台"),
    "www.hkexnews.hk": ("official_exchange", 0.97, "香港联交所披露平台"),
    # US
    "sec.gov":         ("official_exchange", 0.99, "SEC EDGAR"),
    "www.sec.gov":     ("official_exchange", 0.99, "SEC EDGAR"),
    "efts.sec.gov":    ("official_exchange", 0.99, "SEC EDGAR"),
    # B-level authoritative third-party
    "finance.eastmoney.com": ("authoritative_media", 0.72, "东方财富"),
    "eastmoney.com":   ("authoritative_media", 0.72, "东方财富"),
    "10jqka.com.cn":   ("authoritative_media", 0.70, "同花顺"),
    "xueqiu.com":      ("authoritative_media", 0.65, "雪球"),
    "finance.yahoo.com": ("authoritative_media", 0.70, "Yahoo Finance"),
    "nasdaq.com":      ("authoritative_media", 0.73, "Nasdaq"),
    "marketwatch.com": ("authoritative_media", 0.68, "MarketWatch"),
}

_LEVEL_ORDER = {"official_exchange": 0, "official_company": 1,
                "authoritative_media": 2, "general": 3}


def classify_source_authority(url: str) -> dict:
    """
    Classify a URL's source authority.

    Returns
    -------
    {
        "source_level":     "official_exchange" | "official_company" |
                            "authoritative_media" | "general",
        "authority_score":  float 0.0–1.0,
        "source_name":      str,
        "source_official":  bool,
    }
    """
    try:
        parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc.lower().lstrip("www.")
    except Exception:
        domain = url.lower()

    # Direct lookup
    for known_domain, (level, score, name) in _OFFICIAL_DOMAINS.items():
        if domain == known_domain or domain.endswith(f".{known_domain}"):
            return {
                "source_level":    level,
                "authority_score": score,
                "source_name":     name,
                "source_official": level in ("official_exchange", "official_company"),
            }

    # Heuristic: investor relations subdomains
    if re.search(r"ir\.|investor|investors\.|investor-relations", domain):
        return {
            "source_level":    "official_company",
            "authority_score": 0.88,
            "source_name":     domain,
            "source_official": True,
        }

    return {
        "source_level":    "general",
        "authority_score": 0.30,
        "source_name":     domain or "unknown",
        "source_official": False,
    }


# ── Report period helpers ─────────────────────────────────────────────────────

_YEAR_RE    = re.compile(r"(20\d{2}|19\d{2})")
_Q1_RE      = re.compile(r"一季|Q1|第一季|1Q")
_Q2_RE      = re.compile(r"二季|Q2|第二季|2Q|半年|中报|半年报")
_Q3_RE      = re.compile(r"三季|Q3|第三季|3Q")
_Q4_RE      = re.compile(r"四季|Q4|第四季|4Q")
_ANNUAL_RE  = re.compile(r"年报|年度报告|annual.?report|10-k|10k", re.IGNORECASE)
_SEMI_RE    = re.compile(r"半年报|中报|semi.?annual|6-k", re.IGNORECASE)
_QREPORT_RE = re.compile(r"季报|季度报告|quarterly|10-q|10q", re.IGNORECASE)

# Human-readable labels — never expose internal enum keys to users
_REPORT_TYPE_DISPLAY: dict[str, str] = {
    "latest_periodic_report": "最新已披露定期报告",
    "annual_report":          "年度报告",
    "semi_annual_report":     "半年度报告",
    "quarterly_report":       "季度报告",
    "q1_report":              "一季报",
    "q3_report":              "三季报",
}

_KLINE_MAP = [
    # (pattern, trading_days, label)
    (re.compile(r"一年|12个月|全年"), 250, "近1年"),
    (re.compile(r"六个月|半年|6个月"), 120, "近6个月"),
    (re.compile(r"三个月|3个月|90[日天]"), 60, "近3个月"),
    (re.compile(r"两个月|2个月|60[日天]"), 40, "近2个月"),
    (re.compile(r"一个月|1个月|30[日天]|近一月|最近一个月|近30"), 30, "近30个交易日"),
    (re.compile(r"两周|2周|14[日天]"), 10, "近两周"),
    (re.compile(r"一周|1周|七天|7[日天]|近一周"), 5, "近5个交易日"),
]


def _parse_report_period(query: str) -> dict:
    year_m = _YEAR_RE.search(query)
    report_year = int(year_m.group(1)) if year_m else None

    # "年报" or explicit "年份+财报" (e.g. "2026财报") → annual_report
    # "财报" alone / "最新财报" (no explicit year) → latest_periodic_report
    _year_caibao = re.search(r"(20\d{2}|19\d{2}).{0,2}财报|财报.{0,2}(20\d{2}|19\d{2})", query)
    if _ANNUAL_RE.search(query) or "年报" in query or _year_caibao:
        report_type = "annual_report"
        report_period = None
    elif re.search(r"财报|最新.{0,4}报告|最近.{0,4}报告", query):
        # "最新财报" / "财报" alone without a year → latest periodic report
        report_type = "latest_periodic_report"
        report_period = None
    elif _SEMI_RE.search(query):
        report_type = "semi_annual_report"
        report_period = "H1"
    elif _Q1_RE.search(query):
        report_type = "quarterly_report"; report_period = "Q1"
    elif _Q2_RE.search(query):
        report_type = "semi_annual_report"; report_period = "Q2"
    elif _Q3_RE.search(query):
        report_type = "quarterly_report"; report_period = "Q3"
    elif _Q4_RE.search(query):
        report_type = "quarterly_report"; report_period = "Q4"
    elif _QREPORT_RE.search(query):
        report_type = "quarterly_report"; report_period = None
    else:
        report_type = "annual_report"; report_period = None

    return {"report_year": report_year, "report_type": report_type,
            "report_period": report_period}


def _parse_kline_period(query: str) -> dict:
    for pattern, days, label in _KLINE_MAP:
        if pattern.search(query):
            return {"kline_period": "daily", "kline_limit": days,
                    "period_label": label}
    return {"kline_period": None, "kline_limit": None, "period_label": ""}


# ── Company → exchange mapping ────────────────────────────────────────────────

_SYMBOL_EXCHANGE: dict[str, str] = {
    # 6xxxxx / 688xxx → SSE
}


def _infer_exchange(symbol: str, market: str) -> str:
    if market != "CN" or not symbol:
        return ""
    if symbol.startswith(("6", "9")):
        return "SSE"
    if symbol.startswith(("0", "3", "2")):
        return "SZSE"
    return ""


_CN_COMPANY_MAP: dict[str, tuple[str, str, str]] = {
    # name → (symbol, market, company_full_name)
    "茅台":     ("600519", "CN", "贵州茅台"),
    "贵州茅台": ("600519", "CN", "贵州茅台"),
    "中船特气": ("688146", "CN", "中船特气"),
    "宁德时代": ("300750", "CN", "宁德时代"),
    "紫金矿业": ("601899", "CN", "紫金矿业"),
    "平安银行": ("000001", "CN", "平安银行"),
    "腾讯":     ("00700", "HK", "腾讯控股"),
    "腾讯控股": ("00700", "HK", "腾讯控股"),
    "阿里巴巴": ("09988", "HK", "阿里巴巴集团"),
    "美团":     ("03690", "HK", "美团"),
    "比亚迪":   ("002594", "CN", "比亚迪股份"),
    "招商银行": ("600036", "CN", "招商银行"),
    "工商银行": ("601398", "CN", "工商银行"),
}

_US_COMPANY_MAP: dict[str, tuple[str, str]] = {
    "苹果": ("AAPL", "苹果公司"),
    "苹果公司": ("AAPL", "苹果公司"),
    "微软": ("MSFT", "微软"),
    "谷歌": ("GOOGL", "谷歌"),
    "亚马逊": ("AMZN", "亚马逊"),
    "特斯拉": ("TSLA", "特斯拉"),
    "英伟达": ("NVDA", "英伟达"),
    "Meta": ("META", "Meta"),
    "脸书": ("META", "Meta"),
}


def parse_financial_analysis_intent(query: str) -> dict:
    """
    Enhanced intent parser for the financial report + kline analysis scenario.

    Returns a superset of _detect_intent(), adding:
      company_name, exchange, need_report,
      report_year, report_type, report_period,
      kline_period, kline_limit, period_label
    """
    # Imports here to avoid circular import with financial_agent
    from app.agents.financial_agent import _detect_intent  # noqa: PLC0415

    base = _detect_intent(query)
    symbol  = base["symbol"]
    market  = base["market"]
    company_name = ""
    exchange = ""

    # Try CN company names
    for name, (sym, mkt, full_name) in _CN_COMPANY_MAP.items():
        if name in query:
            symbol       = sym
            market       = mkt
            company_name = full_name
            exchange     = _infer_exchange(sym, mkt)
            break

    # Try US company names
    if not symbol:
        for name, (sym, full_name) in sorted(
            _US_COMPANY_MAP.items(), key=lambda x: -len(x[0])
        ):
            if name in query:
                symbol       = sym
                market       = "US"
                company_name = full_name
                exchange     = "NASDAQ"
                break

    # CN 6-digit code
    if not symbol:
        m = re.search(r"\b(\d{6})\b", query)
        if m:
            symbol  = m.group(1)
            market  = "CN"
            exchange = _infer_exchange(symbol, "CN")

    # US ticker
    if not symbol:
        m = re.search(r"\b([A-Z]{1,5})\b", query)
        if m:
            candidate = m.group(1)
            from app.agents.financial_agent import _KNOWN_US_TICKERS  # noqa: PLC0415
            if candidate in _KNOWN_US_TICKERS:
                symbol = candidate; market = "US"

    # Need-report detection
    _REPORT_TRIGGER = re.compile(
        r"财报|年报|年度报告|季报|季度报告|半年报|中报|经营状况|基本面|业绩表现|经营业绩"
        r"|annual.?report|quarterly.?report|10-k|10-q",
        re.IGNORECASE,
    )
    need_report = bool(_REPORT_TRIGGER.search(query))

    # Report period
    period_info = _parse_report_period(query)

    # Kline period
    kline_info = _parse_kline_period(query)
    need_kline = (
        base["need_kline"]
        or bool(kline_info["kline_limit"])
        or bool(re.search(r"行情|股价|走势|涨跌|一[个]?月|近", query))
    )

    # need_rag: triggered by report queries
    need_rag = base["need_rag"] or need_report

    return {
        "symbol":       symbol,
        "market":       market,
        "exchange":     exchange,
        "company_name": company_name,
        # original flags
        "need_quote":    base["need_quote"],
        "need_news":     base["need_news"],
        "need_kline":    need_kline,
        "need_rag":      need_rag,
        # C25: realtime market search flag — MUST be forwarded from _detect_intent
        # without this line, universal_market_search is never triggered for
        # no-symbol queries like "半导体行业最近有哪些热门股？"
        "need_realtime": base["need_realtime"],
        # report flags
        "need_report":  need_report,
        "report_year":  period_info["report_year"],
        "report_type":  period_info["report_type"],
        "report_period": period_info["report_period"],
        # kline details
        "kline_period": kline_info["kline_period"] or "daily",
        "kline_limit":  kline_info["kline_limit"] or (30 if need_kline else None),
        "period_label": kline_info["period_label"] or "近30个交易日",
    }


# ── Candidate verification ────────────────────────────────────────────────────

def verify_financial_report_candidate(
    candidate: dict,
    expected: dict,
) -> dict:
    """
    Verify a candidate financial report against expected criteria.

    Parameters
    ----------
    candidate : from official_financial_report_search
    expected  : {symbol, company_name, report_year, report_type}

    Returns
    -------
    {
        verified: bool,
        authority_score: float,
        title_match: bool,
        company_match: bool,
        period_match: bool,
        report_type_match: bool,
        source_official: bool,
        risk_flags: list[str],
        reason: str,
    }
    """
    auth = classify_source_authority(candidate.get("url", ""))
    authority_score = candidate.get("confidence", auth["authority_score"])
    source_official = auth["source_official"]

    title       = candidate.get("title", "").lower()
    company_name = expected.get("company_name", "")
    symbol       = expected.get("symbol", "")
    exp_year     = expected.get("report_year")
    exp_type     = expected.get("report_type", "")

    # Company match: company name or symbol in title
    company_match = bool(company_name and company_name in title)
    if not company_match and symbol:
        company_match = symbol.lower() in title or symbol in candidate.get("title", "")

    # Period match: report year in title
    period_match = True
    if exp_year:
        period_match = str(exp_year) in candidate.get("title", "")

    # Report type match
    _TYPE_KEYWORDS = {
        "annual_report":       ["年度报告", "年报", "annual report", "10-k"],
        "quarterly_report":    ["季度报告", "季报", "quarterly report", "10-q"],
        "semi_annual_report":  ["半年度报告", "半年报", "中报", "semi-annual"],
    }
    expected_keywords = _TYPE_KEYWORDS.get(exp_type, [])
    report_type_match = any(kw in title for kw in expected_keywords) if expected_keywords else True

    title_match = company_match or (symbol.lower() in title)

    risk_flags: list[str] = []
    if not source_official:
        risk_flags.append("source_not_official")
    if not company_match:
        risk_flags.append("company_mismatch")
    if not period_match:
        risk_flags.append("period_mismatch")
    if not report_type_match:
        risk_flags.append("report_type_mismatch")
    if authority_score < 0.8:
        risk_flags.append("low_authority_score")

    verified = (
        source_official
        and company_match
        and period_match
        and report_type_match
        and authority_score >= 0.8
        and not risk_flags
    )

    if verified:
        reason = "来源官方，标题、公司、报告期及报告类型均匹配，符合正式定期报告特征"
    elif risk_flags:
        reason = f"审核未通过：{', '.join(risk_flags)}"
    else:
        reason = "部分字段匹配失败"

    return {
        "verified":          verified,
        "authority_score":   round(authority_score, 4),
        "title_match":       title_match,
        "company_match":     company_match,
        "period_match":      period_match,
        "report_type_match": report_type_match,
        "source_official":   source_official,
        "risk_flags":        risk_flags,
        "reason":            reason,
    }


# ── cninfo.com.cn search ──────────────────────────────────────────────────────

_CNINFO_CATEGORY = {
    "annual_report":      "category_ndbg_szsh",
    "semi_annual_report": "category_bndbg_szsh",
    "quarterly_report":   "category_sjdbg_szsh",
}

_CNINFO_COLUMN = {
    "SSE":  "sse",
    "SZSE": "szse",
}

_CNINFO_SEARCH_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
_CNINFO_PDF_BASE   = "https://static.cninfo.com.cn/"
_CNINFO_TIMEOUT    = 10.0


async def _search_cninfo(
    symbol: str,
    company_name: str,
    exchange: str,
    report_year: int | None,
    report_type: str,
) -> list[dict]:
    """
    Query 巨潮资讯 (cninfo.com.cn) for official A-share disclosures.

    Returns a list of candidate dicts.
    Falls back to [] on any network/parse error.
    """
    try:
        import httpx  # noqa: PLC0415
    except ImportError:
        log.warning("httpx not installed — cninfo search unavailable")
        return []

    category = _CNINFO_CATEGORY.get(report_type, "category_ndbg_szsh")
    column   = _CNINFO_COLUMN.get(exchange, "sse")

    # Date filter: search the disclosure year range (report filed year after)
    date_range = ""
    if report_year:
        filed_year_start = report_year + 1 if report_type == "annual_report" else report_year
        filed_year_end   = filed_year_start + 1
        date_range = f"{filed_year_start}-01-01%7C{filed_year_end}-12-31"

    payload = {
        "stock":       f"{symbol},{company_name}" if company_name else symbol,
        "tabName":     "fulltext",
        "pageSize":    "10",
        "pageNum":     "1",
        "column":      column,
        "category":    category,
        "plate":       "",
        "seDate":      date_range,
        "searchkey":   "",
        "secid":       "",
        "sortName":    "",
        "sortType":    "",
        "isHLtitle":   "true",
    }

    try:
        async with httpx.AsyncClient(timeout=_CNINFO_TIMEOUT) as client:
            resp = await client.post(
                _CNINFO_SEARCH_URL,
                data=payload,
                headers={"User-Agent": "Mozilla/5.0 (Financial Research Bot)"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.warning("cninfo search failed: %s", exc)
        return []

    announcements = data.get("announcements") or []
    candidates: list[dict] = []

    for ann in announcements[:5]:  # top 5 results
        adj_url  = ann.get("adjunctUrl", "")
        full_url = _CNINFO_PDF_BASE + adj_url if adj_url else ""
        title    = ann.get("announcementTitle", "")
        pub_ts   = ann.get("announcementTime")
        pub_date = ""
        if isinstance(pub_ts, int):
            from datetime import datetime, timezone  # noqa: PLC0415
            pub_date = datetime.fromtimestamp(pub_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

        auth_info = classify_source_authority(full_url or _CNINFO_SEARCH_URL)
        candidates.append({
            "title":        title,
            "url":          full_url,
            "source_domain": "cninfo.com.cn",
            "source_name":  "巨潮资讯",
            "source_level": auth_info["source_level"],
            "report_year":  report_year,
            "report_type":  report_type,
            "published_at": pub_date,
            "file_type":    ann.get("adjunctType", "PDF").lower(),
            "confidence":   auth_info["authority_score"],
            "reason":       f"巨潮资讯官方披露，标题：{title[:60]}",
        })

    return candidates


async def _search_sec_edgar(
    symbol: str,
    company_name: str,
    report_year: int | None,
    report_type: str,
) -> list[dict]:
    """
    Search SEC EDGAR for US company filings.

    Returns up to 3 candidates with source_level=official_exchange.
    Falls back to [] on any error.
    """
    form_map = {
        "annual_report":     "10-K",
        "quarterly_report":  "10-Q",
        "semi_annual_report": "20-F",
    }
    form = form_map.get(report_type, "10-K")

    edgar_url = (
        f"https://efts.sec.gov/LATEST/search-index?q=%22{symbol}%22"
        f"&dateRange=custom&startdt={report_year}-01-01&enddt={report_year + 1}-12-31"
        f"&forms={form}"
    ) if report_year else (
        f"https://efts.sec.gov/LATEST/search-index?q=%22{symbol}%22&forms={form}"
    )

    try:
        import httpx  # noqa: PLC0415
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                edgar_url,
                headers={"User-Agent": "TradingAgents Research Bot contact@example.com"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.warning("SEC EDGAR search failed: %s", exc)
        return []

    hits = data.get("hits", {}).get("hits", [])[:3]
    candidates = []
    for hit in hits:
        src = hit.get("_source", {})
        candidates.append({
            "title":        src.get("display_names", [company_name or symbol])[0] + f" {form}",
            "url":          "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                            f"&CIK={symbol}&type={form}&dateb=&owner=include&count=5",
            "source_domain": "sec.gov",
            "source_name":  "SEC EDGAR",
            "source_level": "official_exchange",
            "report_year":  report_year,
            "report_type":  report_type,
            "published_at": src.get("period_of_report", ""),
            "file_type":    "html",
            "confidence":   0.95,
            "reason":       f"SEC EDGAR 官方申报数据库，表格类型 {form}",
        })
    return candidates


# ── Main search function ───────────────────────────────────────────────────────

async def official_financial_report_search(
    symbol: str,
    market: str,
    *,
    exchange: str = "",
    company_name: str = "",
    report_year: int | None = None,
    report_type: str = "annual_report",
) -> dict:
    """
    Search official sources for a financial report.

    Returns
    -------
    {
        "ok": True,
        "query": str,
        "candidates": [
            {title, url, source_domain, source_name, source_level,
             report_year, report_type, published_at, file_type,
             confidence, reason}
        ]
    }
    or on all-sources failure:
        {"ok": True, "candidates": [], "not_found_reason": str}
    """
    _type_label = _REPORT_TYPE_DISPLAY.get(report_type, report_type)
    # C25.11: avoid "最新最新已披露定期报告" — when _type_label already starts with "最新",
    # don't prepend the "最新" year-fallback prefix.
    _year_prefix = (
        str(report_year) if report_year
        else ('' if _type_label.startswith('最新') else '最新')
    )
    query_label = (
        f"{company_name or symbol}"
        + (f" {_year_prefix}" if _year_prefix else "")
        + f" {_type_label}"
    )

    candidates: list[dict] = []

    if market == "CN":
        cn_results = await _search_cninfo(
            symbol, company_name, exchange or _infer_exchange(symbol, market),
            report_year, report_type,
        )
        candidates.extend(cn_results)

    elif market == "US":
        us_results = await _search_sec_edgar(
            symbol, company_name, report_year, report_type
        )
        candidates.extend(us_results)

    elif market == "HK":
        # HKEX search — stub for Phase 2B; returns empty (upgrade in Phase 2C)
        log.info("HK report search not yet implemented; returning empty candidates")

    if not candidates:
        return {
            "ok":               True,
            "query":            query_label,
            "candidates":       [],
            "not_found_reason": (
                f"未在官方披露渠道检索到{company_name or symbol}"
                + (f"{_year_prefix}" if _year_prefix else "")
                + f"{_type_label}，"
                "建议直接前往巨潮资讯（cninfo.com.cn）或交易所官网查询。"
            ),
        }

    # Sort by confidence descending
    candidates.sort(key=lambda c: c.get("confidence", 0), reverse=True)

    return {
        "ok":         True,
        "query":      query_label,
        "candidates": candidates,
    }


# ── Document download helper (for agent use) ──────────────────────────────────

async def download_document_text(url: str) -> str | None:
    """
    Download text content from a URL.

    For PDFs, returns None (caller should use ingest with file_path).
    For HTML, returns cleaned text.
    Falls back to None on any error.
    """
    try:
        import httpx  # noqa: PLC0415
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Financial Research Bot)"},
            )
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()
            if "pdf" in content_type or url.lower().endswith(".pdf"):
                # PDF: can't extract without file — caller handles separately
                return None
            text = resp.text
            if "html" in content_type:
                from app.agents.financial_document_ingest import _parse_html  # noqa: PLC0415
                text = _parse_html(text)
            return text
    except Exception as exc:
        log.warning("download_document_text failed for %s: %s", url, exc)
        return None
