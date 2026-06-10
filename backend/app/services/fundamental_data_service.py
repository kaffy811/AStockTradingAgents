"""
FundamentalDataService — 基本面快照，Phase 2。

Phase 2 新增数据覆盖（仅 CN A股）：
  profitability.roe            → stock_financial_abstract_ths "净资产收益率"      (%)
  profitability.gross_margin   → stock_financial_abstract_ths "销售毛利率"        (%)
  profitability.net_margin     → stock_financial_abstract_ths "销售净利率"        (%)
  growth.revenue_growth_yoy    → stock_financial_abstract_ths "营业总收入同比增长率" (%)
  growth.net_profit_growth_yoy → stock_financial_abstract_ths "净利润同比增长率"   (%)
  financial_health.debt_ratio  → stock_financial_abstract_ths "资产负债率"        (%)
  financial_health.operating_cashflow → stock_financial_cash_ths
                                       "*经营活动产生的现金流量净额"              (元 CNY)

Phase 2.1 数据覆盖（本轮新增）：
  CN: valuation.market_cap → AkShare spot_em "总市值"（元 CNY）
  CN: company.name fallback → AkShare spot_em → Sina quote → quote_optional
  yfinance: 降级为 CN market_cap optional fallback（AkShare 已填则跳过）
  HK yfinance: 已禁用（经常 429，无稳定 HK provider）

Phase 1 数据覆盖（保留）：
  CN: company.name → AkShare spot_em（备用：Sina quote → quote_optional）
      valuation.pe → AkShare spot_em "市盈率-动态"
      valuation.pb → AkShare spot_em "市净率"
      valuation.market_cap → AkShare spot_em "总市值"（备用：yfinance optional）
  HK: company.name → quote_optional（Tencent HK / AkShare HK）
      其余字段 → null

仍为 null 的字段（当前不覆盖）：
  company.industry, company.business_summary
  valuation.ps, valuation.dividend_yield
  HK 的所有 valuation/财报字段（无稳定数据源）

缓存策略（Phase 2 更新）：
  - TTL = 3600 秒（1 小时）：财报数据变化频率为季报级别，1 小时缓存合理。
  - stale fallback：有历史缓存时不崩溃，返回 data_quality.stale=true。
  - 任何情况下返回 HTTP 200 结构化 JSON，不抛 5xx。

降级规则：
  stock_financial_abstract_ths 失败
    → profitability / growth / financial_health.debt_ratio 全部 null
    → 写入 missing_fields + message，不中断
  stock_financial_cash_ths 失败
    → financial_health.operating_cashflow null
    → 写入 missing_fields + message，不中断
  两者互相独立，不互相阻塞。
"""

from __future__ import annotations

import copy
import logging
import time
from typing import Any

from app.data.providers.akshare_provider import AkShareStockDataProvider
from app.data.providers.fundamental_provider import fundamental_provider
from app.data.providers.sina_provider import SinaQuoteProvider
from app.data.providers.yfinance_provider import YFinanceStockDataProvider
from app.services.cache_service import cache_service
from app.services.stock_data_service import stock_data_service

log = logging.getLogger(__name__)

_FUNDAMENTALS_TTL: int = 3600       # 主缓存 TTL：1 小时（季报频率）
_FUNDAMENTALS_DEGRADED_TTL: int = 600  # 降级结果（stale / 数据缺失）短 TTL：10 分钟
_NEGATIVE_AKSHARE_TTL: int = 300    # AkShare 失败 negative cache：5 分钟
_NEGATIVE_YFINANCE_TTL: int = 600   # yfinance 429 negative cache：10 分钟

_SUPPORTED_MARKETS = {"CN", "HK"}

# ── 内部缓存（独立于 stock_cache_service）────────────────────────────────────

_cache: dict[str, tuple[Any, float]] = {}
_stale: dict[str, Any] = {}


def _cache_key(market: str, symbol: str) -> str:
    return f"fundamentals:{market.upper()}:{symbol}"


def _cache_get(key: str) -> tuple[Any, bool]:
    entry = _cache.get(key)
    if entry is None:
        return None, False
    value, expire_at = entry
    return (value, True) if time.monotonic() <= expire_at else (None, False)


def _cache_set(key: str, value: Any) -> None:
    payload = copy.deepcopy(value)
    _cache[key] = (payload, time.monotonic() + _FUNDAMENTALS_TTL)
    _stale[key] = payload


def _stale_get(key: str) -> tuple[Any, bool]:
    value = _stale.get(key)
    return (copy.deepcopy(value), True) if value is not None else (None, False)


