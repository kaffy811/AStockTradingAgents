"""
Phase 6T-E2: Quarterly Deep Acceptance Performance Fix.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Anchor repo root so `import backend.scripts...` and doc paths work from any CWD
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_resolve_quarterly_window_uses_complete_years_and_no_future():
    from app.services.company_v2_period_classifier import resolve_quarterly_window

    window = resolve_quarterly_window(date(2026, 7, 11), years=5)

    assert window["start_year"] == 2021
    assert window["end_year"] == 2025
    assert len(window["valid_quarters"]) == 20
    assert window["expected_periods"][0] == "2021-03-31"
    assert window["expected_periods"][-1] == "2025-12-31"
    assert "2026-09-30" not in window["expected_periods"]


@pytest.mark.asyncio
async def test_history_dashboard_quarterly_does_not_use_listing_year():
    from app.services.company_v2_history_service import build_company_history_dashboard

    captured: dict = {}

    async def fake_fetch(ts, *, start_year, end_year, period, valid_quarters=None, stats_out=None):
        captured.update({
            "start_year": start_year,
            "end_year": end_year,
            "period": period,
            "valid_quarters": valid_quarters,
        })
        return {}

    with patch("app.services.company_v2_history_service.fetch_all_modules_history", new=AsyncMock(side_effect=fake_fetch)):
        with patch("app.services.company_v2_history_service.get_stock_basic",
                   new=AsyncMock(return_value={"list_year": 2001, "list_date": "2001-08-27",
                                               "list_date_status": "exact"})):
            result = await build_company_history_dashboard("CN", "600519", period="quarterly", force_refresh=True)

    assert captured["start_year"] == date.today().year - 5
    assert captured["end_year"] == date.today().year - 1
    assert len(captured["valid_quarters"]) == 20
    assert result["start_year_status"] == "recent_5_complete_years_default"


@pytest.mark.asyncio
async def test_bulk_quarterly_has_call_accounting_and_avoids_duplicate_bundle_calls():
    from app.datasource import baostock_client as bc

    async def fake_get(key, *, force_refresh=False):
        return None, False, False, "memory"

    async def fake_set(key, value, ttl):
        return None

    def fake_worker(bs_code, year_quarters):
        by_year = {}
        calls_by_endpoint = {k: 0 for k in bc._BULK_TABLE_KEYS}
        for year, _quarter in year_quarters:
            by_year.setdefault(year, {k: [] for k in bc._BULK_TABLE_KEYS})
            for key in bc._BULK_TABLE_KEYS:
                calls_by_endpoint[key] += 1
        return by_year, len(year_quarters) * len(bc._BULK_TABLE_KEYS), calls_by_endpoint

    with patch("app.services.company_v2_snapshot_cache_service.company_v2_snapshot_cache_service.get",
               new=AsyncMock(side_effect=fake_get)):
        with patch("app.services.company_v2_snapshot_cache_service.company_v2_snapshot_cache_service.set",
                   new=AsyncMock(side_effect=fake_set)):
            with patch.object(bc, "_bulk_fetch_years_worker", side_effect=fake_worker):
                with patch("concurrent.futures.ProcessPoolExecutor", side_effect=OSError("disabled")):
                    result = await bc.baostock_client.get_financial_history_bulk(
                        "300750.SZ",
                        start_year=2021,
                        end_year=2021,
                        mode="quarterly",
                        valid_quarters=[(2021, 1), (2021, 2)],
                    )

    stats = result["_bulk_stats"]
    assert stats["planned_calls"] == 12
    assert stats["actual_calls"] == 12
    assert stats["provider_calls"] == 12
    assert stats["calls_by_endpoint"]["profit"] == 2
    assert stats["duplicate_calls_avoided"] > 0


@pytest.mark.asyncio
async def test_partial_quarterly_year_cache_can_resume_missing_year():
    from app.datasource import baostock_client as bc

    get_calls = 0

    async def fake_get(key, *, force_refresh=False):
        nonlocal get_calls
        get_calls += 1
        if get_calls == 2:
            return {
                "tables": {k: [{"statDate": "2021-12-31"}] for k in bc._BULK_TABLE_KEYS},
                "year": 2021,
                "mode": "quarterly",
            }, True, False, "memory"
        return None, False, False, "memory"

    async def fake_set(key, value, ttl):
        return None

    def fake_worker(bs_code, year_quarters):
        years = {year for year, _q in year_quarters}
        by_year = {year: {k: [] for k in bc._BULK_TABLE_KEYS} for year in years}
        return by_year, len(year_quarters) * len(bc._BULK_TABLE_KEYS), {}

    with patch("app.services.company_v2_snapshot_cache_service.company_v2_snapshot_cache_service.get",
               new=AsyncMock(side_effect=fake_get)):
        with patch("app.services.company_v2_snapshot_cache_service.company_v2_snapshot_cache_service.set",
                   new=AsyncMock(side_effect=fake_set)):
            with patch.object(bc, "_bulk_fetch_years_worker", side_effect=fake_worker):
                with patch("concurrent.futures.ProcessPoolExecutor", side_effect=OSError("disabled")):
                    result = await bc.baostock_client.get_financial_history_bulk(
                        "300750.SZ",
                        start_year=2021,
                        end_year=2022,
                        mode="quarterly",
                        valid_quarters=[(2021, 4), (2022, 1)],
                    )

    stats = result["_bulk_stats"]
    assert stats["years_from_cache"] == 1
    assert stats["years_fetched"] == 1
    assert stats["years_completed"] == [2021, 2022]


def _fake_dashboard(symbol="300750"):
    rows = [
        {"period": "2021-03-31", "roe": 0.1},
        {"period": "2021-06-30", "roe": 0.2},
    ]
    return {
        "symbol": symbol,
        "period": "quarterly",
        "start_year": 2021,
        "end_year": 2025,
        "stock_basic": {"list_date": "2018-06-11"},
        "history_truncated": True,
        "history_range_label": "当前数据源覆盖 2021—2025 年",
        "modules": {
            "profitability": {
                "history": rows,
                "latest": rows[-1],
                "period_type": "quarterly",
                "chart_contract": {"preferred_chart": "multi_line", "series": [{"field": "roe"}]},
                "chart_contract_validation": {"valid": True, "issues": [], "warnings": []},
                "data_success": True,
            }
        },
        "performance_summary": {
            "response_size_bytes": 1000,
            "baostock_aggregate_calls": 1,
            "provider_calls": 120,
            "provider_calls_planned": 120,
            "planned_calls": 120,
            "actual_calls": 120,
            "calls_by_endpoint": {"profit": 20},
            "duplicate_calls_avoided": 600,
            "login_batches": 3,
            "years_from_cache": 0,
            "years_fetched": 5,
            "years_completed": [2021, 2022, 2023, 2024, 2025],
            "cache_hit": False,
        },
    }


@pytest.mark.asyncio
async def test_financial_timeout_writes_stage_and_provider_plan():
    from backend.scripts.company_v2_cross_stock_acceptance import accept_symbol

    async def slow_dashboard(*args, **kwargs):
        await asyncio.sleep(0.05)
        return _fake_dashboard()

    snapshots = []
    with patch("app.services.company_v2_stock_basic_service.get_stock_basic",
               new=AsyncMock(return_value={"symbol": "300750", "company_name": "宁德时代",
                                           "list_date": "2018-06-11"})):
        with patch("app.services.company_v2_history_service.build_company_history_dashboard",
                   new=AsyncMock(side_effect=slow_dashboard)):
            result = await accept_symbol(
                "300750",
                period="quarterly",
                quarterly_years=5,
                run_cninfo=True,
                run_payload_compare=False,
                financial_timeout=0.001,
                cninfo_timeout=0.001,
                stage_writer=lambda partial: snapshots.append(dict(partial)),
            )

    assert result["timeout"] is True
    assert result["stage"] == "quarterly_fetch"
    assert result["provider_calls"] == 0
    assert result["performance_progress"]["provider_calls_planned"] == 120
    assert result["deep_chart_gate_status"] == "not_evaluated"
    assert result["deep_chart_gate_reason"] == "financial_timeout"
    assert snapshots


@pytest.mark.asyncio
async def test_cninfo_timeout_is_separate_from_financial_timeout():
    from backend.scripts.company_v2_cross_stock_acceptance import accept_symbol

    async def slow_discover(*args, **kwargs):
        await asyncio.sleep(0.05)
        return {"reports": []}

    with patch("app.services.company_v2_stock_basic_service.get_stock_basic",
               new=AsyncMock(return_value={"symbol": "300750", "company_name": "宁德时代",
                                           "list_date": "2018-06-11"})):
        with patch("app.services.company_v2_history_service.build_company_history_dashboard",
                   new=AsyncMock(return_value=_fake_dashboard())):
            with patch("app.services.cninfo_report_discovery_agent.cninfo_report_discovery_agent.discover",
                       new=AsyncMock(side_effect=slow_discover)):
                result = await accept_symbol(
                    "300750",
                    period="quarterly",
                    quarterly_years=5,
                    run_cninfo=True,
                    run_payload_compare=False,
                    financial_timeout=1,
                    cninfo_timeout=0.001,
                )

    assert result["timeout"] is False
    assert result["provider_calls"] == 120
    assert result["cninfo_status"] == "timeout"
    assert "cninfo_timeout:0.001s" in result["warnings"]


def test_chart_not_evaluated_due_to_timeout_is_not_chart_regression():
    from backend.scripts.company_v2_cross_stock_acceptance import _empty_result, _gates

    timed_out = _empty_result("300750")
    timed_out["timeout"] = True
    timed_out["blocking_issues"] = ["financial_timeout_exceeded:180s"]
    timed_out["final_status"] = "failed"
    gates = _gates([timed_out], mode="deep", run_cninfo=True, period="quarterly")

    assert gates["chart_gate_passed"] is False
    assert gates["deep_chart_gate_status"] == "not_evaluated"
    assert gates["deep_chart_gate_reason"] == "financial_timeout"
    assert gates["chart_contract_regression"] is False


def test_bank_not_applicable_fields_are_not_blocking():
    from app.datasource.history_financial_provider import _CHART_CONTRACTS
    from app.services.company_v2_chart_contract_validator import validate_chart_contract
    from app.services.company_v2_industry_metric_applicability import build_module_applicability

    contract = _CHART_CONTRACTS["solvency"]
    fields = [s["field"] for s in contract["series"]]
    applicability = build_module_applicability("solvency", fields, "bank")
    result = validate_chart_contract(
        "solvency",
        contract,
        rows=[{"period": "2024-03-31", "debt_ratio": 91.0}],
        period_type="quarterly",
        not_applicable_fields=applicability["not_applicable_fields"],
    )

    assert result["valid"] is True


def test_deep_acceptance_script_does_not_download_pdf_or_enter_rag():
    script = (REPO_ROOT / "backend/scripts/company_v2_cross_stock_acceptance.py").read_text(encoding="utf-8")
    assert "downloadCompanyV2Report" not in script
    assert "parseCompanyV2Report" not in script
    assert "report_rag" not in script
