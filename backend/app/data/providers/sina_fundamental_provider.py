"""
SinaFundamentalProvider — 新浪财经基本面数据 provider（草稿，暂未接入业务）。

探索结论（2026-05-21）：
  - hq.sinajs.cn：只提供实时行情（name/price/OHLCV），无 PE/PB/财务指标。
  - vip.stock.finance.sina.com.cn 财务摘要页：只有 HTML，无稳定 JSON 接口。
  - ff_/fx_ 前缀：返回空字符串，无可用数据。
  - money.finance.sina.com.cn JSON API：提供 K线数据，不提供财务指标。

当前可靠覆盖：
  - company.name      ✅ 可从 hq.sinajs.cn 获取（同 SinaQuoteProvider）
  - valuation.*       ❌ 无稳定 JSON 接口，不建议接入
  - profitability.*   ❌ 无稳定 JSON 接口，不建议接入
  - growth.*          ❌ 无稳定 JSON 接口，不建议接入
  - financial_health.*❌ 无稳定 JSON 接口，不建议接入

接入建议：
  - company.name：可通过 hq.sinajs.cn 作为 AkShare spot 的替代（当 EastMoney 被 Clash 拦截时）。
  - PE / PB / 财务数据：继续使用 AkShare（THS 接口走 _direct_connect 绕过代理）。
  - 港股行情：hq.sinajs.cn/list=hk00700 可用，但 SinaQuoteProvider 需要扩展 HK parser。

后续接入计划（等确认后再实现）：
  - 若需新浪 name fallback，可将 SinaQuoteProvider 的 get_quote() 结果中的 name 字段
    注入 FundamentalDataService._fill_cn() 的 quote_optional 链。
  - 不需要新建此 provider，复用 SinaQuoteProvider 即可。

此文件保留作为探索记录，不被 FastAPI 自动加载，不影响任何现有业务。
"""

from __future__ import annotations

import logging
import re

import requests

log = logging.getLogger(__name__)

_HQ_URL = "https://hq.sinajs.cn/list={}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn",
}


def _to_sina_symbol(market: str, symbol: str) -> str:
    if market.upper() == "CN":
        return f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"
    if market.upper() == "HK":
        return f"hk{symbol.zfill(5)}"
    raise ValueError(f"SinaFundamentalProvider: unsupported market '{market}'")


def _safe_float(fields: list[str], idx: int) -> float | None:
    try:
        v = fields[idx].strip()
        return float(v) if v else None
    except (IndexError, ValueError):
        return None


def _safe_str(fields: list[str], idx: int) -> str | None:
    try:
        v = fields[idx].strip()
        return v if v else None
    except IndexError:
        return None


class SinaFundamentalProvider:
    """
    新浪财经基本面数据 provider（草稿）。

    当前只能可靠提供 company.name。
    PE/PB/财务指标均无稳定 JSON 接口，返回 null。

    **此 provider 暂未接入 FundamentalDataService，仅供探索/记录。**
    接入前需等待确认。
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.trust_env = False

    def get_company_profile(self, market: str, symbol: str) -> dict:
        """
        获取公司基础信息。

        当前实现：
        - name: 从 hq.sinajs.cn 行情接口获取（可靠）
        - industry: 无稳定接口 → null
        - business_summary: 无稳定接口 → null

        Returns:
            {
                "company": {"name": str|None, "industry": None, "business_summary": None},
                "data_sources": {"company.name": "sina_hq"} (if name is available)
            }
        """
        result: dict = {
            "company": {"name": None, "industry": None, "business_summary": None},
            "data_sources": {},
        }

        try:
            sina_sym = _to_sina_symbol(market, symbol)
        except ValueError as exc:
            log.warning("SinaFundamentalProvider: %s", exc)
            return result

        url = _HQ_URL.format(sina_sym)
        try:
            r = self._session.get(url, headers=_HEADERS, timeout=8)
            r.raise_for_status()
            text = r.content.decode("gb18030", errors="replace")
        except Exception as exc:
            log.warning("SinaFundamentalProvider.get_company_profile 请求失败 [%s/%s]: %s",
                        market, symbol, exc)
            return result

        m = re.search(r'"([^"]*)"', text)
        if not m:
            return result

        raw = m.group(1).strip()
        if not raw:
            return result

        fields = raw.split(",")

        if market.upper() == "CN" and len(fields) >= 1:
            name = _safe_str(fields, 0)
            if name:
                result["company"]["name"] = name
                result["data_sources"]["company.name"] = "sina_hq"

        elif market.upper() == "HK" and len(fields) >= 2:
            # HK: [0]=英文名, [1]=中文名
            name = _safe_str(fields, 1) or _safe_str(fields, 0)
            if name:
                result["company"]["name"] = name
                result["data_sources"]["company.name"] = "sina_hq_hk"

        return result

    def get_valuation(self, market: str, symbol: str) -> dict:
        """
        获取估值数据。

        当前实现：
        - 新浪 hq.sinajs.cn 不提供 PE/PB/市值
        - 无稳定 JSON 估值接口
        - 全部返回 null

        Returns:
            {
                "valuation": {"pe": None, "pb": None, "market_cap": None,
                              "ps": None, "dividend_yield": None},
                "data_sources": {}
            }
        """
        log.debug(
            "SinaFundamentalProvider.get_valuation: no stable JSON API, returning null "
            "[%s/%s]", market, symbol
        )
        return {
            "valuation": {
                "pe": None,
                "pb": None,
                "market_cap": None,
                "ps": None,
                "dividend_yield": None,
            },
            "data_sources": {},
        }
