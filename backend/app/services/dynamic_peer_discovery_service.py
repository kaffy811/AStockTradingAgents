"""
DynamicPeerDiscoveryService
============================
动态同行发现服务。返回给定股票的同行列表，优先级：

  1. PEER_MAP 手动 override（任何市场均可）
  2. CN 动态行业 Hot Top5（从 industry_hot_stock_snapshot 读取）
  3. 非 CN 且无 PEER_MAP → 空列表
  4. CN 但无行业映射 → 空列表
  5. CN 有行业但无 hot snapshot → 空列表

注意：
- 动态 Hot Top5 代表市场关注度，不等于严格业务可比同行，
  调用方需自行在分析提示中说明此限制。
- PEER_MAP 不会被修改；从 peer_comparison_service 直接导入。
- 不使用 LLM 做任何判断。
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.industry_classification_service import industry_classification_service
from app.services.industry_hot_stock_service import industry_hot_stock_service
from app.services.peer_comparison_service import PEER_MAP

log = logging.getLogger(__name__)

# 固定 message 文本
_MSG_MANUAL = (
    "Peers are selected from manual PEER_MAP override."
)
_MSG_DYNAMIC_HOT = (
    "Peers are selected from same SW level-1 industry hot stocks; "
    "this reflects market attention, not strict business comparability or investment value."
)
_MSG_CN_ONLY = (
    "dynamic peer discovery currently supports CN only"
)
_MSG_NO_INDUSTRY = "No industry mapping found for this symbol."
_MSG_NO_SNAPSHOT = "Industry mapping exists, but no hot stock snapshot is available."


class DynamicPeerDiscoveryService:

    async def discover_peers(
        self,
        db:     AsyncSession,
        market: str,
        symbol: str,
        limit:  int = 5,
    ) -> dict:
        """
        返回同行发现结果。

        返回结构：
          {
            "market": str,
            "symbol": str,
            "industry": {industry_code, industry_name, industry_level, source} | None,
            "peers": [...],
            "data_quality": {peer_source, hot_stock_date, hot_score_version,
                             fallback_reason, message}
          }

        永不抛异常；出错时 peers=[]，data_quality 说明原因。
        """
        market = market.upper()
        symbol = symbol.strip()

        # ── Step 1: PEER_MAP override ─────────────────────────────────────────
        peer_tuples: list[tuple[str, str]] | None = PEER_MAP.get((market, symbol))

        if peer_tuples is not None:
            peers = [
                {
                    "market":       pm,
                    "symbol":       ps,
                    "name":         None,       # PEER_MAP 不存名称；调用方可自行补充
                    "peer_source":  "manual_map",
                    "rank":         idx + 1,
                    "hot_score":    None,
                    "score_factors": None,
                }
                for idx, (pm, ps) in enumerate(peer_tuples[:limit])
            ]
            return {
                "market":  market,
                "symbol":  symbol,
                "industry": None,               # override 不依赖行业
                "peers":   peers,
                "data_quality": {
                    "peer_source":       "manual_map",
                    "hot_stock_date":    None,
                    "hot_score_version": None,
                    "fallback_reason":   None,
                    "message":           _MSG_MANUAL,
                },
            }

        # ── Step 2: 非 CN 市场无 PEER_MAP ─────────────────────────────────────
        if market != "CN":
            return self._empty_result(
                market, symbol,
                industry=None,
                peer_source="none",
                fallback_reason=_MSG_CN_ONLY,
                message=_MSG_CN_ONLY,
            )

        # ── Step 3: 查行业映射 ────────────────────────────────────────────────
        try:
            industry_row = await industry_classification_service.get_stock_industry(
                db, market, symbol
            )
        except Exception as e:
            log.warning("discover_peers: industry lookup failed for %s/%s: %s", market, symbol, e)
            industry_row = None

        if industry_row is None:
            return self._empty_result(
                market, symbol,
                industry=None,
                peer_source="none",
                fallback_reason="industry mapping not found",
                message=_MSG_NO_INDUSTRY,
            )

        industry_info = {
            "industry_code":  industry_row["industry_code"],
            "industry_name":  industry_row["industry_name"],
            "industry_level": industry_row.get("industry_level"),
            "source":         industry_row.get("source"),
            "last_synced_at": None,
        }

        # ── Step 4: 查行业热门股 ──────────────────────────────────────────────
        try:
            hot_result = await industry_hot_stock_service.get_latest_hot_stocks(
                db, market, industry_row["industry_code"], limit=limit + 1
            )
        except Exception as e:
            log.warning("discover_peers: hot stock lookup failed for %s: %s",
                        industry_row["industry_code"], e)
            hot_result = {"items": [], "data_quality": {"message": str(e)}, "trade_date": None, "score_version": "v1"}

        hot_items: list[dict] = hot_result.get("items", [])
        hot_trade_date: date | None = hot_result.get("trade_date")
        hot_version: str = hot_result.get("score_version", "v1")

        if not hot_items:
            return self._empty_result(
                market, symbol,
                industry=industry_info,
                peer_source="none",
                fallback_reason="no hot stock snapshot available",
                message=_MSG_NO_SNAPSHOT,
            )

        # ── Step 5: 排除自身，截取 limit ─────────────────────────────────────
        peers = []
        for item in hot_items:
            if item["symbol"] == symbol:
                continue
            peers.append({
                "market":        market,
                "symbol":        item["symbol"],
                "name":          item.get("stock_name"),
                "peer_source":   "dynamic_hot",
                "rank":          item["rank"],
                "hot_score":     item.get("hot_score"),
                "score_factors": item.get("score_factors"),
            })
            if len(peers) >= limit:
                break

        if not peers:
            return self._empty_result(
                market, symbol,
                industry=industry_info,
                peer_source="none",
                fallback_reason="no hot stock snapshot available after excluding self",
                message=_MSG_NO_SNAPSHOT,
            )

        return {
            "market":   market,
            "symbol":   symbol,
            "industry": industry_info,
            "peers":    peers,
            "data_quality": {
                "peer_source":       "dynamic_hot",
                "hot_stock_date":    str(hot_trade_date) if hot_trade_date else None,
                "hot_score_version": hot_version,
                "fallback_reason":   None,
                "message":           _MSG_DYNAMIC_HOT,
            },
        }

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _empty_result(
        market:         str,
        symbol:         str,
        industry:       dict | None,
        peer_source:    str,
        fallback_reason: str | None,
        message:        str | None,
    ) -> dict:
        return {
            "market":   market,
            "symbol":   symbol,
            "industry": industry,
            "peers":    [],
            "data_quality": {
                "peer_source":       peer_source,
                "hot_stock_date":    None,
                "hot_score_version": None,
                "fallback_reason":   fallback_reason,
                "message":           message,
            },
        }


# 模块级单例
dynamic_peer_discovery_service = DynamicPeerDiscoveryService()
