"""
app/services/company_v2_stock_basic_service.py — 公司/股票基本信息服务（Phase 6T-B）

职责：
1. 查询股票上市日期、公司名称、行业、交易所等基础信息
2. 提供上市日期（list_date）用于确定历史数据起始年份
3. 提供股本信息用于市值计算
4. 支持缓存（Redis TTL 30d）

数据源优先级：
1. BaoStock query_stock_basic（免费）
2. AkShare stock_info_a_code_name（补充）
3. 本地 seed 数据（兜底）

安全原则：
- 不泄露 local_path / token / secret
- 不提供投资建议
- LIST_DATE_UNKNOWN 标记：list_date 缺失时默认取近 10 年数据
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any

log = logging.getLogger(__name__)

# ── 默认回退年份 ─────────────────────────────────────────────────────────────
_DEFAULT_HISTORY_YEARS = 10
_LIST_DATE_UNKNOWN = "LIST_DATE_UNKNOWN"

# ── 本地 seed：部分知名股票的上市日期 ──────────────────────────────────────────
# 用于 BaoStock 查询失败时的兜底
_SEED_LIST_DATE: dict[str, str] = {
    "600519": "2001-08-27",  # 贵州茅台
    "000725": "1996-04-18",  # 京东方
    "601686": "2020-12-04",  # 友发集团（Phase 6T-E 修正：BaoStock exact 为 2020-12-04，原 seed 2016-06-17 有误）
    "000001": "1991-04-03",  # 平安银行
    "600036": "1994-11-29",  # 招商银行
    "601318": "2007-03-01",  # 中国平安
    "000858": "1998-04-27",  # 五粮液
    "601899": "2008-09-25",  # 紫金矿业
    "002594": "2011-06-30",  # 比亚迪
    "600276": "2009-07-15",  # 恒瑞医药
}

# ── BaoStock 行业代码映射（部分） ─────────────────────────────────────────────
_INDUSTRY_MAP: dict[str, str] = {
    "A": "农林牧渔",
    "B": "采矿业",
    "C": "制造业",
    "D": "电力/热力/燃气",
    "E": "建筑业",
    "F": "批发零售",
    "G": "交通运输",
    "H": "住宿餐饮",
    "I": "信息传输/软件",
    "J": "金融业",
    "K": "房地产",
    "L": "租赁商业服务",
    "M": "科研技术服务",
    "N": "水利环境",
    "O": "居民服务",
    "P": "教育",
    "Q": "卫生社会",
    "R": "文化娱乐",
    "S": "综合",
}


def _extract_code(ts_code_or_symbol: str) -> str:
    """提取纯6位股票代码。"""
    if "." in ts_code_or_symbol:
        return ts_code_or_symbol.split(".")[0]
    return ts_code_or_symbol


def _to_ts_code(symbol: str) -> str:
    """将6位代码转为 Tushare 格式。"""
    if "." in symbol:
        return symbol
    if symbol.startswith(("6", "5", "9")):
        return f"{symbol}.SH"
    elif symbol.startswith(("0", "3", "2")):
        return f"{symbol}.SZ"
    elif symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    return f"{symbol}.SH"


def _to_bs_code(ts_code: str) -> str:
    """将 Tushare 格式转为 BaoStock 格式。"""
    if "." not in ts_code:
        code = ts_code
        exchange = "sh" if code.startswith(("6", "5")) else "sz"
        return f"{exchange}.{code}"
    code, ex = ts_code.split(".", 1)
    return f"{ex.lower()}.{code}"


async def _fetch_baostock_stock_basic(ts_code: str) -> dict[str, Any] | None:
    """
    从 BaoStock 获取股票基本信息。
    返回 dict 或 None（查询失败）。
    """
    try:
        import baostock as bs
        import io, sys
        from contextlib import contextmanager

        @contextmanager
        def _suppress():
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
            try:
                yield
            finally:
                sys.stdout = old_out
                sys.stderr = old_err

        bs_code = _to_bs_code(ts_code)

        def _sync_query() -> dict | None:
            with _suppress():
                bs.login()
            try:
                rs = bs.query_stock_basic(code=bs_code)
                rows = []
                while rs.error_code == "0" and rs.next():
                    rows.append(dict(zip(rs.fields, rs.get_row_data())))
                return rows[0] if rows else None
            finally:
                with _suppress():
                    bs.logout()

        row = await asyncio.to_thread(_sync_query)
        if not row:
            return None

        symbol = _extract_code(ts_code)
        list_date_raw = row.get("ipoDate") or row.get("listDate") or ""
        company_name = row.get("code_name") or row.get("companyName") or ""
        exchange_raw = row.get("exchange") or row.get("market") or ""
        # 行业（BaoStock 返回 industry 字段，中文名称）
        industry = row.get("industry") or ""
        if not industry:
            type_code = (row.get("type") or "")[:1]
            industry = _INDUSTRY_MAP.get(type_code, "")

        return {
            "symbol": symbol,
            "ts_code": ts_code,
            "company_name": company_name,
            "exchange": exchange_raw or ("上交所" if ts_code.endswith(".SH") else "深交所"),
            "market": "CN",
            "list_date": list_date_raw,
            "industry": industry,
            "area": row.get("area") or "",
            "source": "baostock",
        }
    except ImportError:
        log.warning("baostock 未安装")
        return None
    except Exception as e:
        log.warning("BaoStock query_stock_basic [%s] 失败: %s", ts_code, e)
        return None


async def _fetch_akshare_stock_info(symbol: str) -> dict[str, Any] | None:
    """
    从 AkShare 获取股票基本信息（补充）。
    """
    try:
        import akshare as ak

        def _sync_query() -> dict | None:
            try:
                # 尝试获取公司简介
                df = ak.stock_profile_em(symbol=symbol)
                if df is None or df.empty:
                    return None
                row = df.iloc[0].to_dict() if len(df) > 0 else {}
                return row
            except Exception:
                return None

        info = await asyncio.to_thread(_sync_query)
        if not info:
            return None

        return {
            "symbol": symbol,
            "ts_code": _to_ts_code(symbol),
            "company_name": str(info.get("公司名称") or info.get("name") or ""),
            "exchange": str(info.get("所属交易所") or ""),
            "industry": str(info.get("行业") or ""),
            "main_business": str(info.get("主营业务") or ""),
            "website": str(info.get("公司主页") or ""),
            "chairman": str(info.get("法人代表") or ""),
            "area": str(info.get("省份") or ""),
            "source": "akshare_profile",
        }
    except Exception as e:
        log.debug("AkShare stock profile [%s] 失败: %s", symbol, e)
        return None


async def get_stock_basic(
    symbol: str,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    获取股票/公司基本信息，含上市日期（用于历史数据范围）。

    返回结构：
    {
      "symbol": "601686",
      "ts_code": "601686.SH",
      "company_name": "友发集团股份有限公司",
      "exchange": "上交所",
      "market": "CN",
      "list_date": "2016-06-17",
      "list_year": 2016,
      "delist_date": null,
      "industry": "钢铁",
      "area": "天津",
      "main_business": null,
      "website": null,
      "chairman": null,
      "list_date_status": "exact" | "seed" | "unknown",
      "source": "baostock" | "akshare_profile" | "seed" | "default",
      "updated_at": "...",
    }
    """
    ts_code = _to_ts_code(symbol)
    code = _extract_code(symbol)
    today_str = date.today().isoformat()

    # 尝试 BaoStock
    bs_info = await _fetch_baostock_stock_basic(ts_code)
    if bs_info and bs_info.get("list_date"):
        list_date = bs_info["list_date"]
        list_date_status = "exact"
        source_info = bs_info
        source = "baostock"
    else:
        # 尝试 seed
        seed_date = _SEED_LIST_DATE.get(code)
        if seed_date:
            list_date = seed_date
            list_date_status = "seed"
            source = "seed"
        else:
            list_date = ""
            list_date_status = "unknown"
            source = "default"
        source_info = bs_info or {}

    # 尝试 AkShare 补充 company info
    ak_info = None
    if not source_info.get("company_name") or not source_info.get("industry"):
        ak_info = await _fetch_akshare_stock_info(code)

    # 解析上市年份
    list_year: int | None = None
    if list_date:
        try:
            list_year = int(list_date[:4])
        except (ValueError, IndexError):
            pass

    return {
        "symbol": code,
        "ts_code": ts_code,
        "company_name": (
            source_info.get("company_name")
            or (ak_info or {}).get("company_name")
            or ""
        ),
        "exchange": (
            source_info.get("exchange")
            or (ak_info or {}).get("exchange")
            or ("上交所" if ts_code.endswith(".SH") else "深交所")
        ),
        "market": "CN",
        "list_date": list_date,
        "list_year": list_year,
        "delist_date": None,
        "industry": (
            source_info.get("industry")
            or (ak_info or {}).get("industry")
            or ""
        ),
        "area": (
            source_info.get("area")
            or (ak_info or {}).get("area")
            or ""
        ),
        "main_business": (ak_info or {}).get("main_business"),
        "website": (ak_info or {}).get("website"),
        "chairman": (ak_info or {}).get("chairman"),
        "list_date_status": list_date_status,
        "source": source,
        "updated_at": today_str,
    }


def get_default_start_year(
    stock_basic: dict[str, Any],
    *,
    min_years: int = _DEFAULT_HISTORY_YEARS,
) -> tuple[int, str]:
    """
    根据 stock_basic 确定历史数据的起始年份。

    Returns:
        (start_year, status) where status is one of:
            "from_list_date" — 使用实际上市年份
            "default_10y"    — 回退到近10年（list_date 未知）
    """
    list_year = stock_basic.get("list_year")
    today_year = date.today().year

    if list_year and isinstance(list_year, int) and list_year >= 1990:
        return list_year, "from_list_date"
    else:
        fallback_year = today_year - min_years
        return fallback_year, "default_10y"
