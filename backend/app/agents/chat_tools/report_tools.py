"""
Report read-only tools (Phase C4):
  - get_recent_reports_tool — list user's recent reports for a stock
  - get_report_detail_tool  — fetch one report's summary section

All tools return ToolResult.  No investment advice output.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_tools.base import BaseTool
from app.agents.chat_tools.tool_result import ToolResult
from app.models.analysis_report import AnalysisReport

log = logging.getLogger(__name__)


def _card(card_type: str, data: dict) -> dict:
    return {"type": card_type, "data": data}


class GetRecentReportsTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_recent_reports_tool"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        user_id_raw: Any = kwargs.get("user_id")
        market: str      = kwargs.get("market", "CN").upper()
        symbol: str      = kwargs.get("symbol", "").strip()
        limit: int       = int(kwargs.get("limit", 5))

        if not user_id_raw:
            return ToolResult(ok=False, tool_name=self.name, summary="缺少用户信息", error="user_id missing")

        try:
            user_id = uuid.UUID(str(user_id_raw))
        except ValueError:
            return ToolResult(ok=False, tool_name=self.name, summary="用户ID无效", error="invalid user_id")

        try:
            filters = [AnalysisReport.user_id == user_id]
            if market:
                filters.append(AnalysisReport.market == market)
            if symbol:
                filters.append(AnalysisReport.symbol == symbol)

            stmt = (
                select(AnalysisReport)
                .where(*filters)
                .order_by(desc(AnalysisReport.created_at))
                .limit(limit)
            )
            rows = (await db.execute(stmt)).scalars().all()
        except Exception as exc:
            log.warning("get_recent_reports_tool: DB error: %s", exc)
            return ToolResult(ok=False, tool_name=self.name, summary="报告查询失败", error=str(exc))

        if not rows:
            return ToolResult(
                ok=True,
                tool_name=self.name,
                summary="暂无历史报告",
                data={"items": [], "count": 0},
                source="db",
            )

        items = [
            {
                "id":             str(r.id),
                "market":         r.market,
                "symbol":         r.symbol,
                "stock_name":     r.stock_name or r.symbol,
                "analysis_scope": r.analysis_scope,
                "created_at":     r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

        card = _card("report_list", {
            "items": items,
            "links": [{"label": "查看全部报告", "path": "/history"}],
        })

        return ToolResult(
            ok=True,
            tool_name=self.name,
            summary=f"找到 {len(items)} 份历史报告",
            data={"items": items, "count": len(items)},
            cards=[card],
            source="db",
        )


class GetReportDetailTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_report_detail_tool"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        user_id_raw: Any = kwargs.get("user_id")
        report_id_raw: Any = kwargs.get("report_id")

        if not user_id_raw or not report_id_raw:
            return ToolResult(ok=False, tool_name=self.name, summary="缺少报告或用户ID", error="missing params")

        try:
            user_id   = uuid.UUID(str(user_id_raw))
            report_id = uuid.UUID(str(report_id_raw))
        except ValueError as exc:
            return ToolResult(ok=False, tool_name=self.name, summary="参数格式无效", error=str(exc))

        try:
            stmt = select(AnalysisReport).where(
                AnalysisReport.id      == report_id,
                AnalysisReport.user_id == user_id,
            )
            report: AnalysisReport | None = (await db.execute(stmt)).scalar_one_or_none()
        except Exception as exc:
            log.warning("get_report_detail_tool: DB error: %s", exc)
            return ToolResult(ok=False, tool_name=self.name, summary="报告获取失败", error=str(exc))

        if report is None:
            return ToolResult(ok=False, tool_name=self.name, summary="报告不存在", error="not found")

        # Return only a short summary — not the full report content (LLM injection risk)
        content: str = report.report_md or ""
        # Extract first ~500 chars of report as a safe preview
        preview = content[:500] + ("…" if len(content) > 500 else "")

        return ToolResult(
            ok=True,
            tool_name=self.name,
            summary=f"获取报告 {report.stock_name or report.symbol}（{report.analysis_scope}）",
            data={
                "id":             str(report.id),
                "market":         report.market,
                "symbol":         report.symbol,
                "stock_name":     report.stock_name or report.symbol,
                "analysis_scope": report.analysis_scope,
                "created_at":     report.created_at.isoformat() if report.created_at else None,
                "preview":        preview,
            },
            source="db",
        )
