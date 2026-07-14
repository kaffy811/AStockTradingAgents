from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob
from app.models.company_v2_financial_fusion_worker_observation import CompanyV2FinancialFusionWorkerObservation
from app.models.report_document import ReportDocument
from app.services.company_v2_financial_fusion_worker_service import company_v2_financial_fusion_worker_service

pytestmark = [pytest.mark.live_supabase, pytest.mark.asyncio(loop_scope="module")]

_live_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0},
)
LiveSessionLocal = async_sessionmaker(_live_engine, expire_on_commit=False)


async def _latest_report(symbol: str) -> ReportDocument:
    async with LiveSessionLocal() as db:
        result = await db.execute(select(ReportDocument).where(ReportDocument.ts_code.like(f"{symbol}.%")))
        docs = list(result.scalars().all())
        annuals = [doc for doc in docs if (doc.report_type or "").lower() == "annual"]
        pool = annuals or docs
        assert pool, f"no report documents found for {symbol}"
        return sorted(pool, key=lambda item: ((item.report_year or 0), item.id), reverse=True)[0]


async def _insert_job(report: ReportDocument, *, job_id: str, status: str = "queued") -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with LiveSessionLocal() as db:
        db.add(
            CompanyV2FinancialFusionJob(
                job_id=job_id,
                market="CN",
                symbol=report.ts_code.split(".")[0],
                report_id=report.id,
                report_year=report.report_year,
                report_type=report.report_type,
                requested_fields_json=json.dumps(["revenue"], ensure_ascii=False),
                request_fingerprint=hashlib.sha256(f"{job_id}|{report.id}".encode("utf-8")).hexdigest(),
                requester_scope="phase6tr_live",
                status=status,
                progress=0.0,
                current_stage="queued",
                cache_hit=0,
                retryable=0,
                repository_backend="database",
                extractor_version="phase6tr",
                requester_metadata_json=json.dumps({"phase": "6tr"}, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
        )
        await db.commit()


async def _cleanup(job_ids: list[str]) -> None:
    async with LiveSessionLocal() as db:
        await db.execute(delete(CompanyV2FinancialFusionWorkerObservation).where(CompanyV2FinancialFusionWorkerObservation.job_id.in_(job_ids)))
        await db.execute(delete(CompanyV2FinancialFusionJob).where(CompanyV2FinancialFusionJob.job_id.in_(job_ids)))
        await db.commit()


async def _get_job(job_id: str) -> CompanyV2FinancialFusionJob | None:
    async with LiveSessionLocal() as db:
        result = await db.execute(select(CompanyV2FinancialFusionJob).where(CompanyV2FinancialFusionJob.job_id == job_id))
        return result.scalars().first()


async def _count_active_leases() -> int:
    async with LiveSessionLocal() as db:
        result = await db.execute(
            select(CompanyV2FinancialFusionJob).where(
                CompanyV2FinancialFusionJob.claimed_by.is_not(None),
                CompanyV2FinancialFusionJob.status == "queued",
            )
        )
        return len(list(result.scalars().all()))


async def _count_active_leases_for(job_ids: list[str]) -> int:
    async with LiveSessionLocal() as db:
        result = await db.execute(
            select(CompanyV2FinancialFusionJob).where(
                CompanyV2FinancialFusionJob.job_id.in_(job_ids),
                CompanyV2FinancialFusionJob.claimed_by.is_not(None),
                CompanyV2FinancialFusionJob.status == "queued",
            )
        )
        return len(list(result.scalars().all()))


async def test_live_claim_is_atomic_and_skip_locked():
    report = await _latest_report("600519")
    job_id = f"phase6tr-{uuid4().hex}"
    await _insert_job(report, job_id=job_id)
    try:
        async def _one(worker_id: str):
            async with LiveSessionLocal() as db:
                return await company_v2_financial_fusion_worker_service.claim_next_job(
                    db=db,
                    worker_id=worker_id,
                    lease_seconds=30,
                    requester_scope="phase6tr_live",
                    allowed_job_ids=[job_id],
                )

        results = await asyncio.gather(_one("worker-a"), _one("worker-b"))
        claimed = [item for item in results if item is not None]
        assert len(claimed) == 1
        assert claimed[0]["job_id"] == job_id
        assert claimed[0]["execution_mode"] == "shadow"
        job = await _get_job(job_id)
        assert job is not None and job.claimed_by is not None
    finally:
        await _cleanup([job_id])


async def test_live_lease_expiry_allows_reclaim_and_blocks_old_heartbeat():
    report = await _latest_report("600519")
    job_id = f"phase6tr-{uuid4().hex}"
    await _insert_job(report, job_id=job_id)
    try:
        async with LiveSessionLocal() as db:
            claim = await company_v2_financial_fusion_worker_service.claim_next_job(
                db=db,
                worker_id="worker-a",
                lease_seconds=30,
                requester_scope="phase6tr_live",
                allowed_job_ids=[job_id],
            )
        assert claim and claim["job_id"] == job_id

        async with LiveSessionLocal() as db:
            assert (
                await company_v2_financial_fusion_worker_service.claim_next_job(
                    db=db,
                    worker_id="worker-b",
                    lease_seconds=30,
                    requester_scope="phase6tr_live",
                    allowed_job_ids=[job_id],
                )
                is None
            )

        async with LiveSessionLocal() as db:
            await db.execute(
                update(CompanyV2FinancialFusionJob)
                .where(CompanyV2FinancialFusionJob.job_id == job_id)
                .values(
                    lease_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1),
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            await db.commit()

        async with LiveSessionLocal() as db:
            assert await company_v2_financial_fusion_worker_service.heartbeat(db=db, job_id=job_id, worker_id="worker-a", lease_seconds=30) is None

        async with LiveSessionLocal() as db:
            reclaimed = await company_v2_financial_fusion_worker_service.claim_next_job(
                db=db,
                worker_id="worker-b",
                lease_seconds=30,
                requester_scope="phase6tr_live",
                allowed_job_ids=[job_id],
            )
        assert reclaimed and reclaimed["claimed_by"] == "worker-b"
        job = await _get_job(job_id)
        assert job is not None and job.attempt_count == 0
    finally:
        await _cleanup([job_id])


async def test_live_shadow_cycle_writes_observation_and_releases_active_lease():
    report = await _latest_report("600519")
    job_id = f"phase6tr-{uuid4().hex}"
    await _insert_job(report, job_id=job_id)
    try:
        async with LiveSessionLocal() as db:
            payload = await company_v2_financial_fusion_worker_service.run_shadow_cycle(
                db=db,
                worker_id="worker-shadow",
                max_jobs=1,
                requester_scope="phase6tr_live",
                allowed_job_ids={job_id},
            )
        assert payload["real_execution_count"] == 0
        assert payload["shadow_mode_verified"] is True
        async with LiveSessionLocal() as db:
            obs = await db.execute(select(CompanyV2FinancialFusionWorkerObservation).where(CompanyV2FinancialFusionWorkerObservation.job_id == job_id))
            observation = obs.scalars().first()
            assert observation is not None
            assert observation.would_execute is False
            assert observation.stage3_authorized is False
            assert observation.provider_calls == 0
            assert observation.rag_query_calls == 0
            assert observation.extractor_calls == 0
            assert observation.fusion_calls == 0
        assert await _count_active_leases_for([job_id]) == 0
        job = await _get_job(job_id)
        assert job is not None
        assert job.claimed_by is None
        assert job.execution_mode == "shadow"
        assert job.attempt_count == 0
    finally:
        await _cleanup([job_id])


async def test_live_cancelled_and_completed_jobs_are_never_claimed():
    report = await _latest_report("600519")
    cancelled_id = f"phase6tr-{uuid4().hex}"
    completed_id = f"phase6tr-{uuid4().hex}"
    await _insert_job(report, job_id=cancelled_id, status="cancelled")
    await _insert_job(report, job_id=completed_id, status="completed")
    try:
        async with LiveSessionLocal() as db:
            assert (
                await company_v2_financial_fusion_worker_service.claim_next_job(
                    db=db,
                    worker_id="worker-a",
                    requester_scope="phase6tr_live",
                    allowed_job_ids=[cancelled_id, completed_id],
                )
                is None
            )
    finally:
        await _cleanup([cancelled_id, completed_id])
