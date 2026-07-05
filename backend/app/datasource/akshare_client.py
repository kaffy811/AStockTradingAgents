"""
app/datasource/akshare_client.py — AkShare 基本面数据备用封装

**重要**：本模块仅在 ENABLE_AKSHARE=true 时被激活。
         即使导入本模块，若 settings.enable_akshare=False，
         所有方法均立即抛出 AkShareDisabledError。

使用方式（在 Tool 内）：
    from app.datasource.akshare_client import akshare_fs_client, AkShareDisabledError
    try:
        data = await akshare_fs_client.get_financial_abstract(symbol)
    except AkShareDisabledError:
        # ENABLE_AKSHARE=false，不使用备用
        raise
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)


class AkShareDisabledError(RuntimeError):
    """ENABLE_AKSHARE=false 时所有 AkShare 方法抛出此错误。"""


class AkShareFSClient:
    """
    AkShare 基本面数据备用客户端。

    仅封装 Fundamental Service 需要的接口，
    复用已有 AkShareFundamentalProvider 的解析逻辑。
    """

    def _check_enabled(self) -> None:
        from app.core.config import settings
        if not settings.enable_akshare:
            raise AkShareDisabledError(
                "AkShare 数据源已禁用（ENABLE_AKSHARE=false）。"
                "如需启用，请在 .env 中设置 ENABLE_AKSHARE=true。"
            )

    async def get_financial_abstract(self, symbol: str) -> dict[str, Any]:
        """
        同花顺财务摘要（复用 AkShareFundamentalProvider.get_financial_abstract）。
        ENABLE_AKSHARE=false 时抛出 AkShareDisabledError。
        """
        self._check_enabled()
        from app.data.providers.fundamental_provider import fundamental_provider
        return await asyncio.to_thread(fundamental_provider.get_financial_abstract, symbol)

    async def get_cash_flow(self, symbol: str) -> dict[str, Any]:
        """
        同花顺现金流（复用 AkShareFundamentalProvider.get_cash_flow）。
        """
        self._check_enabled()
        from app.data.providers.fundamental_provider import fundamental_provider
        return await asyncio.to_thread(fundamental_provider.get_cash_flow, symbol)

    async def get_real_time_quote(self, symbol: str, market: str = "CN") -> dict[str, Any]:
        """
        实时行情（通过 AkShare stock_zh_a_spot_em 或同类接口）。
        仅 CN 市场支持。
        """
        self._check_enabled()
        if market.upper() != "CN":
            raise AkShareDisabledError(f"AkShare 不支持 {market} 市场的实时行情备用")

        import akshare as ak

        def _fetch() -> dict[str, Any]:
            # 全市场快照，筛选指定 symbol
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                raise RuntimeError("AkShare stock_zh_a_spot_em 返回空数据")
            row = df[df["代码"] == symbol]
            if row.empty:
                raise RuntimeError(f"AkShare 未找到 symbol={symbol}")
            r = row.iloc[0]
            return {
                "symbol": symbol,
                "name": str(r.get("名称", "")),
                "close": float(r.get("最新价", 0) or 0),
                "change_pct": float(r.get("涨跌幅", 0) or 0),
                "volume": float(r.get("成交量", 0) or 0),
                "amount": float(r.get("成交额", 0) or 0),
                "high": float(r.get("最高", 0) or 0),
                "low": float(r.get("最低", 0) or 0),
                "open": float(r.get("今开", 0) or 0),
                "pre_close": float(r.get("昨收", 0) or 0),
                "source": "akshare_fallback",
            }

        return await asyncio.to_thread(_fetch)


# ── 模块级单例 ────────────────────────────────────────────────────────────────

akshare_fs_client = AkShareFSClient()
