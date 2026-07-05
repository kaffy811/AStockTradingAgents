"""
app/tools/fundamental/base.py — 基本面工具基类

BaseFundamentalTool 定义所有工具必须实现的接口：
  - fetch(market, symbol) → dict   （纯数据，无 envelope）
  - fetch_with_fallback(market, symbol) → DataEnvelope  （带 AkShare 降级）

工具类不负责缓存，缓存由 FundamentalsAggregator 处理。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from app.aggregator.envelope import DataEnvelope, ok_envelope, err_envelope

log = logging.getLogger(__name__)


class FundamentalToolError(RuntimeError):
    """工具层数据获取/解析失败的基类异常。"""


class BaseFundamentalTool(ABC):
    """
    基本面数据工具基类。

    子类必须定义：
        module_key:       str  — 模块唯一标识（如 "quote_snapshot"）
        cache_ttl_seconds: int — 主 TTL（秒）
        stale_ttl_seconds: int — stale 降级 TTL（秒）

    子类必须实现：
        fetch(market, symbol) → dict  — 从 Tushare 获取原始数据
        fetch_akshare(market, symbol) → dict  — AkShare 备用（可选，默认抛出 NotImplementedError）
    """

    module_key: str = ""
    cache_ttl_seconds: int = 3600
    stale_ttl_seconds: int = 86400

    @abstractmethod
    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        """
        从主数据源（Tushare）获取原始数据。

        返回值：纯 dict，不包含 DataEnvelope 包装。
        失败时抛出 FundamentalToolError 或 TushareError 的子类。
        """

    async def fetch_akshare(self, market: str, symbol: str) -> dict[str, Any]:
        """
        AkShare 备用数据获取（可选实现）。

        默认抛出 NotImplementedError，子类如需 AkShare fallback 则覆盖此方法。
        """
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 AkShare fallback")

    async def fetch_with_fallback(
        self,
        market: str,
        symbol: str,
    ) -> DataEnvelope:
        """
        尝试 Tushare，失败时降级到 AkShare（如果 ENABLE_AKSHARE=true）。
        返回 DataEnvelope。

        流程：
          1. 调用 fetch()（Tushare）
          2. 成功 → 返回 ok_envelope(data)
          3. 失败 → 检查 ENABLE_AKSHARE
             a. 未开启 → 返回 err_envelope(reason)
             b. 已开启 → 调用 fetch_akshare()
                i.  成功 → 返回 ok_envelope(data, stale=True)（标记为 stale 表示数据来源降级）
                ii. 失败 → 返回 err_envelope(combined_reason)
        """
        from app.core.config import settings
        from app.datasource.tushare_client import TushareError

        # 尝试 Tushare
        try:
            data = await self.fetch(market, symbol)
            return ok_envelope(data)
        except TushareError as primary_err:
            primary_reason = str(primary_err)
            log.warning(
                "Tushare fetch 失败 [%s/%s/%s]: %s",
                self.module_key, market, symbol, primary_reason,
            )
        except FundamentalToolError as primary_err:
            primary_reason = str(primary_err)
            log.warning(
                "Tool fetch 失败 [%s/%s/%s]: %s",
                self.module_key, market, symbol, primary_reason,
            )
        except Exception as primary_err:
            primary_reason = str(primary_err)
            log.error(
                "Tool fetch 意外异常 [%s/%s/%s]: %s",
                self.module_key, market, symbol, primary_reason,
                exc_info=True,
            )

        # Tushare 失败 → 尝试 AkShare
        if settings.enable_akshare:
            try:
                data = await self.fetch_akshare(market, symbol)
                log.info(
                    "AkShare fallback 成功 [%s/%s/%s]",
                    self.module_key, market, symbol,
                )
                return ok_envelope(data, stale=True)
            except NotImplementedError:
                pass  # 子类未实现 AkShare fallback，不记录 warning
            except Exception as fallback_err:
                log.warning(
                    "AkShare fallback 也失败 [%s/%s/%s]: %s",
                    self.module_key, market, symbol, fallback_err,
                )
                return err_envelope(
                    f"Tushare 失败（{primary_reason}）；AkShare 也失败（{fallback_err}）"
                )

        return err_envelope(primary_reason)
