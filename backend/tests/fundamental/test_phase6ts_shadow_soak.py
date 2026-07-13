from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from scripts import company_v2_financial_fusion_phase6ts_shadow_soak as soak


def test_percentile_and_sanitize():
    assert soak.percentile([], 50) is None
    assert soak.percentile([10.0], 50) == 10.0
    assert soak.percentile([10.0, 20.0, 30.0], 50) == 20.0
    sanitized = soak._sanitize(
        {
            "database_url": "postgresql://secret",
            "token": "secret",
            "path": "/Users/kaffy/Documents/TradingAgents",
            "nested": {"local_path": "/tmp/company_v2"},
        }
    )
    assert "database_url" not in sanitized
    assert "token" not in sanitized
    assert "path" not in sanitized
    assert "local_path" not in sanitized["nested"]


def test_run_soak_hermetic_controls_restart_and_reconnect(monkeypatch):
    created = []
    cancelled = []
    cleaned = []
    disposals = []
    invocations: dict[str, int] = {}

    async def fake_resolve_latest_report(symbol: str):
        return SimpleNamespace(id=1, ts_code=f"{symbol}.SH", report_type="annual", report_year=2025)

    async def fake_insert_soak_job(report, *, run_id: str, symbol: str):
        payload = {"job_id": f"job-{symbol}", "symbol": symbol, "report_id": report.id}
        created.append(payload)
        return payload

    async def fake_preexisting_active_jobs(scope: str):
        return []

    async def fake_cleanup_jobs(job_ids):
        cleaned.extend(job_ids)

    async def fake_cancel_job(job_id: str, symbol: str):
        cancelled.append(job_id)

    async def fake_count_active_leases():
        return 0

    async def fake_count_stale_leases():
        return 0

    async def fake_dispose():
        disposals.append("disposed")

    async def fake_worker_loop(*, worker_id, metrics, stop_event, active_claims, poll_interval_seconds, lease_seconds, heartbeat_seconds, max_jobs_per_cycle, sample_interval_seconds):
        invocations[worker_id] = invocations.get(worker_id, 0) + 1
        claimed_job_id = f"{worker_id}-job-{invocations[worker_id]}"
        metrics.record_claim(claimed_job_id, 1.5, active_claims)
        metrics.jobs_observed += 1
        metrics.observation_rows_written += 1
        metrics.real_execution_count += 0
        metrics.provider_call_count += 0
        metrics.rag_query_count += 0
        metrics.extractor_call_count += 0
        metrics.fusion_result_write_count += 0
        await asyncio.sleep(0.4)
        metrics.record_release(claimed_job_id, active_claims)
        while not stop_event.is_set():
            await asyncio.sleep(0.05)

    monkeypatch.setattr(soak, "_resolve_latest_report", fake_resolve_latest_report)
    monkeypatch.setattr(soak, "_insert_soak_job", fake_insert_soak_job)
    monkeypatch.setattr(soak, "_preexisting_active_jobs", fake_preexisting_active_jobs)
    monkeypatch.setattr(soak, "_cleanup_jobs", fake_cleanup_jobs)
    monkeypatch.setattr(soak, "_cancel_job", fake_cancel_job)
    monkeypatch.setattr(soak, "_count_active_leases", fake_count_active_leases)
    monkeypatch.setattr(soak, "_count_stale_leases", fake_count_stale_leases)
    monkeypatch.setattr(soak, "async_engine", SimpleNamespace(dispose=fake_dispose))
    monkeypatch.setattr(soak, "_worker_loop", fake_worker_loop)

    args = soak.parse_args(
        [
            "--duration-seconds",
            "1",
            "--worker-count",
            "2",
            "--poll-interval-seconds",
            "0.1",
            "--lease-seconds",
            "2",
            "--heartbeat-seconds",
            "1",
            "--max-jobs-per-cycle",
            "1",
            "--sample-interval-seconds",
            "1",
                "--symbols",
                "601686,600519",
                "--inject-worker-restart-at",
                "0.2",
                "--inject-db-reconnect-at",
                "0.4",
            ]
        )
    payload = asyncio.run(soak.run_soak(args))
    assert payload["status"] == "passed"
    assert payload["shadow_soak_completed"] is True
    assert payload["real_execution_count"] == 0
    assert payload["metrics"]["worker_restart_count"] >= 1
    assert payload["metrics"]["db_reconnect_count"] == 1
    assert payload["metrics"]["duplicate_claim_count"] == 0
    assert payload["metrics"]["active_leases_end"] == 0
    assert payload["metrics"]["stale_leases_end"] == 0
    assert payload["metrics"]["provider_call_count"] == 0
    assert payload["metrics"]["rag_query_count"] == 0
    assert payload["metrics"]["extractor_call_count"] == 0
    assert payload["metrics"]["fusion_result_write_count"] == 0
    assert len(created) == 2
    assert len(cancelled) == 2
    assert cleaned == [item["job_id"] for item in created]
    assert disposals == ["disposed"]


def test_run_soak_blocks_preexisting_active_jobs(monkeypatch):
    async def fake_preexisting_active_jobs(scope: str):
        return ["job-x"]

    inserted = []

    async def fake_insert_soak_job(report, *, run_id: str, symbol: str):
        inserted.append(symbol)
        return {"job_id": f"job-{symbol}", "symbol": symbol, "report_id": report.id}

    monkeypatch.setattr(soak, "_preexisting_active_jobs", fake_preexisting_active_jobs)
    monkeypatch.setattr(soak, "_insert_soak_job", fake_insert_soak_job)
    monkeypatch.setattr(soak, "_resolve_latest_report", lambda symbol: None)

    args = soak.parse_args(["--duration-seconds", "1", "--symbols", "601686"])
    payload = asyncio.run(soak.run_soak(args))
    assert payload["status"] == "failed"
    assert payload["blocking_issues"] == ["PREEXISTING_ACTIVE_JOBS"]
    assert payload["shadow_soak_completed"] is False
    assert inserted == []
