"""
C30.2.2 — ReportRepository: single-source-of-truth data access layer for analysis reports.

All reads and writes for the analysis_reports table go through this class.
Enforces user-level isolation: every query filters by user_id.

Users:
  - save_generated_report() → ReportRepository.create_report()
  - GET /reports/           → ReportRepository.list_reports()
  - GET /reports/{id}       → ReportRepository.get_report()
  - DELETE /reports/{id}    → ReportRepository.delete_report()
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_report import AnalysisReport


class ReportRepository:
    """Async repository for AnalysisReport ORM objects.

    Every public method takes ``user_id`` as a mandatory positional argument
    to enforce ownership isolation — users can only access their own reports.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Write ─────────────────────────────────────────────────────────────────

    async def create_report(
        self,
        *,
        user_id:         uuid.UUID,
        market:          str,
        symbol:          str,
        stock_name:      Optional[str],
        report_type:     str = "comprehensive",
        auto_saved:      bool = True,
        analysis_scope:  str = "comprehensive",
        output_language: str = "zh-CN",
        report_md:       str,
        sections:        dict[str, str],
        report_metadata: dict,
        warnings:        list[str],
        agents:          dict[str, dict],
    ) -> AnalysisReport:
        """
        Persist a new report and return the saved ORM object (with ``id`` populated).
        Commits and refreshes — caller does NOT need to manage the transaction.
        Raises on any DB error (caller should catch and handle).
        """
        report = AnalysisReport(
            user_id         = user_id,
            market          = market.upper(),
            symbol          = symbol,
            stock_name      = stock_name or None,
            report_type     = report_type,
            auto_saved      = auto_saved,
            analysis_scope  = analysis_scope,
            output_language = output_language,
            report_md       = report_md,
            sections        = sections,
            report_metadata = report_metadata,
            warnings        = warnings,
            agents          = agents,
        )
        self._db.add(report)
        await self._db.commit()
        await self._db.refresh(report)
        return report

    async def delete_report(
        self,
        user_id:   uuid.UUID,
        report_id: uuid.UUID,
    ) -> bool:
        """
        Delete report by id. Returns True if deleted, False if not found or wrong owner.
        Commits on success.
        """
        stmt = select(AnalysisReport).where(
            AnalysisReport.id      == report_id,
            AnalysisReport.user_id == user_id,
        )
        report = (await self._db.execute(stmt)).scalar_one_or_none()
        if report is None:
            return False
        await self._db.delete(report)
        await self._db.commit()
        return True

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_report(
        self,
        user_id:   uuid.UUID,
        report_id: uuid.UUID,
    ) -> Optional[AnalysisReport]:
        """
        Return a single report by id, or None if not found / wrong owner.
        Enforces user_id isolation.
        """
        stmt = select(AnalysisReport).where(
            AnalysisReport.id      == report_id,
            AnalysisReport.user_id == user_id,
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def list_reports(
        self,
        user_id:        uuid.UUID,
        *,
        market:         Optional[str]  = None,
        symbol:         Optional[str]  = None,
        analysis_scope: Optional[str]  = None,
        auto_saved:     Optional[bool] = None,
        start_date:     Optional[date] = None,
        end_date:       Optional[date] = None,
        limit:          int = 20,
        offset:         int = 0,
    ) -> tuple[int, list[AnalysisReport]]:
        """
        Return (total_count, page_of_reports) for the given user.

        All filters are additive; only reports owned by user_id are returned.
        Results are ordered newest-first.
        """
        filters = [AnalysisReport.user_id == user_id]
        if market:
            filters.append(AnalysisReport.market == market.upper())
        if symbol:
            filters.append(AnalysisReport.symbol == symbol.strip())
        if analysis_scope:
            filters.append(AnalysisReport.analysis_scope == analysis_scope.strip())
        if auto_saved is not None:
            filters.append(AnalysisReport.auto_saved == auto_saved)
        if start_date:
            dt_start = datetime(start_date.year, start_date.month, start_date.day,
                                tzinfo=timezone.utc)
            filters.append(AnalysisReport.created_at >= dt_start)
        if end_date:
            dt_end = datetime(end_date.year, end_date.month, end_date.day,
                              tzinfo=timezone.utc) + __import__("datetime").timedelta(days=1)
            filters.append(AnalysisReport.created_at < dt_end)

        count_stmt = select(func.count()).select_from(AnalysisReport).where(*filters)
        total: int = (await self._db.execute(count_stmt)).scalar_one()

        rows_stmt = (
            select(AnalysisReport)
            .where(*filters)
            .order_by(AnalysisReport.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self._db.execute(rows_stmt)).scalars().all())
        return total, rows
