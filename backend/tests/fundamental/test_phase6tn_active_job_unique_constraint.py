from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services import company_v2_financial_fusion_job_service as job_service_module


class _FakeConn:
    def __init__(self):
        self.executed = []
        self.run_sync_called = False

    async def run_sync(self, fn):
        self.run_sync_called = True
        return None

    async def execute(self, stmt):
        self.executed.append(str(stmt))


class _FakeBegin:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conn):
        self._conn = conn
        self.url = SimpleNamespace(get_backend_name=lambda: "postgresql")

    def begin(self):
        return _FakeBegin(self._conn)


def test_ensure_schema_creates_active_fingerprint_unique_index(monkeypatch):
    conn = _FakeConn()
    fake_engine = _FakeEngine(conn)
    monkeypatch.setattr(job_service_module, "async_engine", fake_engine)
    monkeypatch.setattr(job_service_module.company_v2_financial_fusion_job_service, "_schema_ready", False)

    asyncio.run(job_service_module.company_v2_financial_fusion_job_service.ensure_schema())

    assert conn.run_sync_called is True
    assert any("CREATE UNIQUE INDEX IF NOT EXISTS uq_company_v2_financial_fusion_jobs_active_fingerprint" in stmt for stmt in conn.executed)
    assert any("WHERE status IN ('queued', 'running')" in stmt for stmt in conn.executed)
