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

    async def fetch_baostock(self, market: str, symbol: str) -> dict[str, Any]:
        """
        BaoStock 免费数据获取（可选实现，Phase 6A）。

        默认抛出 NotImplementedError，子类如需 BaoStock fallback 则覆盖此方法。
        """
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 BaoStock fetch")

    @staticmethod
    def _is_network_error(exc: Exception) -> bool:
        """判断异常是否为网络/超时类错误（Phase 6N-8A error_code 分类用）。"""
        msg = repr(exc).lower()
        return any(k in msg for k in (
            "timeout", "timed out", "connection", "proxy", "remote",
            "unreachable", "refused", "network", "dns",
        ))

    async def _fetch_free_mode(self, market: str, symbol: str) -> DataEnvelope:
        """
        DATA_MODE=free 路径：跳过 Tushare，依次尝试 BaoStock → AkShare。

        Phase 6N-8A: 失败信封携带稳定 error_code —
          - 任一 provider 因网络/超时失败 → DATA_SOURCE_UNAVAILABLE
          - provider 可达但无数据 / 未实现     → DATA_SOURCE_EMPTY
        auth 错误绝不会走到这里（401 在路由依赖层直接抛出）。
        """
        from app.core.config import settings
        from app.core.error_codes import DATA_SOURCE_EMPTY, DATA_SOURCE_UNAVAILABLE

        network_failed = False

        # 优先 BaoStock
        if settings.enable_baostock:
            try:
                data = await self.fetch_baostock(market, symbol)
                log.info("BaoStock fetch 成功 [%s/%s/%s]", self.module_key, market, symbol)
                return ok_envelope(data)
            except NotImplementedError:
                pass  # 子类未实现，静默跳过
            except Exception as e:
                network_failed = network_failed or self._is_network_error(e)
                log.warning("BaoStock 失败 [%s/%s/%s]: %s", self.module_key, market, symbol, e)

        # 降级 AkShare
        if settings.enable_akshare:
            try:
                data = await self.fetch_akshare(market, symbol)
                log.info("AkShare fallback 成功 [%s/%s/%s]", self.module_key, market, symbol)
                return ok_envelope(data, stale=True)
            except NotImplementedError:
                pass
            except Exception as e:
                network_failed = network_failed or self._is_network_error(e)
                log.warning("AkShare 失败 [%s/%s/%s]: %s", self.module_key, market, symbol, e)

        # Deprecated legacy Company Tab message.
        # CompanyV2 must use DebugEnvelope error_code/source_chain instead of
        # this generic BaoStock/AkShare attribution.
        return err_envelope(
            "DATA_MODE=free：BaoStock 和 AkShare 均未返回数据，"
            "请检查 ENABLE_BAOSTOCK / ENABLE_AKSHARE 配置。",
            error_code=DATA_SOURCE_UNAVAILABLE if network_failed else DATA_SOURCE_EMPTY,
        )

    async def fetch_with_fallback(
        self,
        market: str,
        symbol: str,
    ) -> DataEnvelope:
        """
        尝试 Tushare，失败时降级到 AkShare（如果 ENABLE_AKSHARE=true）。
        Phase 6A：DATA_MODE=free 时跳过 Tushare，走 BaoStock → AkShare 链。
        返回 DataEnvelope。

        流程（standard 模式）：
          1. 调用 fetch()（Tushare）
          2. 成功 → 返回 ok_envelope(data)
          3. 失败 → 检查 ENABLE_AKSHARE
             a. 未开启 → 返回 err_envelope(reason)
             b. 已开启 → 调用 fetch_akshare()
                i.  成功 → 返回 ok_envelope(data, stale=True)
                ii. 失败 → 返回 err_envelope(combined_reason)

        流程（free 模式）：
          BaoStock（if ENABLE_BAOSTOCK）→ AkShare（if ENABLE_AKSHARE）→ err_envelope
        """
        from app.core.config import settings
        from app.datasource.tushare_client import TushareError, TushareAuthError

        # Phase 6A: free mode 完全跳过 Tushare
        if settings.data_mode == "free":
            return await self._fetch_free_mode(market, symbol)

        # 尝试 Tushare
        _is_permission_error = False
        try:
            data = await self.fetch(market, symbol)
            return ok_envelope(data)
        except TushareAuthError as primary_err:
            # P1-B: permission errors must NOT expose raw provider error to users.
            # Log the raw detail internally; use a safe user-facing message in the envelope.
            _is_permission_error = True
            log.warning(
                "Tushare 权限不足 [%s/%s/%s]: %s",
                self.module_key, market, symbol, repr(primary_err),
            )
            primary_reason = "部分财务指标暂不可用，系统已继续使用其他可用数据源。"
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

        # Tushare 失败 → 尝试 AkShare（权限错误也试，因为 AkShare 是独立数据源）
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
                from app.core.error_codes import DATA_SOURCE_EMPTY, DATA_SOURCE_UNAVAILABLE
                # P1-B: for permission errors, keep the safe user-facing reason
                combined_reason = (
                    primary_reason
                    if _is_permission_error
                    else f"Tushare 失败（{primary_reason}）；AkShare 也失败（{fallback_err}）"
                )
                return err_envelope(
                    combined_reason,
                    error_code=(
                        DATA_SOURCE_UNAVAILABLE
                        if self._is_network_error(fallback_err)
                        else DATA_SOURCE_EMPTY
                    ),
                )

        from app.core.error_codes import DATA_SOURCE_EMPTY
        return err_envelope(primary_reason, error_code=DATA_SOURCE_EMPTY)