# ── 快照骨架 ──────────────────────────────────────────────────────────────────

def _empty_snapshot(market: str, symbol: str) -> dict:
    return {
        "market": market,
        "symbol": symbol,
        "company": {
            "name":             None,
            "industry":         None,
            "business_summary": None,
        },
        "valuation": {
            "pe":              None,
            "pb":              None,
            "ps":              None,
            "market_cap":      None,
            "market_cap_unit": None,
            "dividend_yield":  None,
        },
        "profitability": {
            "roe":          None,
            "gross_margin": None,
            "net_margin":   None,
        },
        "growth": {
            "revenue_growth_yoy":    None,
            "net_profit_growth_yoy": None,
        },
        "financial_health": {
            "debt_ratio":         None,
            "operating_cashflow": None,
        },
        "data_quality": {
            "provider":       None,
            "data_sources":   {},
            "missing_fields": [],
            "stale":          False,
            "message":        None,
            "latest_report_date": None,   # 最新财报期，Phase 2 新增
        },
    }


# ── missing_fields 计算 ───────────────────────────────────────────────────────

# Phase 2 预期有值的字段（拿不到才列入 missing）
_CN_EXPECTED = frozenset({
    "company.name",
    "valuation.pe",
    "valuation.pb",
    "valuation.market_cap",              # AkShare spot_em 总市值，Phase 2.1 新增
    "profitability.roe",
    "profitability.gross_margin",
    "profitability.net_margin",
    "growth.revenue_growth_yoy",
    "growth.net_profit_growth_yoy",
    "financial_health.debt_ratio",
    "financial_health.operating_cashflow",
})

# 明确不覆盖的字段（不列入 missing，避免误导）
_PLANNED_NULL = frozenset({
    "company.industry",
    "company.business_summary",
    "valuation.ps",
    "valuation.dividend_yield",
    # valuation.market_cap 已移至 _CN_EXPECTED；yfinance 为 optional fallback
})


def _calc_missing(snapshot: dict, sources: dict, market: str) -> list[str]:
    """
    计算未能获取的 Phase 2 字段列表。
    只检查当前 market 预期有值的字段，不包含 PLANNED_NULL。
    """
    missing: list[str] = []

    if market == "CN":
        checks = [
            ("company.name",                    snapshot["company"]["name"]),
            ("valuation.pe",                    snapshot["valuation"]["pe"]),
            ("valuation.pb",                    snapshot["valuation"]["pb"]),
            ("valuation.market_cap",            snapshot["valuation"]["market_cap"]),
            ("profitability.roe",               snapshot["profitability"]["roe"]),
            ("profitability.gross_margin",       snapshot["profitability"]["gross_margin"]),
            ("profitability.net_margin",         snapshot["profitability"]["net_margin"]),
            ("growth.revenue_growth_yoy",        snapshot["growth"]["revenue_growth_yoy"]),
            ("growth.net_profit_growth_yoy",     snapshot["growth"]["net_profit_growth_yoy"]),
            ("financial_health.debt_ratio",      snapshot["financial_health"]["debt_ratio"]),
            ("financial_health.operating_cashflow", snapshot["financial_health"]["operating_cashflow"]),
        ]
    else:  # HK：valuation 暂无稳定数据源，均列入 missing
        checks = [
            ("company.name",          snapshot["company"]["name"]),
            ("valuation.pe",          snapshot["valuation"]["pe"]),
            ("valuation.pb",          snapshot["valuation"]["pb"]),
            ("valuation.market_cap",  snapshot["valuation"]["market_cap"]),
            ("company.industry",      snapshot["company"]["industry"]),
            ("company.business_summary", snapshot["company"]["business_summary"]),
        ]

    for field_path, value in checks:
        if value is None:
            missing.append(field_path)

    return missing


# ── message 拼接辅助 ──────────────────────────────────────────────────────────

def _append_msg(dq: dict, text: str) -> None:
    prev = dq.get("message") or ""
    dq["message"] = (prev + " " + text).strip()


# ── CN name Sina fallback ─────────────────────────────────────────────────────

