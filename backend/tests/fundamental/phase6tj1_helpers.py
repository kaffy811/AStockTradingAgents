"""Shared helpers for Phase 6T-J1 persistence tests.

DB-backed tests use isolated high report_ids (>= 990000) and always clean up,
so the real acceptance data (report_id 2-5) is never touched.
"""
from __future__ import annotations

import hashlib
from typing import Any

from app.services.company_v2_report_chunker import ReportChunkDraft
from app.services.company_v2_report_rag_index_service import ReportDescriptor


def make_descriptor(report_id: int, *, symbol: str = "990519", pdf_hash: str = "a" * 64) -> ReportDescriptor:
    return ReportDescriptor(
        report_id=report_id,
        market="CN",
        symbol=symbol,
        company_name=None,
        report_year=2025,
        report_type="annual",
        announcement_date="2026-04-01",
        source_url="https://static.cninfo.com.cn/finalpage/2026-04-01/9999999999.PDF",
        pdf_hash=pdf_hash,
        report_title=f"{symbol} test annual",
    )


def make_drafts(report_id: int, count: int = 5, *, empty_at: int | None = None) -> list[ReportChunkDraft]:
    drafts = []
    for i in range(count):
        text = "" if empty_at == i else f"测试营业收入第{i}段 chunk text for {report_id}"
        drafts.append(
            ReportChunkDraft(
                report_id=report_id,
                chunk_index=i,
                page_start=i + 1,
                page_end=i + 1,
                section_title=None,
                text=text,
                text_hash=hashlib.sha256(f"{report_id}:{i}:{text}".encode()).hexdigest(),
                token_count=len(text),
                metadata_json={"symbol": "990519"},
            )
        )
    return drafts


def embeddings_for(drafts: list[ReportChunkDraft]) -> dict[str, list[float]]:
    return {d.text_hash: [0.1, 0.2, 0.3] for d in drafts}


def db_repo() -> Any:
    from app.services.company_v2_report_rag_db_repository import DatabaseCompanyV2ReportRagRepository

    return DatabaseCompanyV2ReportRagRepository()


def cleanup(report_ids: list[int]) -> None:
    """Hard-delete test rows for the given isolated report_ids."""
    import asyncio

    from sqlalchemy import delete

    from app.models.company_v2_report_rag import ReportRagChunk, ReportRagDocument

    repo = db_repo()

    async def _clean() -> None:
        maker = await repo._get_sessionmaker()
        async with maker() as session:
            await session.execute(delete(ReportRagChunk).where(ReportRagChunk.report_id.in_(report_ids)))
            await session.execute(delete(ReportRagDocument).where(ReportRagDocument.report_id.in_(report_ids)))
            await session.commit()

    repo._run(_clean())
