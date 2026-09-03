from __future__ import annotations

import asyncio
import importlib.util
import time
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_run_provider_with_debug_success():
    from app.datasource.debug_provider_runner import run_provider_with_debug

    result = await run_provider_with_debug("unit", "success", lambda: [{"x": 1}], timeout_seconds=1)
    assert result["success"] is True
    assert result["status"] == "success"
    assert result["rows_count"] == 1
    assert result["started_at"]
    assert result["ended_at"]


@pytest.mark.asyncio
async def test_run_provider_with_debug_empty():
    from app.datasource.debug_provider_runner import run_provider_with_debug

    result = await run_provider_with_debug("unit", "empty", lambda: [], timeout_seconds=1)
    assert result["success"] is False
    assert result["status"] == "empty"
    assert result["error_code"] == "PROVIDER_EMPTY"


@pytest.mark.asyncio
async def test_run_provider_with_debug_timeout():
    from app.datasource.debug_provider_runner import run_provider_with_debug

    async def slow():
        await asyncio.sleep(1)
        return [{"x": 1}]

    result = await run_provider_with_debug("unit", "slow", slow, timeout_seconds=0.02)
    assert result["success"] is False
    assert result["status"] == "timeout"
    assert result["error_code"] == "PROVIDER_TIMEOUT"
    assert result["rows_count"] == 0


@pytest.mark.asyncio
async def test_sync_blocking_provider_timeout_detached():
    from app.datasource.debug_provider_runner import run_provider_with_debug

    def blocking():
        time.sleep(0.5)
        return [{"x": 1}]

    result = await run_provider_with_debug("unit", "blocking", blocking, timeout_seconds=0.02)
    assert result["error_code"] == "PROVIDER_TIMEOUT"
    assert result["detached_timeout"] is True


@pytest.mark.asyncio
async def test_provider_exception_structured():
    from app.datasource.debug_provider_runner import run_provider_with_debug

    def boom():
        raise RuntimeError("boom")

    result = await run_provider_with_debug("unit", "boom", boom, timeout_seconds=1)
    assert result["success"] is False
    assert result["status"] == "exception"
    assert result["error_code"] == "PROVIDER_EXCEPTION"
    assert "boom" in result["error_message"]


@pytest.mark.asyncio
async def test_debug_full_partial_when_one_provider_timeout(monkeypatch):
    from app.schemas.company_v2_debug import CompanyV2DebugEnvelope, CompanyV2Render, CompanyV2SourceAttempt
    from app.services.company_v2_debug_service import company_v2_debug_service

    async def fake_build_module(market, symbol, module_key, **kwargs):
        env = CompanyV2DebugEnvelope(
            request_id="rid",
            market=market,
            symbol=symbol,
            ts_code=f"{symbol}.SH",
            module_key=module_key,
            data_mode="free",
        )
        if module_key == "profitability":
            env.partial = True
            env.ok = False
            env.source_chain.append(CompanyV2SourceAttempt(
                provider="baostock",
                endpoint="unit",
                status="timeout",
                error_code="PROVIDER_TIMEOUT",
            ))
        else:
            env.render = CompanyV2Render(renderable=True, table_renderable=True, has_displayable_data=True)
            env.ok = True
            env.source_chain.append(CompanyV2SourceAttempt(provider="cache", endpoint="unit", success=True))
        return env

    monkeypatch.setattr(company_v2_debug_service, "build_module", fake_build_module)
    result = await company_v2_debug_service.build_full(
        "CN", "600519", include_raw=False, providers=None, force_refresh=True, max_raw_chars=1000, db=None
    )
    assert result["partial"] is True
    assert result["summary"]["providers_timeout"] == 1
    assert result["modules"]["profitability"]["source_chain"][0]["error_code"] == "PROVIDER_TIMEOUT"


