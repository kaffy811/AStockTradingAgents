from __future__ import annotations

import asyncio
import json
import os
import signal
import time
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

    async def fake_release_run_leases(job_ids):
        return len(job_ids)

    async def fake_cancel_job(job_id: str, symbol: str):
        cancelled.append(job_id)

    async def fake_count_active_leases(job_ids=None):
        return 0

    async def fake_count_stale_leases(job_ids=None):
        return 0

    async def fake_dispose():
        disposals.append("disposed")

    async def fake_worker_loop(
        *,
        worker_id,
        metrics,
        stop_event,
        active_claims,
        poll_interval_seconds,
        lease_seconds,
        heartbeat_seconds,
        max_jobs_per_cycle,
        sample_interval_seconds,
        requester_scope=None,
        requester_run_id=None,
        allowed_job_ids=None,
    ):
        invocations[worker_id] = invocations.get(worker_id, 0) + 1
        assert requester_scope == soak.JOB_SCOPE
        assert requester_run_id is not None
        assert allowed_job_ids == {"job-601686", "job-600519"}
        claimed_job_id = f"{worker_id}-job-{invocations[worker_id]}"
        metrics.record_claim(claimed_job_id, 1.5, active_claims)
        metrics.jobs_observed += 1
        metrics.shadow_observation_count += 1
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
    monkeypatch.setattr(soak, "_release_run_leases", fake_release_run_leases)
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
    assert payload["metrics"]["unknown_jobs_modified"] == 0
    assert payload["actual_duration_seconds"] >= 1
    assert len(created) == 2
    assert len(cancelled) == 2
    assert cleaned == []
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


def test_duration_three_seconds_controls_main_lifecycle(monkeypatch):
    created = []
    cancelled = []

    async def fake_resolve_latest_report(symbol: str):
        return SimpleNamespace(id=1, ts_code=f"{symbol}.SH", report_type="annual", report_year=2025)

    async def fake_insert_soak_job(report, *, run_id: str, symbol: str):
        payload = {"job_id": f"job-{symbol}", "symbol": symbol, "report_id": report.id}
        created.append(payload)
        return payload

    async def fake_worker_loop(**kwargs):
        stop_event = kwargs["stop_event"]
        while not stop_event.is_set():
            await asyncio.sleep(0.05)

    monkeypatch.setattr(soak, "_resolve_latest_report", fake_resolve_latest_report)
    monkeypatch.setattr(soak, "_insert_soak_job", fake_insert_soak_job)
    monkeypatch.setattr(soak, "_preexisting_active_jobs", lambda scope: _async_value([]))
    monkeypatch.setattr(soak, "_release_run_leases", lambda job_ids: _async_value(len(job_ids)))
    monkeypatch.setattr(soak, "_cancel_job", lambda job_id, symbol: _async_append(cancelled, job_id))
    monkeypatch.setattr(soak, "_count_active_leases", lambda job_ids=None: _async_value(0))
    monkeypatch.setattr(soak, "_count_stale_leases", lambda job_ids=None: _async_value(0))
    monkeypatch.setattr(soak, "_worker_loop", fake_worker_loop)

    args = soak.parse_args(
        [
            "--duration-seconds",
            "3",
            "--worker-count",
            "1",
            "--poll-interval-seconds",
            "0.05",
            "--sample-interval-seconds",
            "1",
            "--symbols",
            "601686",
        ]
    )
    started = time.perf_counter()
    payload = asyncio.run(soak.run_soak(args))
    wall_seconds = time.perf_counter() - started
    assert payload["status"] == "passed"
    assert 2.8 <= payload["actual_duration_seconds"] <= 4.5
    assert 2.8 <= wall_seconds <= 4.5
    assert len(created) == 1
    assert cancelled == ["job-601686"]


def test_max_attempts_exhaustion_does_not_stop_shadow_soak(monkeypatch):
    observations = 0

    async def fake_resolve_latest_report(symbol: str):
        return SimpleNamespace(id=1, ts_code=f"{symbol}.SH", report_type="annual", report_year=2025)

    async def fake_insert_soak_job(report, *, run_id: str, symbol: str):
        return {"job_id": f"job-{symbol}", "symbol": symbol, "report_id": report.id}

    async def fake_worker_loop(**kwargs):
        nonlocal observations
        metrics = kwargs["metrics"]
        stop_event = kwargs["stop_event"]
        while not stop_event.is_set():
            observations += 1
            metrics.jobs_observed += 1
            metrics.shadow_observation_count += 1
            await asyncio.sleep(0.05)

    monkeypatch.setattr(soak, "_resolve_latest_report", fake_resolve_latest_report)
    monkeypatch.setattr(soak, "_insert_soak_job", fake_insert_soak_job)
    monkeypatch.setattr(soak, "_preexisting_active_jobs", lambda scope: _async_value([]))
    monkeypatch.setattr(soak, "_release_run_leases", lambda job_ids: _async_value(len(job_ids)))
    monkeypatch.setattr(soak, "_cancel_job", lambda job_id, symbol: _async_value(None))
    monkeypatch.setattr(soak, "_count_active_leases", lambda job_ids=None: _async_value(0))
    monkeypatch.setattr(soak, "_count_stale_leases", lambda job_ids=None: _async_value(0))
    monkeypatch.setattr(soak, "_worker_loop", fake_worker_loop)

    args = soak.parse_args(["--duration-seconds", "1", "--worker-count", "1", "--symbols", "601686"])
    payload = asyncio.run(soak.run_soak(args))
    assert payload["status"] == "passed"
    assert observations > 3
    assert payload["metrics"]["shadow_observation_count"] > 3
    assert payload["real_execution_count"] == 0


