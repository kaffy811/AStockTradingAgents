from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clear_company_v2_cache_memory():
    from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service

    company_v2_snapshot_cache_service._memory.clear()
    company_v2_snapshot_cache_service._memory_locks.clear()
    yield
    company_v2_snapshot_cache_service._memory.clear()
    company_v2_snapshot_cache_service._memory_locks.clear()


def test_phase6u_d4_cache_key_isolates_market_symbol_period_version():
    from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service

    k1 = company_v2_snapshot_cache_service.make_company_key("company_v2", "CN", "000725", "annual", version="v4")
    k2 = company_v2_snapshot_cache_service.make_company_key("company_v2", "CN", "600519", "annual", version="v4")
    k3 = company_v2_snapshot_cache_service.make_company_key("company_v2", "CN", "000725", "quarterly", version="v4")
    k4 = company_v2_snapshot_cache_service.make_company_key("company_v2", "CN", "000725", "annual", version="v5")
    assert k1 == "company_v2:CN:000725:annual:v4"
    assert len({k1, k2, k3, k4}) == 4


@pytest.mark.asyncio
async def test_phase6u_d4_swr_fresh_stale_and_expired(monkeypatch):
    from app.services import company_v2_snapshot_cache_service as module

    svc = module.company_v2_snapshot_cache_service
    monkeypatch.setattr(module.time, "time", lambda: 1000.0)
    await svc.set_swr("company_history:CN:000725:annual:v4", {"ok": True}, fresh_ttl=10, stale_ttl=20)

    value, status, _ = await svc.get_swr("company_history:CN:000725:annual:v4")
    assert status == "fresh"
    assert value == {"ok": True}

    monkeypatch.setattr(module.time, "time", lambda: 1015.0)
    value, status, _ = await svc.get_swr("company_history:CN:000725:annual:v4")
    assert status == "stale"
    assert value == {"ok": True}

    monkeypatch.setattr(module.time, "time", lambda: 1035.0)
    value, status, _ = await svc.get_swr("company_history:CN:000725:annual:v4")
    assert status == "expired"
    assert value == {"ok": True}


@pytest.mark.asyncio
async def test_phase6u_d4_distributed_lock_and_invalidation():
    from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service as svc

    key = "company_reports:CN:600519:annual:v2"
    await svc.set_swr(key, {"reports": [1]}, fresh_ttl=60, stale_ttl=60)
    token = await svc.acquire_refresh_lock(key, ttl=15)
    assert token
    assert await svc.acquire_refresh_lock(key, ttl=15) is None
    await svc.release_refresh_lock(key, token)
    assert await svc.acquire_refresh_lock(key, ttl=15)

    deleted = await svc.invalidate_patterns(["company_reports:CN:600519:*"])
    assert "company_reports:CN:600519:*" in deleted
    value, status, _ = await svc.get_swr(key)
    assert status == "miss"
    assert value is None


def test_phase6u_d4_report_summary_ready_counts_from_same_list():
    from app.routers.company_v2_debug import _reports_view_model

    reports = [
        {"report_type": "annual", "chunk_count": 12, "rag_status": "indexed"},
        {"report_type": "annual", "chunk_count": 0, "rag_status": "pending"},
        {"report_type": "q1", "chunk_count": 0, "rag_index_status": "partial"},
    ]
    model = _reports_view_model(reports, state="persisted_found")
    assert model["summary"]["report_count"] == 3
    assert model["summary"]["annual_count"] == 2
    assert model["summary"]["ready_count"] == 2
    assert model["summary"]["rag_document_count"] == 2
    assert model["report_count"] == len(reports)
