"""
baostock_client.py — BaoStock 免费财务数据客户端（Phase 6A）

BaoStock 是免费 A 股数据源，无需付费订阅。
提供：季频财务指标、盈利能力、成长能力、偿债能力、营运能力、现金流量。
不提供：实时行情（用 AkShare）、港股/美股数据。

使用前安装: pip install baostock
"""
from __future__ import annotations

import asyncio
import importlib.util
import io
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# BaoStock's login/logout/query are not thread-safe and share global socket state.
# Serialize all sync calls with a module-level asyncio lock so concurrent async
# callers don't interleave login/logout → "Bad file descriptor".
_bs_lock: asyncio.Lock | None = None


def baostock_import_status() -> tuple[bool, str | None]:
    """Return whether the runtime can import BaoStock without importing it."""
    try:
        spec = importlib.util.find_spec("baostock")
    except (ImportError, ValueError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if spec is None:
        return False, "No module named 'baostock'"
    return True, None


def _get_bs_lock() -> asyncio.Lock:
    """Return (creating lazily) the per-event-loop BaoStock serialization lock."""
    global _bs_lock
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _bs_lock is None or (loop is not None and _bs_lock._loop is not loop):  # type: ignore[attr-defined]
        _bs_lock = asyncio.Lock()
    return _bs_lock


@contextmanager
def _suppress_bs_output():
    """Suppress BaoStock's noisy login/logout success prints to stdout/stderr."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

# ── BaoStock 季度序列（最近 8 个季度） ────────────────────────────────────────

def _recent_quarters(n: int = 8) -> list[tuple[int, int]]:
    """返回最近 n 个季度的 (year, quarter) 对，降序排列。"""
    import datetime
    today = datetime.date.today()
    year, month = today.year, today.month
    quarter = (month - 1) // 3 + 1
    result = []
    for _ in range(n):
        result.append((year, quarter))
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1
    return result


def _to_bs_code(ts_code: str) -> str:
    """
    将 Tushare 格式的股票代码转换为 BaoStock 格式。
    e.g. "600519.SH" → "sh.600519"
        "000725.SZ" → "sz.000725"
    """
    if "." not in ts_code:
        # 尝试猜测交易所
        if ts_code.startswith(("6", "5")):
            return f"sh.{ts_code}"
        return f"sz.{ts_code}"
    code, exchange = ts_code.split(".", 1)
    return f"{exchange.lower()}.{code}"


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in ("", "None", "null", "nan", "--"):
        return None
    try:
        f = float(s)
        return None if f != f else round(f, 6)
    except (TypeError, ValueError):
        return None


def _parse_rows(rs) -> list[dict]:
    """从 BaoStock ResultData 读取所有行，返回字典列表。"""
    rows = []
    fields = rs.fields if hasattr(rs, "fields") else []
    while rs.error_code == "0" and rs.next():
        row_data = rs.get_row_data()
        rows.append(dict(zip(fields, row_data)))
    return rows


# ── Phase 6T-E1: 批量历史获取 ────────────────────────────────────────────────
# BaoStock 季频财务数据自 2007 年起提供；早于 2007 的查询必然为空，直接跳过。
BAOSTOCK_FINANCIAL_DATA_START_YEAR = 2007

_BULK_TABLE_FNS = {
    "profit":    "query_profit_data",
    "growth":    "query_growth_data",
    "balance":   "query_balance_data",
    "operation": "query_operation_data",
    "cash_flow": "query_cash_flow_data",
    "dupont":    "query_dupont_data",
}

_BULK_TABLE_KEYS = tuple(_BULK_TABLE_FNS.keys())


def _bulk_fetch_years_worker(
    bs_code: str,
    year_quarters: list[tuple[int, int]],
) -> tuple[dict[int, dict[str, list[dict]]], int, dict[str, int]]:
    """
    子进程 worker：单次 login/logout 会话内查询分配到的 (year, quarter) 批。

    BaoStock python 模块为全局 socket（线程不安全），并发只能通过独立进程实现，
    每个 worker 进程有自己的会话。返回 ({year: {table: rows}}, calls_count)。
    """
    import baostock as bs  # 子进程内导入

    import io as _io
    import sys as _sys

    old_out, old_err = _sys.stdout, _sys.stderr
    _sys.stdout = _io.StringIO()
    _sys.stderr = _io.StringIO()
    try:
        bs.login()
    finally:
        _sys.stdout, _sys.stderr = old_out, old_err

    by_year: dict[int, dict[str, list[dict]]] = {}
    calls = 0
    calls_by_endpoint: dict[str, int] = {k: 0 for k in _BULK_TABLE_KEYS}
    try:
        for year, quarter in year_quarters:
            year_tables = by_year.setdefault(year, {k: [] for k in _BULK_TABLE_KEYS})
            for table_key, api_fn_name in _BULK_TABLE_FNS.items():
                api_fn = getattr(bs, api_fn_name, None)
                if api_fn is None:
                    continue
                calls += 1
                calls_by_endpoint[table_key] = calls_by_endpoint.get(table_key, 0) + 1
                try:
                    rs = api_fn(code=bs_code, year=year, quarter=quarter)
                    year_tables[table_key].extend(_parse_rows(rs))
                except Exception:
                    # 单期失败不影响其他期；缺失如实反映为空
                    continue
    finally:
        old_out, old_err = _sys.stdout, _sys.stderr
        _sys.stdout = _io.StringIO()
        _sys.stderr = _io.StringIO()
        try:
            bs.logout()
        finally:
            _sys.stdout, _sys.stderr = old_out, old_err
    return by_year, calls, calls_by_endpoint


def map_aggregate_raw(ts_code: str, raw_all: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """将 BaoStock 原始行映射为标准 aggregate 字段（与 get_*_data 输出一致）。"""
    def _map_profit(rows: list[dict]) -> list[dict]:
        return [
            {
                "ts_code": ts_code, "pub_date": r.get("pubDate"), "stat_date": r.get("statDate"),
                "roe_avg": _safe_float(r.get("roeAvg")), "net_margin": _safe_float(r.get("npMargin")),
                "gross_margin": _safe_float(r.get("gpMargin")), "net_profit": _safe_float(r.get("netProfit")),
                "eps_ttm": _safe_float(r.get("epsTTM")), "mb_revenue": _safe_float(r.get("MBRevenue")),
                "total_share": _safe_float(r.get("totalShare")), "liqa_share": _safe_float(r.get("liqaShare")),
            }
            for r in rows
        ]

    def _map_growth(rows: list[dict]) -> list[dict]:
        return [
            {
                "ts_code": ts_code, "pub_date": r.get("pubDate"), "stat_date": r.get("statDate"),
                "yoy_equity": _safe_float(r.get("YOYEquity")), "yoy_asset": _safe_float(r.get("YOYAsset")),
                "yoy_ni": _safe_float(r.get("YOYNI")), "yoy_eps": _safe_float(r.get("YOYEPSBasic")),
                "yoy_pni": _safe_float(r.get("YOYPNI")),
            }
            for r in rows
        ]

    def _map_balance(rows: list[dict]) -> list[dict]:
        return [
            {
                "ts_code": ts_code, "pub_date": r.get("pubDate"), "stat_date": r.get("statDate"),
                "current_ratio": _safe_float(r.get("currentRatio")), "quick_ratio": _safe_float(r.get("quickRatio")),
                "cash_ratio": _safe_float(r.get("cashRatio")), "yoy_liability": _safe_float(r.get("YOYLiability")),
                "liability_to_asset": _safe_float(r.get("liabilityToAsset")),
                "asset_to_equity": _safe_float(r.get("assetToEquity")),
            }
            for r in rows
        ]

    def _map_operation(rows: list[dict]) -> list[dict]:
        return [
            {
                "ts_code": ts_code, "pub_date": r.get("pubDate"), "stat_date": r.get("statDate"),
                "nr_turn_ratio": _safe_float(r.get("NRTurnRatio")), "nr_turn_days": _safe_float(r.get("NRTurnDays")),
                "inv_turn_ratio": _safe_float(r.get("INVTurnRatio")), "inv_turn_days": _safe_float(r.get("INVTurnDays")),
                "ca_turn_ratio": _safe_float(r.get("CATurnRatio")), "asset_turn_ratio": _safe_float(r.get("AssetTurnRatio")),
            }
            for r in rows
        ]

    def _map_cash_flow(rows: list[dict]) -> list[dict]:
        return [
            {
                "ts_code": ts_code, "pub_date": r.get("pubDate"), "stat_date": r.get("statDate"),
                "ca_to_asset": _safe_float(r.get("CAToAsset")), "nca_to_asset": _safe_float(r.get("NCAToAsset")),
                "tangible_to_asset": _safe_float(r.get("tangibleAssetToAsset")),
                "cfo_to_or": _safe_float(r.get("CFOToOR")), "cfo_to_np": _safe_float(r.get("CFOToNP")),
                "cfo_to_gr": _safe_float(r.get("CFOToGr")), "ebit_to_interest": _safe_float(r.get("ebitToInterest")),
            }
            for r in rows
        ]

    def _map_dupont(rows: list[dict]) -> list[dict]:
        return [
            {
                "ts_code": ts_code, "pub_date": r.get("pubDate"), "stat_date": r.get("statDate"),
                "dupont_roe": _safe_float(r.get("dupontROE")), "dupont_npi": _safe_float(r.get("dupontPnitoni")),
                "dupont_nitogr": _safe_float(r.get("dupontNitogr")), "dupont_tax": _safe_float(r.get("dupontTaxBurden")),
                "dupont_int": _safe_float(r.get("dupontIntburden")), "dupont_at": _safe_float(r.get("dupontAssetTurn")),
                "dupont_am": _safe_float(r.get("dupontAssetStoEquity")),
            }
            for r in rows
        ]

    return {
        "profit":    _map_profit(raw_all.get("profit", [])),
        "growth":    _map_growth(raw_all.get("growth", [])),
        "balance":   _map_balance(raw_all.get("balance", [])),
        "operation": _map_operation(raw_all.get("operation", [])),
        "cash_flow": _map_cash_flow(raw_all.get("cash_flow", [])),
        "dupont":    _map_dupont(raw_all.get("dupont", [])),
    }


# singleflight：同一 (ts_code, mode, range) 的并发请求只执行一次真实抓取
_bulk_singleflight_locks: dict[str, asyncio.Lock] = {}


class BaoStockClient:
    """
    BaoStock 免费财务数据客户端。

    所有方法均为 async，内部通过 asyncio.to_thread 调用同步 BaoStock API。
    所有异常均被捕获并返回空列表，不向调用方抛出。
    """

    # ── 登录/登出 ────────────────────────────────────────────────────────────

    async def login(self) -> None:
        """异步登录 BaoStock（每次 get_* 调用前自动执行）。"""
        try:
            import baostock as bs
            def _do_login():
                with _suppress_bs_output():
                    bs.login()
            await asyncio.to_thread(_do_login)
        except ImportError:
            log.warning("baostock 未安装，请执行: pip install baostock")
        except Exception as e:
            log.warning("BaoStock login 失败: %s", e)

    async def logout(self) -> None:
        """异步登出 BaoStock。"""
        try:
            import baostock as bs
            def _do_logout():
                with _suppress_bs_output():
                    bs.logout()
            await asyncio.to_thread(_do_logout)
        except Exception:
            pass

    # ── 内部：按季度拉取单表 ─────────────────────────────────────────────────

    async def _fetch_quarters(
        self,
        bs_code: str,
        api_fn_name: str,
        n_quarters: int = 8,
    ) -> list[dict]:
        """
        对最近 n_quarters 个季度依次调用 baostock.<api_fn_name>，
        汇总非空行返回。

        api_fn_name 例如: "query_profit_data", "query_growth_data"
        """
        try:
            import baostock as bs
        except ImportError:
            log.warning("baostock 未安装")
            return []

        api_fn = getattr(bs, api_fn_name, None)
        if api_fn is None:
            log.warning("BaoStock 无此接口: %s", api_fn_name)
            return []

        quarters = _recent_quarters(n_quarters)
        all_rows: list[dict] = []

        def _sync_fetch():
            with _suppress_bs_output():
                bs.login()
            rows = []
            for year, quarter in quarters:
                try:
                    rs = api_fn(code=bs_code, year=year, quarter=quarter)
                    rows.extend(_parse_rows(rs))
                except Exception as ex:
                    log.debug("BaoStock %s [%s %dQ%d] 失败: %s", api_fn_name, bs_code, year, quarter, ex)
            with _suppress_bs_output():
                bs.logout()
            return rows

        try:
            async with _get_bs_lock():
                all_rows = await asyncio.to_thread(_sync_fetch)
        except Exception as e:
            log.warning("BaoStock _fetch_quarters [%s/%s] 失败: %s", api_fn_name, bs_code, e)
        return all_rows

    # ── 公开接口 ─────────────────────────────────────────────────────────────

    async def get_profit_data(self, ts_code: str, n: int = 8) -> list[dict]:
        """
        盈利能力数据。

        BaoStock 字段：code, pubDate, statDate, roeAvg, npMargin, gpMargin,
                       netProfit, epsTTM, MBRevenue, totalShare, liqaShare
        """
        bs_code = _to_bs_code(ts_code)
        rows = await self._fetch_quarters(bs_code, "query_profit_data", n)
        result = []
        for r in rows:
            result.append({
                "ts_code":          ts_code,
                "pub_date":         r.get("pubDate"),
                "stat_date":        r.get("statDate"),
                "roe_avg":          _safe_float(r.get("roeAvg")),
                "net_margin":       _safe_float(r.get("npMargin")),
                "gross_margin":     _safe_float(r.get("gpMargin")),
                "net_profit":       _safe_float(r.get("netProfit")),
                "eps_ttm":          _safe_float(r.get("epsTTM")),
                "mb_revenue":       _safe_float(r.get("MBRevenue")),
                "total_share":      _safe_float(r.get("totalShare")),
                "liqa_share":       _safe_float(r.get("liqaShare")),
            })
        return result

    async def get_growth_data(self, ts_code: str, n: int = 8) -> list[dict]:
        """
        成长能力数据。

        BaoStock 字段：code, pubDate, statDate, YOYEquity, YOYAsset,
                       YOYNI, YOYEPSBasic, YOYPNI
        """
        bs_code = _to_bs_code(ts_code)
        rows = await self._fetch_quarters(bs_code, "query_growth_data", n)
        result = []
        for r in rows:
            result.append({
                "ts_code":      ts_code,
                "pub_date":     r.get("pubDate"),
                "stat_date":    r.get("statDate"),
                "yoy_equity":   _safe_float(r.get("YOYEquity")),
                "yoy_asset":    _safe_float(r.get("YOYAsset")),
                "yoy_ni":       _safe_float(r.get("YOYNI")),
                "yoy_eps":      _safe_float(r.get("YOYEPSBasic")),
                "yoy_pni":      _safe_float(r.get("YOYPNI")),
            })
        return result

    async def get_balance_data(self, ts_code: str, n: int = 8) -> list[dict]:
        """
        偿债能力数据。

        BaoStock 字段：code, pubDate, statDate, currentRatio, quickRatio,
                       cashRatio, YOYLiability, liabilityToAsset, assetToEquity
        """
        bs_code = _to_bs_code(ts_code)
        rows = await self._fetch_quarters(bs_code, "query_balance_data", n)
        result = []
        for r in rows:
            result.append({
                "ts_code":            ts_code,
                "pub_date":           r.get("pubDate"),
                "stat_date":          r.get("statDate"),
                "current_ratio":      _safe_float(r.get("currentRatio")),
                "quick_ratio":        _safe_float(r.get("quickRatio")),
                "cash_ratio":         _safe_float(r.get("cashRatio")),
                "yoy_liability":      _safe_float(r.get("YOYLiability")),
                "liability_to_asset": _safe_float(r.get("liabilityToAsset")),
                "asset_to_equity":    _safe_float(r.get("assetToEquity")),
            })
        return result

    async def get_operation_data(self, ts_code: str, n: int = 8) -> list[dict]:
        """
        营运能力数据。

        BaoStock 字段：code, pubDate, statDate, NRTurnRatio, NRTurnDays,
                       INVTurnRatio, INVTurnDays, CATurnRatio, AssetTurnRatio
        """
        bs_code = _to_bs_code(ts_code)
        rows = await self._fetch_quarters(bs_code, "query_operation_data", n)
        result = []
        for r in rows:
            result.append({
                "ts_code":          ts_code,
                "pub_date":         r.get("pubDate"),
                "stat_date":        r.get("statDate"),
                "nr_turn_ratio":    _safe_float(r.get("NRTurnRatio")),
                "nr_turn_days":     _safe_float(r.get("NRTurnDays")),
                "inv_turn_ratio":   _safe_float(r.get("INVTurnRatio")),
                "inv_turn_days":    _safe_float(r.get("INVTurnDays")),
                "ca_turn_ratio":    _safe_float(r.get("CATurnRatio")),
                "asset_turn_ratio": _safe_float(r.get("AssetTurnRatio")),
            })
        return result

    async def get_cash_flow_data(self, ts_code: str, n: int = 8) -> list[dict]:
        """
        现金流量数据。

        BaoStock 字段（实测）：code, pubDate, statDate, CAToAsset, NCAToAsset,
                       tangibleAssetToAsset, ebitToInterest, CFOToOR, CFOToNP, CFOToGr
        注意：BaoStock 返回 CFOToNP（经营现金流/净利润），无 CFOToOI。
        """
        bs_code = _to_bs_code(ts_code)
        rows = await self._fetch_quarters(bs_code, "query_cash_flow_data", n)
        result = []
        for r in rows:
            result.append({
                "ts_code":           ts_code,
                "pub_date":          r.get("pubDate"),
                "stat_date":         r.get("statDate"),
                "ca_to_asset":       _safe_float(r.get("CAToAsset")),
                "nca_to_asset":      _safe_float(r.get("NCAToAsset")),
                "tangible_to_asset": _safe_float(r.get("tangibleAssetToAsset")),
                "cfo_to_or":         _safe_float(r.get("CFOToOR")),
                "cfo_to_np":         _safe_float(r.get("CFOToNP")),   # BaoStock: CFO/净利润
                "cfo_to_gr":         _safe_float(r.get("CFOToGr")),   # BaoStock: CFO/营收
                "ebit_to_interest":  _safe_float(r.get("ebitToInterest")),
            })
        return result

    async def get_dupont_data(self, ts_code: str, n: int = 8) -> list[dict]:
        """
        杜邦分析数据。

        BaoStock 字段（实测）：code, pubDate, statDate, dupontROE,
                       dupontAssetStoEquity, dupontAssetTurn, dupontPnitoni,
                       dupontNitogr, dupontTaxBurden, dupontIntburden, dupontEbittogr
        注意：字段名与旧文档不同，以实测为准。
        """
        bs_code = _to_bs_code(ts_code)
        rows = await self._fetch_quarters(bs_code, "query_dupont_data", n)
        result = []
        for r in rows:
            result.append({
                "ts_code":      ts_code,
                "pub_date":     r.get("pubDate"),
                "stat_date":    r.get("statDate"),
                # 核心杜邦分解字段（实测字段名）
                "dupont_roe":   _safe_float(r.get("dupontROE")),
                # 净利/营业利润（净利率分解要素）
                "dupont_npi":   _safe_float(r.get("dupontPnitoni")),
                # 营业利润/营收（EBIT margin）
                "dupont_nitogr": _safe_float(r.get("dupontNitogr")),
                # 税负担率
                "dupont_tax":   _safe_float(r.get("dupontTaxBurden")),
                # 利息负担率
                "dupont_int":   _safe_float(r.get("dupontIntburden")),
                # 资产周转率
                "dupont_at":    _safe_float(r.get("dupontAssetTurn")),
                # 权益乘数（资产/权益）
                "dupont_am":    _safe_float(r.get("dupontAssetStoEquity")),
            })
        return result


    async def get_recent_close(self, ts_code: str, days: int = 5) -> dict | None:
        """
        查询最近 N 个交易日的收盘价 + 估值字段（通过 query_history_k_data_plus）。

        Phase 6N-7B: kline 请求同时携带 peTTM/pbMRQ/psTTM/pcfNcfTTM/turn/pctChg，
        零额外请求成本，使 free mode 页面能显示 PE(TTM)/PB 等 P0 估值字段。

        返回最新一条 {
            "close", "trade_date", "ts_code", "source": "baostock_kline_fallback",
            "pe_ttm", "pb", "ps_ttm", "pcf_ttm", "turnover_rate", "change_pct",
        } 或 None（查询失败/数据空）。缺失的估值字段为 None（如停牌/数据未更新）。
        用途：当 AkShare 快照因网络错误失败时，提供 latest_price + 估值 fallback。
        """
        import datetime
        try:
            import baostock as bs
        except ImportError:
            log.warning("baostock 未安装")
            return None

        bs_code = _to_bs_code(ts_code)
        today = datetime.date.today()
        start = today - datetime.timedelta(days=30)  # 30 天窗口足以覆盖休市

        def _sync_fetch():
            with _suppress_bs_output():
                bs.login()
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,close,pctChg,turn,peTTM,pbMRQ,psTTM,pcfNcfTTM",
                    start_date=start.strftime("%Y-%m-%d"),
                    end_date=today.strftime("%Y-%m-%d"),
                    frequency="d",
                    adjustflag="3",
                )
                rows = _parse_rows(rs)
            finally:
                with _suppress_bs_output():
                    bs.logout()
            return rows

        try:
            async with _get_bs_lock():
                rows = await asyncio.to_thread(_sync_fetch)
            if not rows:
                return None
            latest = rows[-1]
            close = _safe_float(latest.get("close"))
            if close is None:
                return None
            return {
                "ts_code":       ts_code,
                "trade_date":    latest.get("date", ""),
                "close":         close,
                # Phase 6N-7B: BaoStock kline 估值字段（可能为 None）
                "change_pct":    _safe_float(latest.get("pctChg")),   # percent
                "turnover_rate": _safe_float(latest.get("turn")),     # percent
                "pe_ttm":        _safe_float(latest.get("peTTM")),
                "pb":            _safe_float(latest.get("pbMRQ")),
                "ps_ttm":        _safe_float(latest.get("psTTM")),
                "pcf_ttm":       _safe_float(latest.get("pcfNcfTTM")),
                "source":        "baostock_kline_fallback",
            }
        except Exception as e:
            log.warning("BaoStock get_recent_close [%s] 失败: %s", ts_code, e)
            return None


    async def get_all_financial_indicators(
        self,
        ts_code: str,
        n_quarters: int = 8,
    ) -> dict[str, list[dict]]:
        """
        一次 BaoStock 会话获取全部 6 张财务表（一次 login/logout）。

        比分别调用 6 个 get_*_data 方法快约 5–6 倍，
        因为每个 _fetch_quarters 都会 login + n*8 季度查询 + logout。

        返回：
          {
            "profit":    [...],   # get_profit_data
            "growth":    [...],   # get_growth_data
            "balance":   [...],   # get_balance_data
            "operation": [...],   # get_operation_data
            "cash_flow": [...],   # get_cash_flow_data
            "dupont":    [...],   # get_dupont_data
          }
        每个值均为处理后的字典列表（与各 get_*_data 方法返回格式一致）。
        任何表失败时对应列表为空，不影响其他表。
        """
        try:
            import baostock as bs
        except ImportError:
            log.warning("baostock 未安装")
            return {k: [] for k in ("profit", "growth", "balance", "operation", "cash_flow", "dupont")}

        bs_code = _to_bs_code(ts_code)
        quarters = _recent_quarters(n_quarters)

        # 表名 → BaoStock API 函数名
        _TABLE_FNS = {
            "profit":    "query_profit_data",
            "growth":    "query_growth_data",
            "balance":   "query_balance_data",
            "operation": "query_operation_data",
            "cash_flow": "query_cash_flow_data",
            "dupont":    "query_dupont_data",
        }

        def _sync_fetch_all() -> dict[str, list[dict]]:
            """在单次 BaoStock 会话内查询全部 6 张表 × n_quarters 季度。"""
            with _suppress_bs_output():
                bs.login()
            raw: dict[str, list[dict]] = {k: [] for k in _TABLE_FNS}
            for table_key, api_fn_name in _TABLE_FNS.items():
                api_fn = getattr(bs, api_fn_name, None)
                if api_fn is None:
                    log.warning("BaoStock 无此接口: %s", api_fn_name)
                    continue
                for year, quarter in quarters:
                    try:
                        rs = api_fn(code=bs_code, year=year, quarter=quarter)
                        raw[table_key].extend(_parse_rows(rs))
                    except Exception as ex:
                        log.debug(
                            "BaoStock aggregate [%s/%s %dQ%d] 失败: %s",
                            table_key, bs_code, year, quarter, ex,
                        )
            with _suppress_bs_output():
                bs.logout()
            return raw

        raw_all: dict[str, list[dict]] = {}
        try:
            async with _get_bs_lock():
                raw_all = await asyncio.to_thread(_sync_fetch_all)
        except Exception as e:
            log.warning("BaoStock get_all_financial_indicators [%s] 失败: %s", ts_code, e)
            return {k: [] for k in _TABLE_FNS}

        # ── 与各 get_*_data 相同的字段映射 ───────────────────────────────────

        def _map_profit(rows: list[dict]) -> list[dict]:
            return [
                {
                    "ts_code":      ts_code,
                    "pub_date":     r.get("pubDate"),
                    "stat_date":    r.get("statDate"),
                    "roe_avg":      _safe_float(r.get("roeAvg")),
                    "net_margin":   _safe_float(r.get("npMargin")),
                    "gross_margin": _safe_float(r.get("gpMargin")),
                    "net_profit":   _safe_float(r.get("netProfit")),
                    "eps_ttm":      _safe_float(r.get("epsTTM")),
                    "mb_revenue":   _safe_float(r.get("MBRevenue")),
                    "total_share":  _safe_float(r.get("totalShare")),
                    "liqa_share":   _safe_float(r.get("liqaShare")),
                }
                for r in rows
            ]

        def _map_growth(rows: list[dict]) -> list[dict]:
            return [
                {
                    "ts_code":    ts_code,
                    "pub_date":   r.get("pubDate"),
                    "stat_date":  r.get("statDate"),
                    "yoy_equity": _safe_float(r.get("YOYEquity")),
                    "yoy_asset":  _safe_float(r.get("YOYAsset")),
                    "yoy_ni":     _safe_float(r.get("YOYNI")),
                    "yoy_eps":    _safe_float(r.get("YOYEPSBasic")),
                    "yoy_pni":    _safe_float(r.get("YOYPNI")),
                }
                for r in rows
            ]

        def _map_balance(rows: list[dict]) -> list[dict]:
            return [
                {
                    "ts_code":            ts_code,
                    "pub_date":           r.get("pubDate"),
                    "stat_date":          r.get("statDate"),
                    "current_ratio":      _safe_float(r.get("currentRatio")),
                    "quick_ratio":        _safe_float(r.get("quickRatio")),
                    "cash_ratio":         _safe_float(r.get("cashRatio")),
                    "yoy_liability":      _safe_float(r.get("YOYLiability")),
                    "liability_to_asset": _safe_float(r.get("liabilityToAsset")),
                    "asset_to_equity":    _safe_float(r.get("assetToEquity")),
                }
                for r in rows
            ]

        def _map_operation(rows: list[dict]) -> list[dict]:
            return [
                {
                    "ts_code":          ts_code,
                    "pub_date":         r.get("pubDate"),
                    "stat_date":        r.get("statDate"),
                    "nr_turn_ratio":    _safe_float(r.get("NRTurnRatio")),
                    "nr_turn_days":     _safe_float(r.get("NRTurnDays")),
                    "inv_turn_ratio":   _safe_float(r.get("INVTurnRatio")),
                    "inv_turn_days":    _safe_float(r.get("INVTurnDays")),
                    "ca_turn_ratio":    _safe_float(r.get("CATurnRatio")),
                    "asset_turn_ratio": _safe_float(r.get("AssetTurnRatio")),
                }
                for r in rows
            ]

        def _map_cash_flow(rows: list[dict]) -> list[dict]:
            return [
                {
                    "ts_code":           ts_code,
                    "pub_date":          r.get("pubDate"),
                    "stat_date":         r.get("statDate"),
                    "ca_to_asset":       _safe_float(r.get("CAToAsset")),
                    "nca_to_asset":      _safe_float(r.get("NCAToAsset")),
                    "tangible_to_asset": _safe_float(r.get("tangibleAssetToAsset")),
                    "cfo_to_or":         _safe_float(r.get("CFOToOR")),
                    "cfo_to_np":         _safe_float(r.get("CFOToNP")),
                    "cfo_to_gr":         _safe_float(r.get("CFOToGr")),
                    "ebit_to_interest":  _safe_float(r.get("ebitToInterest")),
                }
                for r in rows
            ]

        def _map_dupont(rows: list[dict]) -> list[dict]:
            return [
                {
                    "ts_code":       ts_code,
                    "pub_date":      r.get("pubDate"),
                    "stat_date":     r.get("statDate"),
                    "dupont_roe":    _safe_float(r.get("dupontROE")),
                    "dupont_npi":    _safe_float(r.get("dupontPnitoni")),
                    "dupont_nitogr": _safe_float(r.get("dupontNitogr")),
                    "dupont_tax":    _safe_float(r.get("dupontTaxBurden")),
                    "dupont_int":    _safe_float(r.get("dupontIntburden")),
                    "dupont_at":     _safe_float(r.get("dupontAssetTurn")),
                    "dupont_am":     _safe_float(r.get("dupontAssetStoEquity")),
                }
                for r in rows
            ]

        return {
            "profit":    _map_profit(raw_all.get("profit", [])),
            "growth":    _map_growth(raw_all.get("growth", [])),
            "balance":   _map_balance(raw_all.get("balance", [])),
            "operation": _map_operation(raw_all.get("operation", [])),
            "cash_flow": _map_cash_flow(raw_all.get("cash_flow", [])),
            "dupont":    _map_dupont(raw_all.get("dupont", [])),
        }

    # ── Phase 6T-E1: 批量历史获取（分年缓存 + singleflight + 进程并发 ≤3） ────

    async def get_financial_history_bulk(
        self,
        ts_code: str,
        *,
        start_year: int,
        end_year: int | None = None,
        mode: str = "annual",       # "annual"（每年仅 Q4）| "quarterly"（每年 4 季）
        concurrency: int = 3,
        force_refresh: bool = False,
        valid_quarters: list[tuple[int, int]] | None = None,
    ) -> dict[str, Any]:
        """
        批量获取历史财务数据（替代按 n_quarters 无限串行逐季查询）。

        消除 N+1：
        - annual 模式每年只查 Q4（年报累计），调用数 = 年数 × 6 表；
        - 分年结果缓存（历史年份 30d / 当前年 1d），二次请求零外部调用；
        - singleflight：并发相同请求只执行一次真实抓取；
        - 未缓存年份分片给最多 concurrency(≤3) 个子进程 worker，
          每个 worker 独立会话（BaoStock 全局 socket 无法线程并发）；
        - 早于 2007（BaoStock 季频数据起点）的年份直接跳过并记录截断。

        Returns: {profit/growth/balance/operation/cash_flow/dupont: rows,
                  "_bulk_stats": {...}}
        """
        import datetime as _dt

        if end_year is None:
            end_year = _dt.date.today().year
        requested_start = start_year
        clamped = False
        if start_year < BAOSTOCK_FINANCIAL_DATA_START_YEAR:
            start_year = BAOSTOCK_FINANCIAL_DATA_START_YEAR
            clamped = True
        mode = "quarterly" if mode == "quarterly" else "annual"
        quarters = (1, 2, 3, 4) if mode == "quarterly" else (4,)
        if valid_quarters is not None:
            year_quarters_all = [
                (int(y), int(q)) for y, q in valid_quarters
                if start_year <= int(y) <= end_year and 1 <= int(q) <= 4
            ]
            years = sorted({y for y, _q in year_quarters_all})
        else:
            years = list(range(start_year, end_year + 1))
            year_quarters_all = [(year, q) for year in years for q in quarters]
        concurrency = max(1, min(3, int(concurrency)))
        bs_code = _to_bs_code(ts_code)
        planned_calls = len(year_quarters_all) * len(_BULK_TABLE_KEYS)
        quarter_sig = ",".join(f"{y}Q{q}" for y, q in year_quarters_all) or "none"

        stats: dict[str, Any] = {
            "status": "pending",
            "reason_code": None,
            "errors": [],
            "mode": mode,
            "requested_start_year": requested_start,
            "effective_start_year": start_year,
            "end_year": end_year,
            "provider_history_clamped_to_2007": clamped,
            "years_total": len(years),
            "valid_quarters_total": len(year_quarters_all),
            "provider_calls_planned": planned_calls,
            "planned_calls": planned_calls,
            "actual_calls": 0,
            "calls_by_endpoint": {k: 0 for k in _BULK_TABLE_KEYS},
            "duplicate_calls_avoided": max(0, planned_calls * (len(_BULK_TABLE_KEYS) - 1)),
            "years_from_cache": 0,
            "years_fetched": 0,
            "provider_calls": 0,
            "login_batches": 0,
            "cache_hit": False,
            "years_completed": [],
            "current_year": None,
            "current_quarter": None,
            "last_successful_operation": "",
        }
        empty = {k: [] for k in _BULK_TABLE_KEYS}
        available, import_error = baostock_import_status()
        if not available:
            stats.update({
                "status": "unavailable",
                "reason_code": "PROVIDER_UNAVAILABLE",
                "errors": [import_error or "baostock import unavailable"],
            })
            log.warning("BaoStock unavailable for history bulk [%s]: %s", ts_code, import_error)
            return {**map_aggregate_raw(ts_code, empty), "_bulk_stats": stats}
        if not years:
            stats.update({"status": "empty", "reason_code": "NO_REQUESTED_YEARS"})
            return {**map_aggregate_raw(ts_code, empty), "_bulk_stats": stats}

        from app.services.company_v2_snapshot_cache_service import (
            company_v2_snapshot_cache_service as cache,
        )

        sf_key = f"{ts_code}:{mode}:{start_year}:{end_year}:{quarter_sig}"
        lock = _bulk_singleflight_locks.setdefault(sf_key, asyncio.Lock())
        async with lock:
            if mode == "quarterly":
                bundle_key = cache.make_key("quarterly_bundle", ts_code, str(start_year), str(end_year), quarter_sig, "v2")
                cached_bundle, bundle_hit, _stale, _st = await cache.get(bundle_key, force_refresh=force_refresh)
                if bundle_hit and isinstance(cached_bundle, dict) and isinstance(cached_bundle.get("tables"), dict):
                    stats.update(cached_bundle.get("stats") or {})
                    stats["cache_hit"] = True
                    stats["bundle_cache_hit"] = True
                    stats["years_from_cache"] = len(years)
                    mapped = map_aggregate_raw(ts_code, cached_bundle["tables"])
                    mapped["_bulk_stats"] = stats
                    return mapped

            merged_raw: dict[str, list[dict]] = {k: [] for k in _BULK_TABLE_KEYS}
            uncached_years: list[int] = []
            current_year = _dt.date.today().year

            for year in years:
                year_quarters = [q for y, q in year_quarters_all if y == year]
                year_sig = ",".join(str(q) for q in year_quarters) or "none"
                key = cache.make_key("bsyearraw", ts_code, str(year), mode, year_sig, "v2")
                cached, hit, _stale, _st = await cache.get(key, force_refresh=force_refresh)
                if hit and isinstance(cached, dict) and isinstance(cached.get("tables"), dict):
                    stats["years_from_cache"] += 1
                    stats["years_completed"].append(year)
                    stats["last_successful_operation"] = f"cache:{year}:{mode}"
                    for tk in _BULK_TABLE_KEYS:
                        merged_raw[tk].extend(cached["tables"].get(tk) or [])
                else:
                    uncached_years.append(year)

            if uncached_years:
                # 分片给 ≤concurrency 个子进程 worker（各自独立 BaoStock 会话）
                year_quarters_by_chunk: list[list[tuple[int, int]]] = [
                    [] for _ in range(min(concurrency, len(uncached_years)))
                ]
                for i, year in enumerate(uncached_years):
                    chunk = year_quarters_by_chunk[i % len(year_quarters_by_chunk)]
                    chunk.extend((y, q) for y, q in year_quarters_all if y == year)

                loop = asyncio.get_running_loop()
                from concurrent.futures import ProcessPoolExecutor

                fetched_by_year: dict[int, dict[str, list[dict]]] = {}
                try:
                    with ProcessPoolExecutor(max_workers=len(year_quarters_by_chunk)) as pool:
                        futures = [
                            loop.run_in_executor(pool, _bulk_fetch_years_worker, bs_code, chunk)
                            for chunk in year_quarters_by_chunk if chunk
                        ]
                        stats["login_batches"] = len(futures)
                        results = await asyncio.gather(*futures, return_exceptions=True)
                except Exception as exc:
                    log.warning("bulk fetch pool failed [%s]: %s，回退单会话串行", ts_code, exc)
                    results = []
                    try:
                        flat = [yq for chunk in year_quarters_by_chunk for yq in chunk]
                        async with _get_bs_lock():
                            results = [await asyncio.to_thread(_bulk_fetch_years_worker, bs_code, flat)]
                        stats["login_batches"] = 1
                    except Exception as exc2:
                        log.warning("bulk fetch serial fallback failed [%s]: %s", ts_code, exc2)

                for result in results:
                    if isinstance(result, Exception):
                        log.warning("bulk fetch worker failed [%s]: %s", ts_code, result)
                        continue
                    if len(result) == 3:
                        by_year, calls, calls_by_endpoint = result
                    else:
                        by_year, calls = result
                        calls_by_endpoint = {}
                    stats["provider_calls"] += calls
                    stats["actual_calls"] += calls
                    for endpoint, count in calls_by_endpoint.items():
                        stats["calls_by_endpoint"][endpoint] = stats["calls_by_endpoint"].get(endpoint, 0) + count
                    for year, tables in by_year.items():
                        fetched_by_year[year] = tables

                missing_years = [year for year in uncached_years if year not in fetched_by_year]
                if missing_years:
                    missing_quarters = [
                        (y, q) for y, q in year_quarters_all if y in set(missing_years)
                    ]
                    try:
                        async with _get_bs_lock():
                            serial_result = await asyncio.to_thread(
                                _bulk_fetch_years_worker,
                                bs_code,
                                missing_quarters,
                            )
                        stats["login_batches"] = max(1, stats["login_batches"]) + 1
                        by_year, calls, calls_by_endpoint = serial_result
                        stats["provider_calls"] += calls
                        stats["actual_calls"] += calls
                        for endpoint, count in calls_by_endpoint.items():
                            stats["calls_by_endpoint"][endpoint] = stats["calls_by_endpoint"].get(endpoint, 0) + count
                        for year, tables in by_year.items():
                            fetched_by_year[year] = tables
                    except ImportError as exc:
                        stats["errors"].append(f"PROVIDER_UNAVAILABLE: {exc}")
                        stats["reason_code"] = "PROVIDER_UNAVAILABLE"
                        log.warning("bulk fetch serial fallback unavailable [%s]: %s", ts_code, exc)
                    except Exception as exc:
                        stats["errors"].append(f"serial fallback failed: {str(exc)[:160]}")
                        log.warning("bulk fetch serial fallback failed [%s]: %s", ts_code, exc)

                for year in uncached_years:
                    tables = fetched_by_year.get(year)
                    if tables is None:
                        continue  # worker 失败的年份如实缺失，不伪造
                    stats["years_fetched"] += 1
                    stats["years_completed"].append(year)
                    for tk in _BULK_TABLE_KEYS:
                        merged_raw[tk].extend(tables.get(tk) or [])
                    ttl = 24 * 3600 if year >= current_year else 30 * 24 * 3600
                    try:
                        year_quarters = [q for y, q in year_quarters_all if y == year]
                        year_sig = ",".join(str(q) for q in year_quarters) or "none"
                        await cache.set(
                            cache.make_key("bsyearraw", ts_code, str(year), mode, year_sig, "v2"),
                            {
                                "provider": "baostock",
                                "fetched_at": datetime.now(timezone.utc).isoformat(),
                                "period": mode,
                                "schema_version": "phase6te2-year-raw-v2",
                                "tables": tables,
                                "year": year,
                                "quarters": year_quarters,
                                "mode": mode,
                            },
                            ttl=ttl,
                        )
                        stats["last_successful_operation"] = f"fetch:{year}:{mode}"
                    except Exception as exc:
                        log.debug("bulk year cache set failed: %s", exc)

            stats["cache_hit"] = stats["years_from_cache"] == len(years) and len(years) > 0
            stats["years_completed"] = sorted(set(stats["years_completed"]))
            if stats["years_completed"]:
                stats["status"] = "success" if len(stats["years_completed"]) == len(years) else "partial"
                if stats["status"] == "partial" and not stats.get("reason_code"):
                    stats["reason_code"] = "PARTIAL_PROVIDER_DATA"
            else:
                stats["status"] = "empty"
                if not stats.get("reason_code"):
                    stats["reason_code"] = "PROVIDER_EMPTY"
            mapped = map_aggregate_raw(ts_code, merged_raw)
            if mode == "quarterly" and (stats["years_from_cache"] or stats["years_fetched"]):
                try:
                    await cache.set(
                        bundle_key,
                        {
                            "provider": "baostock",
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "period": mode,
                            "schema_version": "phase6te2-quarterly-bundle-v2",
                            "tables": merged_raw,
                            "start_year": start_year,
                            "end_year": end_year,
                            "valid_quarters": year_quarters_all,
                            "stats": stats,
                        },
                        ttl=3 * 24 * 3600,
                    )
                except Exception as exc:
                    log.debug("bulk quarterly bundle cache set failed: %s", exc)
            mapped["_bulk_stats"] = stats
            return mapped


# ── 单例 ─────────────────────────────────────────────────────────────────────
baostock_client = BaoStockClient()
