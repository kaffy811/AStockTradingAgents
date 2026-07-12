from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import settings

from scripts import company_v2_financial_fusion_phase6tq_acceptance as script


class _FakeResponse:
    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, *, post_responses=None, get_responses=None):
        self.post_responses = list(post_responses or [])
        self.get_responses = list(get_responses or [])
        self.calls: list[tuple[str, str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None):
        self.calls.append(("POST", url, json))
        if not self.post_responses:
            raise AssertionError(f"unexpected POST {url}")
        return self.post_responses.pop(0)

    async def get(self, url):
        self.calls.append(("GET", url, None))
        if not self.get_responses:
            raise AssertionError(f"unexpected GET {url}")
        return self.get_responses.pop(0)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows_by_query):
        self.rows_by_query = list(rows_by_query)
        self.executed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        if self.executed >= len(self.rows_by_query):
            raise AssertionError("unexpected execute")
        rows = self.rows_by_query[self.executed]
        self.executed += 1
        return _FakeResult(rows)


def _make_session_factory(*rows_by_query):
    session = _FakeSession(rows_by_query)

    def _factory():
        return session

    return _factory, session


def test_percentile_calculation():
    assert script._percentile([10, 20, 30, 40], 50) == 25.0
    assert script._percentile([10, 20, 30, 40], 95) == 38.5
    assert script._percentile([], 95) is None


def test_resolve_symbol_reports_uses_database_rows():
    doc_older = SimpleNamespace(id=7, report_year=2023, report_type="annual", ts_code="601686.SH")
    doc_newer = SimpleNamespace(id=9, report_year=2024, report_type="annual", ts_code="601686.SH")
    session_factory, _session = _make_session_factory([doc_older, doc_newer])

    resolved = asyncio.run(script._resolve_symbol_reports(["601686"], session_factory=session_factory))

    assert resolved["601686"].report_id == 9
    assert resolved["601686"].report_year == 2024


def test_sanitize_redacts_secret_fields():
    payload = script._sanitize(
        {
            "database_url": "postgresql://user:pass@host/db",
            "token": "abc",
            "nested": {"local_path": "/Users/kaffy/Documents/TradingAgents/file.pdf"},
            "ok": True,
        }
    )
    assert payload["database_url"] == "[redacted]"
    assert payload["token"] == "[redacted]"
    assert "local_path" not in payload["nested"]
    assert payload["ok"] is True


@pytest.mark.parametrize(
    "post_responses,get_responses,expected_code",
    [
        ([ _FakeResponse(200, {"ok": True, "job_id": "job-1", "status": "queued"}) ], [], "CREATE_NOT_ACCEPTED"),
        ([ _FakeResponse(202, {"ok": True, "status": "queued"}) ], [], "CREATE_MISSING_JOB_ID"),
        (
            [_FakeResponse(202, {"ok": True, "job_id": "job-1", "status": "queued"}), _FakeResponse(200, {"ok": True, "job_id": "job-1", "status": "queued"})],
            [_FakeResponse(200, {"ok": True, "job_id": "job-1", "status": "running", "started_at": "2026-07-13T12:00:00Z"})],
            "STATUS_NOT_QUEUED",
        ),
        (
            [_FakeResponse(202, {"ok": True, "job_id": "job-1", "status": "queued"}), _FakeResponse(500, {"ok": False, "status": "failed"})],
            [_FakeResponse(200, {"ok": True, "job_id": "job-1", "status": "queued", "started_at": None})],
            "CANCEL_FAILED",
        ),
    ],
)
def test_sample_once_rejects_failure_modes(post_responses, get_responses, expected_code):
    client = _FakeClient(post_responses=post_responses, get_responses=get_responses)
    report = script.ReportRef(symbol="600519", report_id=12, report_year=2024, report_type="annual", ts_code="600519.SH")

    with pytest.raises(script.Phase6TQAcceptanceError) as excinfo:
        asyncio.run(
            script._sample_once(
                client,
                symbol="600519",
                report=report,
                fields=["revenue"],
                refresh=False,
                sample_kind="formal-1",
            )
        )

    assert excinfo.value.code == expected_code


def test_sample_once_happy_path_returns_queue_and_cancelled():
    client = _FakeClient(
        post_responses=[
            _FakeResponse(202, {"ok": True, "job_id": "job-1", "status": "queued", "poll_after_ms": 1000, "terminal": False}),
            _FakeResponse(200, {"ok": True, "job_id": "job-1", "status": "cancelled"}),
        ],
        get_responses=[
            _FakeResponse(200, {"ok": True, "job_id": "job-1", "status": "queued", "started_at": None}),
        ],
    )
    report = script.ReportRef(symbol="600519", report_id=12, report_year=2024, report_type="annual", ts_code="600519.SH")

    result = asyncio.run(
        script._sample_once(
            client,
            symbol="600519",
            report=report,
            fields=["revenue"],
            refresh=False,
            sample_kind="formal-1",
        )
    )

    assert result["queued"] is True
    assert result["started_at_is_null"] is True
    assert result["cancelled"] is True
    assert result["job_id"] == "job-1"


