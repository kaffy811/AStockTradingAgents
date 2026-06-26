"""
Watchlist read-only tools (Phase C4):
  - get_watchlist_tool — list user's watchlist items

Write operations (add/remove) stay as mock confirmation in the orchestrator.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_tools.base import BaseTool
from app.agents.chat_tools.tool_result import ToolResult
from app.models.watchlist_item import WatchlistItem

log = logging.getLogger(__name__)


def _card(card_type: str, data: dict) -> dict:
    return {"type": card_type, "data": data}


class GetWatchlistTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_watchlist_tool"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        user_id_raw: Any = kwargs.get("user_id")
        symbol: str      = kwargs.get("symbol", "").strip()   # optional: check if specific stock is in list

        if not user_id_raw:
            return ToolResult(ok=False, tool_name=self.name, summary="缺少用户信息", error="user_id missing")

        try:
            user_id = uuid.UUID(str(user_id_raw))
        except ValueError:
            return ToolResult(ok=False, tool_name=self.name, summary="用户ID无效", error="invalid user_id")

        try:
            stmt = (
                select(WatchlistItem)
                .where(WatchlistItem.user_id == user_id)
                .order_by(WatchlistItem.created_at.desc())
                .limit(50)
            )
            rows = (await db.execute(stmt)).scalars().all()
        except Exception as exc:
            log.warning("get_watchlist_tool: DB error: %s", exc)
            return ToolResult(ok=False, tool_name=self.name, summary="自选股查询失败", error=str(exc))

        items = [
            {
                "market":     r.market,
                "symbol":     r.symbol,
                "note":       r.note,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

        # Check duplicate (used by add_watchlist flow to avoid duplicates)
        already_in = symbol and any(it["symbol"] == symbol for it in items)

        card = _card("watchlist_list", {
            "items": items[:10],   # show at most 10 in card
            "total": len(items),
            "links": [{"label": "查看自选股", "path": "/watchlist"}],
        })

        return ToolResult(
            ok=True,
            tool_name=self.name,
            summary=f"自选股列表，共 {len(items)} 只" + ("，未发现重复" if symbol and not already_in else ""),
            data={"items": items, "count": len(items), "already_in": already_in},
            cards=[card] if items else [],
            source="db",
        )
