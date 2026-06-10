"""
StockDataService — 股票数据统一入口，带多数据源 fallback 和内存缓存。

Provider 顺序
─────────────
CN A股 quote：
  1. EastmoneyDirectProvider  (直连 push2.eastmoney.com, trust_env=False)
  2. SinaQuoteProvider        (hq.sinajs.cn, gb18030)
  3. TencentQuoteProvider(CN) (qt.gtimg.cn, gb18030)
  4. stale cache → HTTP 200 + stale=true
  5. 无缓存 → HTTP 503

HK 港股 quote：
  1. TencentQuoteProvider(HK) (qt.gtimg.cn/q=hk00700)
  2. AkShare 实时 quote
  3. stale cache → HTTP 200 + stale=true
  4. 无缓存 → HTTP 503
  （本轮已移除 yfinance，避免 Yahoo 429 拖慢接口）

CN A股 kline：
  1. EastmoneyKlineProvider (push2his.eastmoney.com, trust_env=False)
  2. TencentKlineProvider   (web.ifzq.gtimg.cn, 直连，已验证可用)
  3. AkShare kline
  4. stale cache → HTTP 200 + stale=true
  5. 无缓存 → HTTP 503
  （本轮已移除 yfinance）

HK 港股 kline：
  1. TencentKlineProvider   (web.ifzq.gtimg.cn/q=hk00700，直连，已验证可用)
  2. AkShare kline
  3. stale cache → HTTP 200 + stale=true
  4. 无缓存 → HTTP 503
  （本轮已移除 yfinance）

规则：
  - 有 stale cache 时一律返回 HTTP 200，不返回 502 / 503。
  - 完全无缓存时才返回 HTTP 503，不再返回 HTTP 502。
  - Agent / Router 只调用本 Service，不直接 import Provider。
  - get_quote() 返回 QuoteResult；get_kline() 返回 KlineResult。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.data.providers.akshare_provider import AkShareStockDataProvider
from app.data.providers.baostock_provider import BaoStockDataProvider
from app.data.providers.eastmoney_provider import EastmoneyDirectProvider, EastmoneyKlineProvider
from app.data.providers.sina_provider import SinaQuoteProvider
from app.data.providers.tencent_provider import TencentQuoteProvider, TencentKlineProvider
from app.data.providers.yfinance_provider import YFinanceStockDataProvider
from app.data.providers.base import BaseStockDataProvider
from app.services import stock_cache_service as cache

log = logging.getLogger(__name__)

_SUPPORTED_MARKETS = {"CN", "HK"}


# ── 返回结构 ──────────────────────────────────────────────────────────────────

@dataclass
class QuoteResult:
    """
    get_quote() 统一返回结构。
    Router 读取 http_status 决定响应码，业务逻辑不扩散到 Router。
    """
    data: dict
    provider: str
    cached: bool = False
    stale: bool = False
    fallback_chain: list[dict] = field(default_factory=list)
    message: str | None = None
    http_status: int = 200


@dataclass
class KlineResult:
    """
    get_kline() 统一返回结构（与 QuoteResult 对称）。
    stale=true 表示返回的是历史缓存；http_status=503 表示完全无数据。
    """
    bars: list[dict]
    provider: str
    cached: bool = False
    stale: bool = False
    fallback_chain: list[dict] = field(default_factory=list)
    message: str | None = None
    http_status: int = 200


# ── 参数校验 ──────────────────────────────────────────────────────────────────

def _validate(market: str, symbol: str) -> str:
    m = market.upper()
    if m not in _SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market '{market}'. Use CN or HK.")
    if not symbol:
        raise ValueError("symbol 不能为空。")
    return m


# ── kline 最后一条 → quote 构造 ───────────────────────────────────────────────

def _quote_from_kline(symbol: str, bar: dict) -> dict:
    """用最后一条 K 线构造简化 quote，保证 quote 不因实时接口失败而中断分析。"""
    return {
        "symbol":      symbol,
        "name":        None,
        "price":       bar.get("close"),   # 与实时 quote 字段名一致
        "open":        bar.get("open"),
        "high":        bar.get("high"),
        "low":         bar.get("low"),
        "prev_close":  None,
        "volume":      bar.get("volume"),
        "amount":      bar.get("amount"),
        "change":      None,
        "change_pct":  None,
        "trade_date":  bar.get("date"),
        "source_note": "quote_from_kline",
    }


# ── StockDataService ──────────────────────────────────────────────────────────

class StockDataService:

    def __init__(self) -> None:
        # CN A股 quote 专用（直连，不走 akshare）
        self._eastmoney       = EastmoneyDirectProvider()
        self._sina            = SinaQuoteProvider()
        self._tencent_quote   = TencentQuoteProvider()    # CN + HK quote

        # Kline providers
        self._eastmoney_kline = EastmoneyKlineProvider()  # CN kline (trust_env=False)
        self._tencent_kline   = TencentKlineProvider()    # CN + HK kline (直连)

        # 通用 providers（作为备用）
        self._akshare:  BaseStockDataProvider = AkShareStockDataProvider()
        self._yfinance: BaseStockDataProvider = YFinanceStockDataProvider()
        self._baostock: BaseStockDataProvider = BaoStockDataProvider()   # stub

    # =========================================================================
    # Quote
    # =========================================================================

    def get_quote(self, market: str, symbol: str) -> QuoteResult:
        """
        获取最新 quote，返回 QuoteResult（含 http_status）。

        CN fallback: Eastmoney → Sina → Tencent(CN) → stale → 503
        HK fallback: Tencent(HK) → AkShare → stale → 503

        Raises:
            ValueError – 参数非法（→ HTTP 400）
        """
        market = _validate(market, symbol)

        # 主缓存命中（TTL 内）
        cached_payload, hit = cache.get_quote_cache(market, symbol)
        if hit:
            log.debug("Cache HIT quote [%s/%s]", market, symbol)
            return QuoteResult(
                data=cached_payload["data"],
                provider=cached_payload["provider"],
                cached=True,
                fallback_chain=cached_payload.get("fallback_chain", []),
            )

        if market == "CN":
            return self._get_quote_cn(symbol)
        return self._get_quote_hk(symbol)

    # ── CN quote chain ────────────────────────────────────────────────────────

    def _get_quote_cn(self, symbol: str) -> QuoteResult:
        """CN A股 quote: Eastmoney → Sina → Tencent → stale → 503"""
        errors: list[str] = []
        fallback_chain: list[dict] = []

        providers = [
            (self._eastmoney,     "eastmoney"),
            (self._sina,          "sina"),
            (self._tencent_quote, "tencent"),
        ]

        for provider, name in providers:
            try:
                data = provider.get_quote("CN", symbol)
                fallback_chain.append({"source": name, "status": "ok"})
                cache.set_quote_cache("CN", symbol, data, name, fallback_chain)
                return QuoteResult(data=data, provider=name, fallback_chain=fallback_chain)
            except Exception as exc:
                msg = str(exc)
                log.warning("%s quote failed [CN/%s]: %s", name, symbol, msg)
                errors.append(f"{name}: {msg}")
                fallback_chain.append({"source": name, "error": msg})

        return self._stale_or_503_quote("CN", symbol, errors, fallback_chain)

    # ── HK quote chain ────────────────────────────────────────────────────────

    def _get_quote_hk(self, symbol: str) -> QuoteResult:
        """HK 港股 quote: Tencent(HK) → AkShare → stale → 503"""
        errors: list[str] = []
        fallback_chain: list[dict] = []

        # 1. Tencent HK（主数据源，直连，不走 yfinance）
        try:
            data = self._tencent_quote.get_quote("HK", symbol)
            fallback_chain.append({"source": "tencent_hk", "status": "ok"})
            cache.set_quote_cache("HK", symbol, data, "tencent_hk", fallback_chain)
            return QuoteResult(data=data, provider="tencent_hk", fallback_chain=fallback_chain)
        except Exception as exc:
            msg = str(exc)
            log.warning("tencent_hk quote failed [HK/%s]: %s", symbol, msg)
            errors.append(f"tencent_hk: {msg}")
            fallback_chain.append({"source": "tencent_hk", "error": msg})

        # 2. AkShare 实时 quote（备用）
        try:
            data = self._akshare.get_quote("HK", symbol)
            fallback_chain.append({"source": "akshare", "status": "ok"})
            cache.set_quote_cache("HK", symbol, data, "akshare", fallback_chain)
            return QuoteResult(data=data, provider="akshare", fallback_chain=fallback_chain)
        except Exception as exc:
            msg = str(exc)
            log.warning("akshare quote failed [HK/%s]: %s", symbol, msg)
            errors.append(f"akshare: {msg}")
            fallback_chain.append({"source": "akshare", "error": msg})

        return self._stale_or_503_quote("HK", symbol, errors, fallback_chain)

    # ── quote stale 兜底 ──────────────────────────────────────────────────────

    def _stale_or_503_quote(
        self,
        market: str,
        symbol: str,
        errors: list[str],
        fallback_chain: list[dict],
    ) -> QuoteResult:
        stale_payload, found = cache.get_quote_stale(market, symbol)
        if found:
            log.warning("所有实时 quote 源失败 [%s/%s]，返回 stale 缓存。", market, symbol)
            return QuoteResult(
                data=stale_payload["data"],
                provider=stale_payload.get("provider", "cache"),
                cached=True,
                stale=True,
                fallback_chain=fallback_chain + [{"source": "stale_cache", "status": "ok"}],
                message="实时行情源暂时不可用，当前展示最近一次缓存数据",
                http_status=200,
            )

        detail = "\n".join(f"  - {e}" for e in errors)
        log.error("所有 quote 源均失败且无任何缓存 [%s/%s]", market, symbol)
        return QuoteResult(
            data={},
            provider="none",
            fallback_chain=fallback_chain + [{"source": "stale_cache", "status": "no data"}],
            message=f"所有实时行情源均不可用，且无历史缓存数据。\n{detail}",
            http_status=503,
        )

    # =========================================================================
    # Kline
    # =========================================================================

    def get_kline(
        self,
        market: str,
        symbol: str,
        period: str = "daily",
        adjust: str = "",
        limit: int = 120,
    ) -> KlineResult:
        """
        获取 OHLCV K线数据，返回 KlineResult（含 http_status）。

        CN fallback: EastmoneyKline → AkShare → stale → 503
        HK fallback: AkShare → stale → 503

        Raises:
            ValueError – 参数非法（→ HTTP 400）
        """
        market = _validate(market, symbol)

        # 主缓存命中（TTL 内）
        cached_payload, hit = cache.get_kline_cache(market, symbol, period, adjust, limit)
        if hit:
            log.debug("Cache HIT kline [%s/%s %s %s limit=%d]", market, symbol, period, adjust, limit)
            return KlineResult(
                bars=cached_payload["bars"],
                provider=cached_payload["provider"],
                cached=True,
                fallback_chain=cached_payload.get("fallback_chain", []),
            )

        if market == "CN":
            return self._get_kline_cn(symbol, period, adjust, limit)
        return self._get_kline_hk(symbol, period, adjust, limit)

    # ── CN kline chain ────────────────────────────────────────────────────────

    def _get_kline_cn(
        self, symbol: str, period: str, adjust: str, limit: int
    ) -> KlineResult:
        """CN A股 kline: EastmoneyKline → TencentKline → AkShare → stale → 503"""
        errors: list[str] = []
        fallback_chain: list[dict] = []

        # 1. EastmoneyKline（主，直连，trust_env=False）
        try:
            bars = self._eastmoney_kline.get_kline("CN", symbol, period, adjust, limit)
            fallback_chain.append({"source": "eastmoney_kline", "status": "ok"})
            cache.set_kline_cache("CN", symbol, period, adjust, limit, bars, "eastmoney_kline", fallback_chain)
            return KlineResult(bars=bars, provider="eastmoney_kline", fallback_chain=fallback_chain)
        except Exception as exc:
            msg = str(exc)
            log.warning("EastmoneyKline failed [CN/%s]: %s", symbol, msg)
            errors.append(f"eastmoney_kline: {msg}")
            fallback_chain.append({"source": "eastmoney_kline", "error": msg})

        # 2. TencentKline（直连，已验证可用）
        try:
            bars = self._tencent_kline.get_kline("CN", symbol, period, adjust, limit)
            fallback_chain.append({"source": "tencent_kline", "status": "ok"})
            cache.set_kline_cache("CN", symbol, period, adjust, limit, bars, "tencent_kline", fallback_chain)
            return KlineResult(bars=bars, provider="tencent_kline", fallback_chain=fallback_chain)
        except Exception as exc:
            msg = str(exc)
            log.warning("TencentKline failed [CN/%s]: %s", symbol, msg)
            errors.append(f"tencent_kline: {msg}")
            fallback_chain.append({"source": "tencent_kline", "error": msg})

        # 3. AkShare（备用）
        try:
            bars = self._akshare.get_kline("CN", symbol, period, adjust, limit)
            fallback_chain.append({"source": "akshare", "status": "ok"})
            cache.set_kline_cache("CN", symbol, period, adjust, limit, bars, "akshare", fallback_chain)
            return KlineResult(bars=bars, provider="akshare", fallback_chain=fallback_chain)
        except Exception as exc:
            msg = str(exc)
            log.warning("AkShare kline failed [CN/%s]: %s", symbol, msg)
            errors.append(f"akshare: {msg}")
            fallback_chain.append({"source": "akshare", "error": msg})

        return self._stale_or_503_kline("CN", symbol, period, adjust, limit, errors, fallback_chain)

    # ── HK kline chain ────────────────────────────────────────────────────────

    def _get_kline_hk(
        self, symbol: str, period: str, adjust: str, limit: int
    ) -> KlineResult:
        """HK 港股 kline: TencentKline → AkShare → stale → 503"""
        errors: list[str] = []
        fallback_chain: list[dict] = []

        # 1. TencentKline HK（直连，已验证可用）
        try:
            bars = self._tencent_kline.get_kline("HK", symbol, period, adjust, limit)
            fallback_chain.append({"source": "tencent_kline", "status": "ok"})
            cache.set_kline_cache("HK", symbol, period, adjust, limit, bars, "tencent_kline", fallback_chain)
            return KlineResult(bars=bars, provider="tencent_kline", fallback_chain=fallback_chain)
        except Exception as exc:
            msg = str(exc)
            log.warning("TencentKline failed [HK/%s]: %s", symbol, msg)
            errors.append(f"tencent_kline: {msg}")
            fallback_chain.append({"source": "tencent_kline", "error": msg})

        # 2. AkShare（备用）
        try:
            bars = self._akshare.get_kline("HK", symbol, period, adjust, limit)
            fallback_chain.append({"source": "akshare", "status": "ok"})
            cache.set_kline_cache("HK", symbol, period, adjust, limit, bars, "akshare", fallback_chain)
            return KlineResult(bars=bars, provider="akshare", fallback_chain=fallback_chain)
        except Exception as exc:
            msg = str(exc)
            log.warning("AkShare kline failed [HK/%s]: %s", symbol, msg)
            errors.append(f"akshare: {msg}")
            fallback_chain.append({"source": "akshare", "error": msg})

        return self._stale_or_503_kline("HK", symbol, period, adjust, limit, errors, fallback_chain)

    # ── kline stale 兜底 ──────────────────────────────────────────────────────

    def _stale_or_503_kline(
        self,
        market: str,
        symbol: str,
        period: str,
        adjust: str,
        limit: int,
        errors: list[str],
        fallback_chain: list[dict],
    ) -> KlineResult:
        stale_payload, found = cache.get_kline_stale(market, symbol, period, adjust, limit)
        if found:
            log.warning("所有实时 kline 源失败 [%s/%s]，返回 stale 缓存。", market, symbol)
            return KlineResult(
                bars=stale_payload["bars"],
                provider=stale_payload.get("provider", "cache"),
                cached=True,
                stale=True,
                fallback_chain=fallback_chain + [{"source": "stale_cache", "status": "ok"}],
                message="实时K线源暂时不可用，当前展示最近一次缓存数据",
                http_status=200,
            )

        detail = "\n".join(f"  - {e}" for e in errors)
        log.error("所有 kline 源均失败且无任何缓存 [%s/%s]", market, symbol)
        return KlineResult(
            bars=[],
            provider="none",
            fallback_chain=fallback_chain + [{"source": "stale_cache", "status": "no data"}],
            message=f"所有K线数据源均不可用，且无历史缓存数据。\n{detail}",
            http_status=503,
        )

    # =========================================================================
    # Agent 友好接口
    # =========================================================================

    def get_kline_for_agent(
        self,
        market: str,
        symbol: str,
        limit: int = 120,
        period: str = "daily",
        adjust: str = "qfq",
    ) -> list[dict]:
        """
        Agent 专用：尽最大努力返回 K线，失败抛出清晰异常。
        默认：前复权（qfq），最近 120 根。
        """
        r = self.get_kline(market, symbol, period, adjust, limit)
        if r.http_status != 200 or not r.bars:
            raise RuntimeError(r.message or f"Kline unavailable for {market}/{symbol}")
        return r.bars

    def get_quote_optional(self, market: str, symbol: str) -> dict | None:
        """
        Agent 专用：quote 成功则返回 dict，失败静默返回 None。
        不会抛出异常，不会中断 Agent 分析流程。
        """
        try:
            r = self.get_quote(market, symbol)
            return r.data if r.http_status == 200 and r.data else None
        except Exception as exc:
            log.warning("get_quote_optional: failed [%s/%s]: %s", market, symbol, exc)
            return None

    def get_quote_for_agent(self, market: str, symbol: str) -> dict:
        """兼容旧接口：返回 quote data，503 时抛出 RuntimeError。"""
        r = self.get_quote(market, symbol)
        if r.http_status != 200:
            raise RuntimeError(r.message or f"Quote unavailable for {market}/{symbol}")
        return r.data


# ── 模块级单例 ────────────────────────────────────────────────────────────────

stock_data_service = StockDataService()
