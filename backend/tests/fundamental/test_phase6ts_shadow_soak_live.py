from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob
from app.models.company_v2_financial_fusion_worker_observation import CompanyV2FinancialFusionWorkerObservation
from app.models.report_document import ReportDocument
from scripts import company_v2_financial_fusion_phase6ts_shadow_soak as soak

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


async def _cleanup_scope(scope: str) -> None:
    async with LiveSessionLocal() as db:
        job_ids = (
            await db.execute(
                select(CompanyV2FinancialFusionJob.job_id).where(CompanyV2FinancialFusionJob.requester_scope == scope)
            )
        ).scalars().all()
        if job_ids:
            await db.execute(delete(CompanyV2FinancialFusionWorkerObservation).where(CompanyV2FinancialFusionWorkerObservation.job_id.in_(job_ids)))
            await db.execute(delete(CompanyV2FinancialFusionJob).where(CompanyV2FinancialFusionJob.job_id.in_(job_ids)))
            await db.commit()


async def _count_active_scope_jobs(scope: str) -> int:
    async with LiveSessionLocal() as db:
        result = await db.execute(
            select(CompanyV2FinancialFusionJob).where(
                CompanyV2FinancialFusionJob.requester_scope == scope,
                CompanyV2FinancialFusionJob.status.in_(["queued", "running"]),
            )
        )
        return len(list(result.scalars().all()))


async def test_live_shadow_soak_short_run_with_restart_and_reconnect(monkeypatch, tmp_path):
    await _cleanup_scope(soak.JOB_SCOPE)
    symbols = ["601686", "600519"]
    monkeypatch.setenv("COMPANY_V2_FINANCIAL_FUSION_SYMBOL_ALLOWLIST", ",".join(symbols))
    monkeypatch.setenv("COMPANY_V2_FINANCIAL_FUSION_ENABLED", "true")
    monkeypatch.setenv("COMPANY_V2_FINANCIAL_FUSION_STAGE3_AUTHORIZED", "false")
    monkeypatch.setenv("COMPANY_V2_FINANCIAL_FUSION_WORKER_ENABLED", "true")
    monkeypatch.setenv("COMPANY_V2_FINANCIAL_FUSION_WORKER_MODE", "shadow")
    monkeypatch.setenv("COMPANY_V2_FINANCIAL_FUSION_AUTO_RUN", "false")
    monkeypatch.setenv("COMPANY_V2_FINANCIAL_FUSION_ROLLOUT_PERCENT", "0")
    for symbol in symbols:
        await _latest_report(symbol)
    json_path = tmp_path / "acceptance.json"
    md_path = tmp_path / "acceptance.md"
    try:
        command = [
            sys.executable,
            "scripts/company_v2_financial_fusion_phase6ts_shadow_soak.py",
            "--duration-seconds",
            "8",
            "--worker-count",
            "2",
            "--poll-interval-seconds",
            "0.5",
            "--lease-seconds",
            "3",
            "--heartbeat-seconds",
            "1",
            "--max-jobs-per-cycle",
            "1",
            "--sample-interval-seconds",
            "1",
            "--inject-worker-restart-at",
            "2",
            "--inject-db-reconnect-at",
            "4",
            "--symbols",
            ",".join(symbols),
            "--out-json",
            str(json_path),
            "--out-md",
            str(md_path),
        ]
        env = os.environ.copy()
        env["COMPANY_V2_FINANCIAL_FUSION_SYMBOL_ALLOWLIST"] = ",".join(symbols)
        env["COMPANY_V2_FINANCIAL_FUSION_ENABLED"] = "true"
        env["COMPANY_V2_FINANCIAL_FUSION_STAGE3_AUTHORIZED"] = "false"
        env["COMPANY_V2_FINANCIAL_FUSION_WORKER_ENABLED"] = "true"
        env["COMPANY_V2_FINANCIAL_FUSION_WORKER_MODE"] = "shadow"
        env["COMPANY_V2_FINANCIAL_FUSION_AUTO_RUN"] = "false"
        env["COMPANY_V2_FINANCIAL_FUSION_ROLLOUT_PERCENT"] = "0"
        subprocess.run(command, cwd=str(Path(__file__).resolve().parents[2]), check=True, env=env)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["status"] == "passed"
        assert payload["shadow_soak_completed"] is True
        assert payload["real_execution_count"] == 0
        assert payload["provider_call_count"] == 0
        assert payload["rag_query_count"] == 0
        assert payload["extractor_call_count"] == 0
        assert payload["fusion_result_write_count"] == 0
        assert payload["metrics"]["duplicate_claim_count"] == 0
        assert payload["metrics"]["active_leases_end"] == 0
        assert payload["metrics"]["stale_leases_end"] == 0
        assert payload["metrics"]["worker_restart_count"] >= 1
        assert payload["metrics"]["db_reconnect_count"] == 1
        assert payload["metrics"]["jobs_created"] == len(symbols)
        assert payload["metrics"]["jobs_cancelled"] == len(symbols)
        assert len(payload["created_jobs"]) == len(symbols)
        assert await _count_active_scope_jobs(soak.JOB_SCOPE) == 0
    finally:
        await _cleanup_scope(soak.JOB_SCOPE)