def test_worker_loop_continues_polling_without_eligible_jobs(monkeypatch):
    calls = 0
    stop_event = asyncio.Event()
    metrics = soak.SoakMetrics(duration_seconds=1, worker_count=1)

    async def fake_claim(**kwargs):
        nonlocal calls
        calls += 1
        if calls >= 3:
            stop_event.set()
        return None

    monkeypatch.setattr(soak.company_v2_financial_fusion_worker_service, "claim_next_job", fake_claim)
    asyncio.run(
        soak._worker_loop(
            worker_id="worker-a",
            metrics=metrics,
            stop_event=stop_event,
            active_claims=set(),
            poll_interval_seconds=0.05,
            lease_seconds=1,
            heartbeat_seconds=1,
            max_jobs_per_cycle=1,
            sample_interval_seconds=1,
            requester_scope=soak.JOB_SCOPE,
            requester_run_id="run-123",
            allowed_job_ids={"job-1"},
        )
    )
    assert calls >= 3


def test_worker_task_exception_marks_soak_failed_and_cleans_up(monkeypatch):
    cancelled = []
    invocations = 0

    async def fake_resolve_latest_report(symbol: str):
        return SimpleNamespace(id=1, ts_code=f"{symbol}.SH", report_type="annual", report_year=2025)

    async def fake_insert_soak_job(report, *, run_id: str, symbol: str):
        return {"job_id": f"job-{symbol}", "symbol": symbol, "report_id": report.id}

    async def fake_worker_loop(**kwargs):
        nonlocal invocations
        invocations += 1
        if invocations == 1:
            raise RuntimeError("boom")
        stop_event = kwargs["stop_event"]
        while not stop_event.is_set():
            await asyncio.sleep(0.05)

    monkeypatch.setattr(soak, "_resolve_latest_report", fake_resolve_latest_report)
    monkeypatch.setattr(soak, "_insert_soak_job", fake_insert_soak_job)
    monkeypatch.setattr(soak, "_preexisting_active_jobs", lambda scope: _async_value([]))
    monkeypatch.setattr(soak, "_release_run_leases", lambda job_ids: _async_value(len(job_ids)))
    monkeypatch.setattr(soak, "_cancel_job", lambda job_id, symbol: _async_append(cancelled, job_id))
    monkeypatch.setattr(soak, "_count_active_leases", lambda job_ids=None: _async_value(0))
    monkeypatch.setattr(soak, "_count_stale_leases", lambda job_ids=None: _async_value(0))
    monkeypatch.setattr(soak, "_worker_loop", fake_worker_loop)

    args = soak.parse_args(["--duration-seconds", "1", "--worker-count", "1", "--symbols", "601686"])
    payload = asyncio.run(soak.run_soak(args))
    assert payload["status"] == "failed"
    assert any(error["code"] == "WORKER_TASK_FAILED" for error in payload["errors"])
    assert cancelled == ["job-601686"]
    assert payload["active_leases_end"] == 0