def test_run_acceptance_blocks_on_preexisting_active_jobs(monkeypatch):
    async def fake_resolve(_symbols, *, session_factory=None):
        return {
            "600519": script.ReportRef(symbol="600519", report_id=12, report_year=2024, report_type="annual", ts_code="600519.SH"),
        }

    async def fake_active_jobs(*, session_factory=None):
        return [{"job_id": "preexisting", "symbol": "600519", "report_id": 12, "status": "queued"}]

    monkeypatch.setattr(script, "_resolve_symbol_reports", fake_resolve)
    monkeypatch.setattr(script, "_list_active_jobs", fake_active_jobs)

    args = SimpleNamespace(
        base_url="http://127.0.0.1:8000",
        warmup=0,
        samples=1,
        symbols="600519",
        runner_region="ap-northeast-2",
        timeout=30.0,
        out_json="/tmp/phase6tq.json",
        out_md="/tmp/phase6tq.md",
        cleanup_known_job_ids="",
    )

    payload = asyncio.run(
        script.run_acceptance(
            args,
            client_factory=lambda **kwargs: _FakeClient(),
        )
    )

    assert payload["status"] == "failed"
    assert payload["preexisting_active_jobs_found"] == 1
    assert payload["errors"][0]["code"] == "PREEXISTING_ACTIVE_JOBS"


def test_run_acceptance_cleans_up_created_jobs_on_exception(monkeypatch):
    async def fake_resolve(_symbols, *, session_factory=None):
        return {
            "600519": script.ReportRef(symbol="600519", report_id=12, report_year=2024, report_type="annual", ts_code="600519.SH"),
        }

    active_calls = []

    async def fake_active_jobs(*, session_factory=None):
        active_calls.append(1)
        return []

    monkeypatch.setattr(script, "_resolve_symbol_reports", fake_resolve)
    monkeypatch.setattr(script, "_list_active_jobs", fake_active_jobs)

    client = _FakeClient(
        post_responses=[
            _FakeResponse(202, {"ok": True, "job_id": "job-1", "status": "queued"}),
            _FakeResponse(200, {"ok": True, "job_id": "job-1", "status": "cancelled"}),
        ],
        get_responses=[
            _FakeResponse(200, {"ok": True, "job_id": "job-1", "status": "running", "started_at": "2026-07-13T12:00:00Z"}),
        ],
    )

    args = SimpleNamespace(
        base_url="http://127.0.0.1:8000",
        warmup=0,
        samples=1,
        symbols="600519",
        runner_region="ap-northeast-2",
        timeout=30.0,
        out_json="/tmp/phase6tq.json",
        out_md="/tmp/phase6tq.md",
        cleanup_known_job_ids="",
    )

    payload = asyncio.run(
        script.run_acceptance(
            args,
            client_factory=lambda **kwargs: client,
        )
    )

    assert payload["status"] == "failed"
    assert any(call[0] == "POST" and call[1].endswith("/cancel") for call in client.calls)
    assert active_calls


def test_run_acceptance_records_auto_run_and_rollout_controls(monkeypatch):
    async def fake_resolve(_symbols, *, session_factory=None):
        return {
            "600519": script.ReportRef(symbol="600519", report_id=12, report_year=2024, report_type="annual", ts_code="600519.SH"),
        }

    async def fake_active_jobs(*, session_factory=None):
        return []

    monkeypatch.setattr(script, "_resolve_symbol_reports", fake_resolve)
    monkeypatch.setattr(script, "_list_active_jobs", fake_active_jobs)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_auto_run", False, raising=False)
    monkeypatch.setattr(settings, "company_v2_financial_fusion_rollout_percent", 0, raising=False)

    client = _FakeClient(
        post_responses=[
            _FakeResponse(202, {"ok": True, "job_id": "job-1", "status": "queued"}),
            _FakeResponse(200, {"ok": True, "job_id": "job-1", "status": "cancelled"}),
        ],
        get_responses=[
            _FakeResponse(200, {"ok": True, "job_id": "job-1", "status": "queued", "started_at": None}),
        ],
    )

    args = SimpleNamespace(
        base_url="http://127.0.0.1:8000",
        warmup=0,
        samples=1,
        symbols="600519",
        runner_region="ap-northeast-2",
        timeout=30.0,
        out_json="/tmp/phase6tq.json",
        out_md="/tmp/phase6tq.md",
        cleanup_known_job_ids="",
    )

    payload = asyncio.run(
        script.run_acceptance(
            args,
            client_factory=lambda **kwargs: client,
        )
    )

    assert payload["status"] == "passed"
    assert payload["auto_run"] is False
    assert payload["rollout_percent"] == 0
    assert payload["manual_jobs_remained_queued"] is True


def test_sample_once_rejects_non_allowlist_rejection_from_api():
    client = _FakeClient(post_responses=[_FakeResponse(200, {"ok": False, "status": "ineligible", "error_code": "NOT_IN_ALLOWLIST"})])
    report = script.ReportRef(symbol="999999", report_id=99, report_year=2024, report_type="annual", ts_code="999999.SH")

    with pytest.raises(script.Phase6TQAcceptanceError) as excinfo:
        asyncio.run(
            script._sample_once(
                client,
                symbol="999999",
                report=report,
                fields=["revenue"],
                refresh=False,
                sample_kind="formal-1",
            )
        )

    assert excinfo.value.code == "CREATE_NOT_ACCEPTED"