@pytest.mark.asyncio
async def test_debug_full_total_timeout_returns_partial(monkeypatch):
    from app.core.config import settings
    from app.services.company_v2_debug_service import company_v2_debug_service

    old_timeout = settings.company_v2_debug_full_timeout_seconds
    settings.company_v2_debug_full_timeout_seconds = 0.02

    async def slow_build_module(*args, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(company_v2_debug_service, "build_module", slow_build_module)
    try:
        result = await company_v2_debug_service.build_full(
            "CN", "600519", include_raw=False, providers=None, force_refresh=True, max_raw_chars=1000, db=None
        )
    finally:
        settings.company_v2_debug_full_timeout_seconds = old_timeout

    assert result["partial"] is True
    assert result["summary"]["providers_timeout"] >= 1


def test_diagnosis_mapping_error():
    from app.services.company_v2_debug_diagnosis_service import diagnose_company_v2_envelope

    diagnosis = diagnose_company_v2_envelope({
        "module_key": "growth",
        "source_chain": [{"provider": "baostock", "rows_count": 2, "success": True}],
        "raw": {},
        "normalized": {"rows": [], "fields": {}},
        "render": {"renderable": False},
    })
    assert diagnosis["primary_issue"] == "MAPPING_ERROR"


def test_diagnosis_render_rule_error():
    from app.services.company_v2_debug_diagnosis_service import diagnose_company_v2_envelope

    diagnosis = diagnose_company_v2_envelope({
        "module_key": "growth",
        "source_chain": [{"provider": "baostock", "rows_count": 1, "success": True}],
        "normalized": {"rows": [{"revenue": 0}], "fields": {"revenue": {"value": 0}}},
        "render": {"renderable": False},
    })
    assert diagnosis["primary_issue"] == "RENDER_RULE_ERROR"


@pytest.mark.asyncio
async def test_script_writes_partial_artifact_on_timeout(tmp_path, monkeypatch):
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "debug_free_mode_data_sources.py"
    spec = importlib.util.spec_from_file_location("debug_free_mode_data_sources_test", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    async def fake_run_symbol(ts_code, years, provider_timeout, symbol_timeout):
        return {
            "ts_code": ts_code,
            "symbol_6": ts_code.split(".")[0],
            "partial": True,
            "probed_at": "now",
            "probes": [{
                "probe": "unit_timeout",
                "status": "timeout",
                "latency_ms": 1,
                "error": "PROVIDER_TIMEOUT",
                "detail": {"rows_count": 0},
            }],
            "renderability": {"score": 0},
            "summary": {"timeout": 1},
        }

    monkeypatch.setattr(module, "_run_symbol", fake_run_symbol)
    out_json = tmp_path / "partial.json"
    out_csv = tmp_path / "partial.csv"
    code = await module._run(
        symbols=["600519"],
        years=[2025],
        out_dir=tmp_path,
        out_json=out_json,
        out_csv=out_csv,
        dry_run=False,
        provider_timeout=0.01,
        symbol_timeout=0.01,
    )
    assert code == 1
    assert out_json.exists()
    assert out_csv.exists()
    assert "PROVIDER_TIMEOUT" in out_json.read_text()


@pytest.mark.asyncio
async def test_raw_safety_and_include_raw_controls():
    from app.datasource.debug_provider_runner import run_provider_with_debug

    hidden = await run_provider_with_debug(
        "unit", "raw", lambda: [{"token": "x", "local_path": "/tmp/a", "v": 1}],
        include_raw=False,
        timeout_seconds=1,
    )
    visible = await run_provider_with_debug(
        "unit", "raw", lambda: [{"token": "x", "local_path": "/tmp/a", "v": 1}],
        include_raw=True,
        timeout_seconds=1,
    )
    assert "raw_full" not in hidden
    assert visible["raw_full"][0]["token"] == "[redacted]"
    assert "local_path" not in visible["raw_full"][0]


def test_frontend_company_v2_debug_panel_enhanced():
    root = Path(__file__).resolve().parents[3]
    panel = (root / "frontend/src/components/company-v2/CompanyV2DebugPanel.vue").read_text()
    section = (root / "frontend/src/components/company-v2/CompanyV2Section.vue").read_text()
    assert "providers_timeout" in panel
    assert "diagnosis" in section
    assert "source-timeout" in section