def test_sigterm_path_marks_failed_and_runs_cleanup(monkeypatch):
    cancelled = []

    async def fake_resolve_latest_report(symbol: str):
        return SimpleNamespace(id=1, ts_code=f"{symbol}.SH", report_type="annual", report_year=2025)

    async def fake_insert_soak_job(report, *, run_id: str, symbol: str):
        return {"job_id": f"job-{symbol}", "symbol": symbol, "report_id": report.id}

    async def fake_worker_loop(**kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
        stop_event = kwargs["stop_event"]
        while not stop_event.is_set():
            await asyncio.sleep(0.05)

    monkeypatch.setattr(soak, "_resolve_latest_report", fake_resolve_latest_report)
    monkeypatch.setattr(soak, "_insert_soak_job", fake_insert_soak_job)
    monkeypatch.setattr(soak, "_preexisting_active_jobs", lambda scope: _async_value([]))
    monkeypatch.setattr(soak, "_release_run_leases", lambda job_ids: _async_value(len(job_ids)))
    monkeypatch.setattr(soak, "_cancel_job", lambda job_id, symbol: _async_append(cancelled, job_id))
    monkeypatch.setattr(soak, "_count_active_leases", lambda job_ids=None: _async_value(0))
    monkeypatch.setattr(soak, "_count_stale_leases", lambda job_ids=None: _async_value(0))
    monkeypatch.setattr(soak, "_worker_loop", fake_worker_loop)

    args = soak.parse_args(["--duration-seconds", "5", "--worker-count", "1", "--symbols", "601686"])
    payload = asyncio.run(soak.run_soak(args))
    assert payload["status"] == "failed"
    assert payload["exit_reason"] == "signal:SIGTERM"
    assert "SHADOW_SOAK_INTERRUPTED" in payload["blocking_issues"]
    assert cancelled == ["job-601686"]


def test_running_artifact_overwrites_old_run_id_before_final(monkeypatch, tmp_path):
    json_path = tmp_path / "shadow.json"
    md_path = tmp_path / "shadow.md"
    json_path.write_text(json.dumps({"status": "passed", "run_id": "old-run"}, ensure_ascii=False), encoding="utf-8")
    observed_running = {}

    async def fake_run_soak(args, *, run_id=None, started_at=None, process_pid=None, git_commit=None):
        observed_running.update(json.loads(json_path.read_text(encoding="utf-8")))
        metrics = soak.SoakMetrics(duration_seconds=int(args.duration_seconds), worker_count=int(args.worker_count))
        metrics.active_leases_end = 0
        metrics.stale_leases_end = 0
        return soak._build_payload(
            status="passed",
            run_id=run_id,
            symbols=["601686"],
            created_jobs=[],
            metrics=metrics,
            blocking_issues=[],
            started_at=started_at,
            finished_at=soak._now(),
            requested_duration_seconds=float(args.duration_seconds),
            actual_duration_seconds=1.0,
            exit_reason="duration_elapsed",
            process_pid=process_pid,
            git_commit=git_commit,
        )

    monkeypatch.setattr(soak, "run_soak", fake_run_soak)
    rc = soak.main(
        [
            "--duration-seconds",
            "1",
            "--symbols",
            "601686",
            "--out-json",
            str(json_path),
            "--out-md",
            str(md_path),
        ]
    )
    final_payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert observed_running["status"] == "running"
    assert observed_running["run_id"] != "old-run"
    assert final_payload["status"] == "passed"
    assert final_payload["run_id"] == observed_running["run_id"]
    assert final_payload["actual_duration_seconds"] == 1.0


def test_worker_loop_receives_soak_scope_filters(monkeypatch):
    calls = []
    stop_event = asyncio.Event()
    metrics = soak.SoakMetrics(duration_seconds=1, worker_count=1)

    async def fake_claim(*, db, worker_id, lease_seconds=None, heartbeat_seconds=None, execution_mode=soak.SHADOW_EXECUTION_MODE, max_attempts=None, requester_scope=None, requester_run_id=None, allowed_job_ids=None):
        calls.append(
            {
                "worker_id": worker_id,
                "requester_scope": requester_scope,
                "requester_run_id": requester_run_id,
                "allowed_job_ids": sorted(list(allowed_job_ids or [])),
            }
        )
        stop_event.set()
        return None

    monkeypatch.setattr(soak.company_v2_financial_fusion_worker_service, "claim_next_job", fake_claim)
    asyncio.run(
        soak._worker_loop(
            worker_id="worker-a",
            metrics=metrics,
            stop_event=stop_event,
            active_claims=set(),
            poll_interval_seconds=0.1,
            lease_seconds=1,
            heartbeat_seconds=1,
            max_jobs_per_cycle=1,
            sample_interval_seconds=1,
            requester_scope=soak.JOB_SCOPE,
            requester_run_id="run-123",
            allowed_job_ids={"job-1", "job-2"},
        )
    )
    assert calls and calls[0]["requester_scope"] == soak.JOB_SCOPE
    assert calls[0]["requester_run_id"] == "run-123"
    assert calls[0]["allowed_job_ids"] == ["job-1", "job-2"]


def test_soak_claim_scope_validation_rejects_wrong_scope():
    job = SimpleNamespace(
        job_id="job-bad",
        requester_scope="manual",
        requester_metadata_json=json.dumps({"run_id": "other"}, ensure_ascii=False),
    )
    with pytest.raises(RuntimeError, match="scope isolation violation"):
        soak._assert_soak_claim_scope(
            job,
            requester_scope=soak.JOB_SCOPE,
            requester_run_id="run-123",
            allowed_job_ids={"job-bad"},
        )


async def _async_value(value):
    return value


async def _async_append(target, value):
    target.append(value)
