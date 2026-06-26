"""
orchestrator/market_agent.py — Phase 2E-1: Market / Quote / Kline Sub-Agent.

Responsibilities
----------------
* Fetch real-time quote and K-line data.
* Compute summary statistics: range return, high/low, volume.
* Return AgentFinding — never LLM output.

Reuses (does NOT re-implement)
-------------------------------
* GetQuoteTool       (app.agents.chat_tools.stock_tools)
* GetKlineSummaryTool

Safety rules
------------
* Never outputs buy/sell/hold advice.
* If market data is unavailable, status=failed (not fabricated).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator.schemas import make_agent_finding

log = logging.getLogger(__name__)

AGENT_NAME      = "market_agent"
TIMEOUT_SECONDS = 15.0


class MarketAgent:
    """
    Sub-agent for market / quote / K-line data.

    Accepts injectable `quote_tool` and `kline_tool` for unit testing.
    """

    def __init__(
        self,
        *,
        quote_tool: Any = None,
        kline_tool: Any = None,
    ) -> None:
        self._quote_tool = quote_tool
        self._kline_tool = kline_tool

    def _get_quote_tool(self) -> Any:
        if self._quote_tool is not None:
            return self._quote_tool
        from app.agents.chat_tools.stock_tools import GetQuoteTool  # noqa: PLC0415
        return GetQuoteTool()

    def _get_kline_tool(self) -> Any:
        if self._kline_tool is not None:
            return self._kline_tool
        from app.agents.chat_tools.stock_tools import GetKlineSummaryTool  # noqa: PLC0415
        return GetKlineSummaryTool()

    async def run(
        self,
        intent: dict,
        db: AsyncSession,
        *,
        event_callback: Callable | None = None,
    ) -> dict:
        """
        Fetch market data and return an AgentFinding dict.

        Never raises.
        """
        symbol      = intent.get("symbol", "")
        market      = intent.get("market", "")
        kline_limit = int(intent.get("kline_limit") or 30)

        risk_flags:   list[str] = []
        data_points:  list[str] = []
        data_quality: dict      = {"market_data_available": False}

        if not symbol or not market:
            return make_agent_finding(
                AGENT_NAME,
                status="failed",
                summary="缺少股票代码或市场信息，无法获取行情数据。",
                risk_flags=["missing_symbol"],
            )

        # ── Quote ─────────────────────────────────────────────────────────────
        if intent.get("need_quote"):
            try:
                tool   = self._get_quote_tool()
                result = await tool.run(db, market=market, symbol=symbol, name=symbol)
                if result.ok and result.data:
                    d = result.data
                    if d.get("price") not in (None, "N/A", ""):
                        data_points.append(f"当前价格: {d.get('price')}")
                    if d.get("change_pct") not in (None, "N/A", ""):
                        data_points.append(f"涨跌幅: {d.get('change_pct')}%")
                    data_quality["market_data_available"] = True
                else:
                    risk_flags.append("quote_failed")
            except Exception as exc:
                log.warning("MarketAgent: quote tool failed: %s", exc)
                risk_flags.append("quote_failed")

        # ── Kline ─────────────────────────────────────────────────────────────
        kline_data: dict     = {}
        kline_bars: list     = []
        if intent.get("need_kline"):
            try:
                tool   = self._get_kline_tool()
                result = await tool.run(db, market=market, symbol=symbol, limit=kline_limit)
                if result.ok and result.data:
                    kline_data = result.data
                    kline_bars = kline_data.get("bars_sample", [])
                    bars_count = kline_data.get("bars_count", 0)
                    period_chg = kline_data.get("period_change_pct")

                    data_points.append(f"K线数据: {bars_count}条")
                    if period_chg is not None:
                        data_points.append(f"区间涨跌幅: {period_chg:.2f}%")

                    # Extract high / low / volume from bars sample
                    if kline_bars:
                        highs = [b.get("high") for b in kline_bars if b.get("high") is not None]
                        lows  = [b.get("low")  for b in kline_bars if b.get("low")  is not None]
                        vols  = [b.get("volume") for b in kline_bars if b.get("volume") is not None]
                        if highs:
                            data_points.append(f"样本最高价: {max(highs):.2f}")
                        if lows:
                            data_points.append(f"样本最低价: {min(lows):.2f}")
                        if vols:
                            avg_vol = sum(vols) / len(vols)
                            data_points.append(f"平均成交量: {avg_vol:.0f}")

                    data_quality["market_data_available"] = True
                    data_quality["bars_count"] = kline_data.get("bars_count", len(kline_bars))
                else:
                    risk_flags.append("kline_failed")
            except Exception as exc:
                log.warning("MarketAgent: kline tool failed: %s", exc)
                risk_flags.append("kline_failed")

        # ── Status ────────────────────────────────────────────────────────────
        if not data_points:
            return make_agent_finding(
                AGENT_NAME,
                status="failed",
                summary=f"无法获取 {symbol} 的行情数据。",
                risk_flags=risk_flags,
                data_quality=data_quality,
            )

        bars_cnt    = kline_data.get("bars_count", len(kline_bars))
        period_chg  = kline_data.get("period_change_pct")
        chg_str     = f"区间涨跌幅 {period_chg:.2f}%，" if period_chg is not None else ""
        summary     = f"{symbol} 行情数据获取成功。{chg_str}{bars_cnt}条K线。"

        return make_agent_finding(
            AGENT_NAME,
            status="success",
            summary=summary,
            data_points=data_points,
            risk_flags=risk_flags,
            data_quality=data_quality,
        )
