from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.company_v2_financial_fusion_worker_service import (
    SHADOW_EXECUTION_MODE,
    WORKER_VERSION,
    company_v2_financial_fusion_worker_service,
)


class _FakeTxn:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSelectResult:
    def __init__(self, row):
        self._row = row

    def scalars(self):
        return self

    def first(self):
        return self._row


class _FakeUpdateResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def first(self):
        return self._value


class _FakeSession:
    def __init__(self, responses, dialect_name: str = "postgresql"):
        self.responses = list(responses)
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
        self.added = []
        self.flushed = 0
        self._in_transaction = False

    def begin(self):
        return _FakeTxn()

    async def execute(self, _stmt):
        if not self.responses:
            raise AssertionError("unexpected execute")
        return self.responses.pop(0)

    async def flush(self):
        self.flushed += 1

    def add(self, obj):
        self.added.append(obj)

    def in_transaction(self):
        return self._in_transaction

    async def commit(self):
        self._in_transaction = False

    async def rollback(self):
        self._in_transaction = False


def _make_job_row(**overrides):
    defaults = {
        "job_id": "job-1",
        "symbol": "600519",
        "report_id": 2,
        "report_year": 2025,
        "requester_scope": "manual",
        "status": "queued",
        "attempt_count": 0,
        "claimed_by": None,
        "claimed_at": None,
        "heartbeat_at": None,
        "lease_expires_at": None,
        "execution_mode": None,
        "worker_version": None,
        "rollout_percent_at_claim": None,
        "auto_run_at_claim": None,
        "last_error_message_sanitized": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_report_row(**overrides):
    defaults = {
        "id": 2,
        "ts_code": "600519.SH",
        "download_status": "downloaded",
        "local_path": "/tmp/redacted/report.pdf",
        "pdf_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/test.pdf",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/test.pdf",
        "rag_status": "indexed",
        "chunk_count": 12,
        "parsed": True,
        "parse_status": "parsed",
        "report_year": 2025,
        "report_type": "annual",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_claim_next_job_assigns_shadow_lease(monkeypatch):
    row = _make_job_row()
    db = _FakeSession([_FakeSelectResult(row)])
    monkeypatch.setattr(settings, "company_v2_financial_fusion_worker_lease_seconds", 60, raising=False)
    payload = asyncio.run(
        company_v2_financial_fusion_worker_service.claim_next_job(db=db, worker_id="worker-a", execution_mode=SHADOW_EXECUTION_MODE)
    )
    assert payload["job_id"] == "job-1"
    assert payload["claimed_by"] == "worker-a"
    assert payload["attempt_count"] == 0
    assert row.attempt_count == 0
    assert payload["execution_mode"] == SHADOW_EXECUTION_MODE
    assert row.claimed_by == "worker-a"
    assert row.worker_version == WORKER_VERSION
    assert db.flushed == 1


def test_claim_next_job_increments_attempt_only_for_real_execution(monkeypatch):
    row = _make_job_row()
    db = _FakeSession([_FakeSelectResult(row)])
    monkeypatch.setattr(settings, "company_v2_financial_fusion_worker_lease_seconds", 60, raising=False)
    payload = asyncio.run(
        company_v2_financial_fusion_worker_service.claim_next_job(db=db, worker_id="worker-a", execution_mode="canary")
    )
    assert payload["attempt_count"] == 1
    assert row.attempt_count == 1
    assert payload["execution_mode"] == "canary"


def test_shadow_claim_ignores_real_max_attempts_budget(monkeypatch):
    row = _make_job_row(attempt_count=3, max_attempts=3)
    db = _FakeSession([_FakeSelectResult(row)])
    monkeypatch.setattr(settings, "company_v2_financial_fusion_worker_lease_seconds", 60, raising=False)
    payload = asyncio.run(
        company_v2_financial_fusion_worker_service.claim_next_job(
            db=db,
            worker_id="worker-a",
            execution_mode=SHADOW_EXECUTION_MODE,
            max_attempts=3,
        )
    )
    assert payload["job_id"] == "job-1"
    assert payload["attempt_count"] == 3
    assert row.attempt_count == 3


def test_heartbeat_requires_owner_and_active_lease():
    db = _FakeSession([_FakeUpdateResult("job-1")])
    result = asyncio.run(
        company_v2_financial_fusion_worker_service.heartbeat(db=db, job_id="job-1", worker_id="worker-a", lease_seconds=30)
    )
    assert result["job_id"] == "job-1"
    assert result["worker_id"] == "worker-a"

    expired = _FakeSession([_FakeUpdateResult(None)])
    assert asyncio.run(
        company_v2_financial_fusion_worker_service.heartbeat(db=expired, job_id="job-1", worker_id="worker-a", lease_seconds=30)
    ) is None


def test_release_claim_writes_observation_and_clears_claim():
    db = _FakeSession([_FakeUpdateResult(("job-1", "queued", datetime.utcnow()))])
    observation_payload = {
        "symbol": "600519",
        "report_id": 2,
        "would_execute": False,
        "block_reason": "STAGE3_NOT_AUTHORIZED",
        "allowlist_match": True,
        "report_ready": True,
        "rag_ready": True,
        "structured_ready": True,
        "circuit_open": False,
        "auto_run": False,
        "rollout_percent": 0,
        "stage3_authorized": False,
        "worker_version": WORKER_VERSION,
        "execution_mode": SHADOW_EXECUTION_MODE,
        "provider_calls": 0,
        "rag_query_calls": 0,
        "extractor_calls": 0,
        "fusion_calls": 0,
    }
    result = asyncio.run(
        company_v2_financial_fusion_worker_service.release_claim(
            db=db,
            job_id="job-1",
            worker_id="worker-a",
            block_reason="STAGE3_NOT_AUTHORIZED",
            observation_payload=observation_payload,
        )
    )
    assert result["job_id"] == "job-1"
    assert len(db.added) == 1
    observation = db.added[0]
    assert observation.job_id == "job-1"
    assert observation.would_execute is False
    assert observation.block_reason == "STAGE3_NOT_AUTHORIZED"
    assert observation.worker_version == WORKER_VERSION
    assert observation.provider_calls == 0
    assert observation.rag_query_calls == 0
    assert observation.extractor_calls == 0
    assert observation.fusion_calls == 0


def test_evaluate_shadow_job_never_requests_real_execution(monkeypatch):
    job = _make_job_row()
    report = _make_report_row()
    db = _FakeSession([_FakeSelectResult(report), _FakeUpdateResult(("job-1", "queued", datetime.utcnow()))])
    monkeypatch.setattr(settings, "company_v2_financial_fusion_stage3_authorized", False, raising=False)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_auto_run", False, raising=False)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_rollout_percent", 0, raising=False)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_symbol_allowlist", "600519,300750", raising=False)
    payload = asyncio.run(
        company_v2_financial_fusion_worker_service.evaluate_shadow_job(db=db, job=job, worker_id="worker-a")
    )
    assert payload["would_execute"] is False
    assert payload["block_reason"] == "STAGE3_NOT_AUTHORIZED"
    assert payload["execution_mode"] == SHADOW_EXECUTION_MODE
    assert payload["worker_version"] == WORKER_VERSION
    assert payload["provider_calls"] == 0
    assert payload["rag_query_calls"] == 0
    assert payload["extractor_calls"] == 0
    assert payload["fusion_calls"] == 0


def test_run_shadow_cycle_reports_zero_real_execution(monkeypatch):
    async def fake_claim(
        *,
        db,
        worker_id,
        lease_seconds=None,
        heartbeat_seconds=None,
        execution_mode=SHADOW_EXECUTION_MODE,
        max_attempts=None,
        requester_scope=None,
        requester_run_id=None,
        allowed_job_ids=None,
    ):
        if not hasattr(fake_claim, "called"):
            fake_claim.called = True
            return {"job_id": "job-1", "symbol": "600519", "report_id": 2}
        return None

    async def fake_load_job(_db, _job_id):
        return _make_job_row()

    async def fake_eval(*, db, job, worker_id, expected_requester_scope=None, expected_requester_run_id=None, allowed_job_ids=None):
        return {"would_execute": False, "job_id": job.job_id}

    monkeypatch.setattr(company_v2_financial_fusion_worker_service, "claim_next_job", fake_claim)
    monkeypatch.setattr(company_v2_financial_fusion_worker_service, "_load_job", fake_load_job)
    monkeypatch.setattr(company_v2_financial_fusion_worker_service, "evaluate_shadow_job", fake_eval)
    db = _FakeSession([])
    payload = asyncio.run(company_v2_financial_fusion_worker_service.run_shadow_cycle(db=db, worker_id="worker-a", max_jobs=1))
    assert payload["real_execution_count"] == 0
    assert payload["shadow_mode_verified"] is True


def test_cli_rejects_non_shadow_modes(monkeypatch, tmp_path):
    from scripts import company_v2_financial_fusion_worker as cli

    args = cli.parse_args(
        [
            "--mode",
            "canary",
            "--out-json",
            str(tmp_path / "worker.json"),
            "--out-md",
            str(tmp_path / "worker.md"),
        ]
    )
    payload = asyncio.run(cli.run_worker(args))
    assert payload["status"] == "failed"
    assert payload["errors"][0]["code"] == "STAGE3_NOT_AUTHORIZED"


def test_cli_shadow_once_runs_without_real_execution(monkeypatch, tmp_path):
    from scripts import company_v2_financial_fusion_worker as cli

    class _FakeAsyncSession:
        def __init__(self):
            self.executed = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, _stmt):
            self.executed += 1
            class _Result:
                def scalars(self):
                    return self

                def all(self):
                    return []
            return _Result()

    class _FakeAsyncSessionLocal:
        def __call__(self):
            return _FakeAsyncSession()

    async def fake_cycle(*_args, **_kwargs):
        return {
            "claimed_jobs": [],
            "observations": [],
            "real_execution_count": 0,
            "shadow_mode_verified": True,
            "stage3_authorized": False,
            "auto_run": False,
            "rollout_percent": 0,
        }

    monkeypatch.setattr(cli, "AsyncSessionLocal", _FakeAsyncSessionLocal())
    monkeypatch.setattr(cli.company_v2_financial_fusion_worker_service, "run_shadow_cycle", fake_cycle)
    args = cli.parse_args(
        [
            "--mode",
            "shadow",
            "--once",
            "--out-json",
            str(tmp_path / "worker.json"),
            "--out-md",
            str(tmp_path / "worker.md"),
        ]
    )
    payload = asyncio.run(cli.run_worker(args))
    assert payload["status"] == "passed"
    assert payload["real_execution_count"] == 0
    assert payload["shadow_mode_verified"] is True


def test_shadow_artifact_sanitization():
    from scripts.company_v2_financial_fusion_worker import _sanitize

    payload = _sanitize({"database_url": "postgresql://secret", "path": "/Users/kaffy/Documents/TradingAgents/x"})
    assert "database_url" not in payload
    assert "path" not in payload or payload["path"] == "[redacted]"
