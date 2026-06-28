"""
C30.3 — Report Persistence

save_generated_report(): saves a completed analysis run's result dict to the
analysis_reports table and returns the new report_id (str UUID).

Design rules:
- Never fabricates report_id. Returns None on any failure.
- On failure: caller must set run.status = "failed".
- Does NOT commit on its own when called from within a larger transaction;
  commit is explicit here so callers don't need to manage it.
- auto_saved=True by default (generated via chat P3 agent).
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.report_repository import ReportRepository
from app.services.run_registry_protocol import AnalysisRunRef

log = logging.getLogger(__name__)


async def save_generated_report(
    run_ref: AnalysisRunRef,
    full_result: dict,
    db: AsyncSession,
    *,
    auto_saved: bool = True,
) -> Optional[str]:
    """
    Persist the completed analysis result to the analysis_reports table.

    Args:
        run_ref:     AnalysisRunRef with user_id, market, symbol, etc.
        full_result: dict produced by RealtimeAnalysisRunner._do_run()
            {market, symbol, stock_name, report, sections, metadata,
             analysis_scope, output_language}
        db:          AsyncSession (background session — caller manages lifecycle)
        auto_saved:  mark as auto-saved (True for P3 agent runs)

    Returns:
        report_id (str UUID) on success, None on failure.
    """
    try:
        metadata = full_result.get("metadata") or {}
        raw_sections = full_result.get("sections") or {}

        # sections must be str→str (agent results are strings; filter exceptions)
        sections: dict[str, str] = {
            k: v for k, v in raw_sections.items()
            if isinstance(v, str)
        }

        # agents field: {agent_name: {status, message}}
        agents_meta: dict = metadata.get("agents", {})
        agents: dict[str, dict] = {
            name: {"status": info.get("status", "unknown"), "message": info.get("message")}
            for name, info in agents_meta.items()
            if isinstance(info, dict)
        }

        warnings: list[str] = metadata.get("warnings", [])
        if not isinstance(warnings, list):
            warnings = []

        # Determine user UUID
        try:
            user_uuid = uuid.UUID(run_ref.user_id)
        except (ValueError, AttributeError):
            log.error("save_generated_report: invalid user_id=%r [run=%s]",
                      run_ref.user_id, run_ref.run_id)
            return None

        repo = ReportRepository(db)
        report = await repo.create_report(
            user_id         = user_uuid,
            market          = full_result.get("market", run_ref.market),
            symbol          = full_result.get("symbol", run_ref.symbol),
            stock_name      = full_result.get("stock_name") or None,
            report_type     = "comprehensive",
            auto_saved      = auto_saved,
            analysis_scope  = full_result.get("analysis_scope", run_ref.analysis_scope),
            output_language = full_result.get("output_language", run_ref.output_language or "zh-CN"),
            report_md       = full_result.get("report", ""),
            sections        = sections,
            report_metadata = {k: v for k, v in metadata.items() if k not in ("agents", "warnings")},
            warnings        = warnings,
            agents          = agents,
        )
        report_id = str(report.id)
        log.info(
            "C30.3 report saved: run=%s → report_id=%s market=%s symbol=%s",
            run_ref.run_id[:8], report_id[:8], run_ref.market, run_ref.symbol,
        )
        return report_id

    except Exception as exc:
        log.error(
            "C30.3 save_generated_report FAILED [run=%s]: %s",
            run_ref.run_id, exc, exc_info=True,
        )
        try:
            await db.rollback()
        except Exception:
            pass
        return None