def _fill_cn_name_with_sina_if_missing(
    snapshot: dict, symbol: str, dq: dict, sources: dict
) -> None:
    """
    若 company.name 仍为 None，尝试 SinaQuoteProvider 补充。

    - Sina 只用于 company.name，不补 pe/pb/market_cap。
    - Sina 失败不中断后续逻辑，只追加 message。
    - 成功时 data_sources["company.name"] = "sina_quote"。
    """
    if snapshot["company"]["name"] is not None:
        return

    try:
        q = SinaQuoteProvider().get_quote("CN", symbol)
        name = q.get("name") if q else None
        if name:
            snapshot["company"]["name"] = name
            sources["company.name"] = "sina_quote"
            if dq.get("provider") is None:
                dq["provider"] = "sina_quote"
            log.info("fundamentals Sina name OK [CN/%s]: %s", symbol, name)
    except Exception as exc:
        log.warning("fundamentals Sina quote failed [CN/%s]: %s", symbol, exc)
        _append_msg(dq, f"Sina name fallback failed ({exc}).")


# ── 主服务类 ──────────────────────────────────────────────────────────────────

class FundamentalDataService:
    """
    基本面快照 Service — Phase 2。

    对外唯一入口：get_fundamentals(market, symbol) → dict
    任何情况下都不抛出异常，拿不到的字段返回 null + missing_fields。
    """

    def __init__(self) -> None:
        self._akshare  = AkShareStockDataProvider()
        self._yfinance = YFinanceStockDataProvider()

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def get_fundamentals(self, market: str, symbol: str) -> dict:
        market = market.upper()

        if market not in _SUPPORTED_MARKETS:
            snap = _empty_snapshot(market, symbol)
            snap["data_quality"]["message"] = (
                f"不支持的市场 '{market}'，只支持 CN / HK。"
            )
            snap["data_quality"]["missing_fields"] = ["company.name"]
            return snap

        # ── 第一层：Redis 缓存（跨进程/实例共享，TTL 由写入时决定）────────────
        redis_key = f"fundamental:{market}:{symbol}"
        redis_hit = cache_service.sync_get_json(redis_key)
        if redis_hit is not None:
            log.info("fundamentals Redis HIT [%s/%s]", market, symbol)
            return redis_hit

        # ── 第二层：进程内内存缓存（TTL 60 分钟）────────────────────────────────
        mem_key = _cache_key(market, symbol)
        cached, hit = _cache_get(mem_key)
        if hit:
            log.debug("fundamentals memory cache HIT [%s/%s]", market, symbol)
            # 回写 Redis（避免冷启动后跨进程缓存空缺）
            cache_service.sync_set_json(redis_key, cached, _FUNDAMENTALS_TTL)
            return cached

        snapshot = _empty_snapshot(market, symbol)

        if market == "CN":
            has_data = self._fill_cn(symbol, snapshot)
        else:
            has_data = self._fill_hk(symbol, snapshot)

        if has_data:
            _cache_set(mem_key, snapshot)
            cache_service.sync_set_json(redis_key, snapshot, _FUNDAMENTALS_TTL)
            log.info("fundamentals written to memory+Redis [%s/%s]", market, symbol)
            return snapshot

        # 无任何数据 → 尝试 stale
        stale_val, found = _stale_get(mem_key)
        if found:
            log.warning("fundamentals 所有源失败 [%s/%s]，返回 stale 缓存。", market, symbol)
            stale_val["data_quality"]["stale"] = True
            _append_msg(stale_val["data_quality"], "实时数据源暂不可用，当前展示最近一次历史缓存。")
            # stale 结果写入 Redis 短 TTL，避免反复打上游
            cache_service.sync_set_json(redis_key, stale_val, _FUNDAMENTALS_DEGRADED_TTL)
            return stale_val

        log.error("fundamentals 所有源失败且无历史缓存 [%s/%s]", market, symbol)
        return snapshot

    # ── CN 填充（Phase 2）────────────────────────────────────────────────────

    def _fill_cn(self, symbol: str, snapshot: dict) -> bool:
        dq      = snapshot["data_quality"]
        sources: dict[str, str] = {}

        # ── Step 1: AkShare CN quote → name / pe / pb / market_cap ─────────────
        _neg_akshare = f"negative:akshare_quote:CN:{symbol}"
        if cache_service.sync_exists(_neg_akshare):
            log.info("fundamentals skip AkShare quote [CN/%s] due to negative cache", symbol)
            _append_msg(dq, "AkShare spot_em 暂时跳过（negative cache）。")
        else:
            try:
                data = self._akshare.get_quote("CN", symbol)
                if data.get("name"):
                    snapshot["company"]["name"] = data["name"]
                    sources["company.name"] = "akshare_spot_em"
                if data.get("pe") is not None:
                    snapshot["valuation"]["pe"] = data["pe"]
                    sources["valuation.pe"] = "akshare_spot_em"
                if data.get("pb") is not None:
                    snapshot["valuation"]["pb"] = data["pb"]
                    sources["valuation.pb"] = "akshare_spot_em"
                # market_cap: AkShare spot_em 返回 "总市值"（元），_QUOTE_CN_COLS 已映射
                mc_raw = data.get("market_cap")
                if mc_raw is not None:
                    try:
                        mc_float = float(mc_raw)
                        if mc_float > 0:
                            snapshot["valuation"]["market_cap"] = mc_float
                            snapshot["valuation"]["market_cap_unit"] = "CNY"
                            sources["valuation.market_cap"] = "akshare_spot_em"
                    except (TypeError, ValueError):
                        pass
                dq["provider"] = "akshare"
                log.info(
                    "fundamentals quote OK [CN/%s]: name=%s pe=%s pb=%s mc=%s",
                    symbol, data.get("name"), data.get("pe"), data.get("pb"), mc_raw,
                )
            except Exception as exc:
                exc_str = str(exc)
                log.warning("fundamentals AkShare quote failed [CN/%s]: %s", symbol, exc)
                _append_msg(
                    dq,
                    f"AkShare spot_em unavailable ({exc}); "
                    "valuation.pe/pb unavailable. Trying Sina/quote_optional for name.",
                )
                # 写入 negative cache（RemoteDisconnected / ConnectionError 类错误）
                if any(kw in exc_str for kw in (
                    "RemoteDisconnected", "Connection aborted", "ConnectionError",
                    "ConnectionReset", "Errno 104", "Errno 111",
                )):
                    cache_service.sync_set_json(_neg_akshare, 1, _NEGATIVE_AKSHARE_TTL)
                    log.info(
                        "fundamentals AkShare negative cache set [CN/%s] ttl=%ds",
                        symbol, _NEGATIVE_AKSHARE_TTL,
                    )

        # ── Step 1b: name fallback chain（Sina → quote_optional）────────────
        # _fill_cn_name_with_sina_if_missing 是 no-op 当 name 已填
        _fill_cn_name_with_sina_if_missing(snapshot, symbol, dq, sources)

        if snapshot["company"]["name"] is None:
            try:
                q = stock_data_service.get_quote_optional("CN", symbol)
                if q and q.get("name"):
                    snapshot["company"]["name"] = q["name"]
                    sources["company.name"] = "quote_optional"
                    if dq.get("provider") is None:
                        dq["provider"] = "quote_optional"
            except Exception as qe:
                log.warning("fundamentals quote_optional failed [CN/%s]: %s", symbol, qe)

        # ── Step 2: AkShareFundamentalProvider → 财报摘要 ────────────────────
        self._fill_cn_financial_abstract(symbol, snapshot, sources)

        # ── Step 3: AkShareFundamentalProvider → 现金流 ──────────────────────
        self._fill_cn_cash_flow(symbol, snapshot, sources)

        # ── Step 4: yfinance → market_cap（optional）─────────────────────────
        self._try_market_cap(symbol, "CN", snapshot, sources)

        # ── Step 5: 统计 ──────────────────────────────────────────────────────
        dq["data_sources"]   = sources
        dq["missing_fields"] = _calc_missing(snapshot, sources, "CN")

        return bool(sources)

    def _fill_cn_financial_abstract(
        self, symbol: str, snapshot: dict, sources: dict
    ) -> None:
        """
        从 stock_financial_abstract_ths 填充：
        roe / gross_margin / net_margin / revenue_growth_yoy /
        net_profit_growth_yoy / debt_ratio
        """
        dq = snapshot["data_quality"]

        _FIELD_MAP = {
            "roe":                  ("profitability", "roe"),
            "gross_margin":         ("profitability", "gross_margin"),
            "net_margin":           ("profitability", "net_margin"),
            "revenue_growth_yoy":   ("growth",        "revenue_growth_yoy"),
            "net_profit_growth_yoy":("growth",        "net_profit_growth_yoy"),
            "debt_ratio":           ("financial_health", "debt_ratio"),
        }

        try:
            abstract = fundamental_provider.get_financial_abstract(symbol)
        except Exception as exc:
            log.warning("financial_abstract failed [CN/%s]: %s", symbol, exc)
            _append_msg(dq, f"财报摘要不可用（{exc}）。")
            return

        if abstract is None:
            _append_msg(dq, "财报摘要返回空。")
            return

        # 记录最新报告期
        if abstract.get("report_date"):
            dq["latest_report_date"] = abstract["report_date"]

        for field, (section, key) in _FIELD_MAP.items():
            val = abstract.get(field)
            if val is not None:
                snapshot[section][key] = val
                sources[f"{section}.{key}"] = "akshare_ths_financial_abstract"

    def _fill_cn_cash_flow(
        self, symbol: str, snapshot: dict, sources: dict
    ) -> None:
        """从 stock_financial_cash_ths 填充 operating_cashflow（元）。"""
        dq = snapshot["data_quality"]
        try:
            cf = fundamental_provider.get_cash_flow(symbol)
        except Exception as exc:
            log.warning("cash_flow failed [CN/%s]: %s", symbol, exc)
            _append_msg(dq, f"现金流数据不可用（{exc}）。")
            return

        if cf is None:
            _append_msg(dq, "现金流数据返回空。")
            return

        ocf = cf.get("operating_cashflow")
        if ocf is not None:
            snapshot["financial_health"]["operating_cashflow"] = ocf
            sources["financial_health.operating_cashflow"] = "akshare_ths_cash_flow"
            # 如果摘要里没记录报告期，用现金流的
            if not dq.get("latest_report_date") and cf.get("report_date"):
                dq["latest_report_date"] = cf["report_date"]

    # ── HK 填充（Phase 2 不扩展，维持 Phase 1）───────────────────────────────

    def _fill_hk(self, symbol: str, snapshot: dict) -> bool:
        dq      = snapshot["data_quality"]
        sources: dict[str, str] = {}

        try:
            q = stock_data_service.get_quote_optional("HK", symbol)
            if q and q.get("name"):
                snapshot["company"]["name"] = q["name"]
                sources["company.name"] = "quote_optional"
                dq["provider"] = "quote_optional"
        except Exception as exc:
            log.warning("fundamentals HK name failed [%s]: %s", symbol, exc)

        # yfinance 已禁用：在 HK 不稳定且经常 429，不调用。
        # valuation.pe / pb / market_cap 本阶段无稳定 HK 数据源，保持 null。

        dq["data_sources"]   = sources
        dq["missing_fields"] = _calc_missing(snapshot, sources, "HK")
        _append_msg(
            dq,
            "HK valuation/fundamentals provider not configured; "
            "yfinance disabled to avoid rate limits. "
            "pe/pb/market_cap/industry remain null.",
        )
        return bool(sources)

    # ── yfinance market_cap（optional）───────────────────────────────────────

    def _try_market_cap(
        self, symbol: str, market: str, snapshot: dict, sources: dict
    ) -> None:
        """
        yfinance market_cap — optional CN fallback only.

        跳过条件：
        - market_cap 已从 AkShare spot_em 填充（避免无谓 yfinance 调用）；
        - HK 不调用（yfinance HK 经常 429，已在 _fill_hk 禁用）。
        """
        if snapshot["valuation"]["market_cap"] is not None:
            log.debug(
                "fundamentals market_cap already filled [%s/%s], skipping yfinance",
                market, symbol,
            )
            return

        _neg_yf = f"negative:yfinance_quote:{market}:{symbol}"
        if cache_service.sync_exists(_neg_yf):
            log.info(
                "fundamentals skip yfinance [%s/%s] due to negative cache", market, symbol
            )
            return

        try:
            yf_data = self._yfinance.get_quote(market, symbol)
            mc = yf_data.get("market_cap")
            if mc is not None and mc > 0:
                snapshot["valuation"]["market_cap"]      = mc
                snapshot["valuation"]["market_cap_unit"] = "CNY" if market == "CN" else "HKD"
                sources["valuation.market_cap"] = "yfinance_fast_info"
                log.info("fundamentals yfinance market_cap OK [%s/%s]: %s", market, symbol, mc)
        except Exception as exc:
            exc_str = str(exc)
            log.warning("fundamentals yfinance market_cap failed [%s/%s]: %s", market, symbol, exc)
            # Too Many Requests (429) → 写入 negative cache
            if any(kw in exc_str for kw in ("Too Many Requests", "429", "rate limit", "Rate limit")):
                cache_service.sync_set_json(_neg_yf, 1, _NEGATIVE_YFINANCE_TTL)
                log.info(
                    "fundamentals yfinance negative cache set [%s/%s] ttl=%ds",
                    market, symbol, _NEGATIVE_YFINANCE_TTL,
                )


# ── 模块级单例 ────────────────────────────────────────────────────────────────

fundamental_data_service = FundamentalDataService()
