from __future__ import annotations

import pytest


def test_provider_registry_keyed_by_provider_endpoint_field():
    from app.services.provider_field_registry import get_provider_field_definition

    roe = get_provider_field_definition("baostock", "query_profit_data", "roe_avg")
    assert roe is not None
    assert roe.raw_unit == "ratio"
    assert roe.normalization_rule == "percentage_fraction x 100"
    assert get_provider_field_definition("baostock", "query_growth_data", "roe_avg") is None


def test_provenance_survives_provider_to_dashboard_rows():
    from app.datasource.history_financial_provider import _build_module_history_from_rows

    result = _build_module_history_from_rows(
        "profitability",
        [{
            "stat_date": "2025-12-31",
            "pub_date": "2026-04-25",
            "mb_revenue": "1000000000",
            "roe_avg": "0.07",
        }],
        ts_code="000858.SZ",
        start_year=2025,
        end_year=2025,
        period="annual",
        data_success=True,
    )
    row = result["history"][0]
    assert row["financial_metric_schema_version"] == "financial_metric_v1"
    assert row["field_provenance"]["revenue"]["source_endpoint"] == "query_profit_data"
    assert row["field_provenance"]["revenue"]["source_key"] == "mb_revenue"
    assert row["field_provenance"]["revenue"]["raw_unit"] == "CNY"
    assert row["field_provenance"]["roe"]["raw_unit"] == "ratio"
    assert row["field_provenance"]["roe"]["period_type"] == "annual"
    assert row["field_provenance"]["roe"]["disclosed_at"] == "2026-04-25"


def test_company_chat_metric_uses_persisted_provenance_for_verified_unit():
    from app.services.company_chat_data_service import _metric_from_row

    row = {
        "period": "2025-12-31",
        "report_year": 2025,
        "report_period_type": "annual",
        "roe": 0.07,
        "field_provenance": {
            "roe": {
                "raw_unit": "ratio",
                "source_system": "baostock.query_profit_data",
                "source_endpoint": "query_profit_data",
                "source_key": "roe_avg",
                "period_type": "annual",
                "report_year": 2025,
                "accounting_scope": "consolidated",
                "value_type": "ratio",
                "normalization_rule": "percentage_fraction x 100",
                "schema_version": "financial_metric_v1",
            }
        },
    }
    metric = _metric_from_row(row, "roe", source="company_v2_history.profitability")
    assert metric["raw_unit"] == "ratio"
    assert metric["normalized_value"] == pytest.approx(7.0)
    assert metric["normalized_unit"] == "percent"
    assert metric["validation_status"] in {"verified", "normalized"}


def test_legacy_value_without_provenance_remains_unverified():
    from app.services.company_chat_data_service import _metric_from_row

    row = {"period": "2025-12-31", "report_year": 2025, "report_period_type": "annual", "roe": 0.07}
    metric = _metric_from_row(row, "roe", source="company_v2_history.profitability")
    assert metric["normalized_value"] == pytest.approx(7.0)
    assert metric["validation_status"] == "unverified"
    assert "LEGACY_PROVENANCE_MISSING" in metric["warnings"]
    assert metric["legacy_unverified"] is True


@pytest.mark.asyncio
async def test_backfill_dry_run_performs_no_writes(monkeypatch):
    import scripts.backfill_financial_metric_provenance as script

    calls = []

    async def _dashboard(*args, **kwargs):
        calls.append(kwargs)
        return {
            "modules": {
                "profitability": {
                    "history": [
                        {
                            "period": "2025-12-31",
                            "report_year": 2025,
                            "roe": 0.07,
                        }
                    ]
                }
            }
        }

    monkeypatch.setattr(script, "build_company_history_dashboard", _dashboard)
    args = type("Args", (), {
        "market": "CN",
        "symbol": "000858",
        "report_year": 2025,
        "dry_run": True,
        "force_refresh": True,
        "limit": 10,
    })()
    payload = await script._run(args)
    assert payload["write_performed"] is False
    assert calls[0]["force_refresh"] is False
    assert payload["summary"]["legacy_unverified_rows"] == 1
    assert payload["coverage"]["legacy_unverified"] == 1


@pytest.mark.asyncio
async def test_backfill_apply_requires_confirm_symbol(monkeypatch):
    import scripts.backfill_financial_metric_provenance as script

    calls = []

    async def _dashboard(*args, **kwargs):
        calls.append(kwargs)
        return {"modules": {"profitability": {"history": []}}}

    monkeypatch.setattr(script, "build_company_history_dashboard", _dashboard)
    args = type("Args", (), {
        "market": "CN",
        "symbol": "000858",
        "report_year": 2025,
        "dry_run": False,
        "apply": True,
        "confirm_symbol": None,
        "limit": 10,
    })()
    payload = await script._run(args)
    assert payload["write_allowed"] is False
    assert payload["write_performed"] is False
    assert "CONFIRM_SYMBOL_REQUIRED" in payload["write_validation_errors"]
    assert calls[0]["force_refresh"] is False


@pytest.mark.asyncio
async def test_backfill_apply_uses_existing_refresh_path_when_confirmed(monkeypatch):
    import scripts.backfill_financial_metric_provenance as script

    calls = []

    async def _dashboard(*args, **kwargs):
        calls.append(kwargs)
        return {
            "modules": {
                "profitability": {
                    "history": [
                        {
                            "period": "2025-12-31",
                            "report_year": 2025,
                            "report_period_type": "annual",
                            "roe": 0.07,
                            "field_provenance": {
                                "roe": {
                                    "raw_unit": "ratio",
                                    "source_endpoint": "query_profit_data",
                                    "source_key": "roe_avg",
                                }
                            },
                            "financial_metric_schema_version": "financial_metric_v1",
                        }
                    ]
                }
            }
        }

    monkeypatch.setattr(script, "build_company_history_dashboard", _dashboard)
    args = type("Args", (), {
        "market": "CN",
        "symbol": "000858",
        "report_year": 2025,
        "dry_run": False,
        "apply": True,
        "confirm_symbol": "000858",
        "limit": 10,
    })()
    payload = await script._run(args)
    assert payload["write_allowed"] is True
    assert payload["write_performed"] is True
    assert calls[0]["force_refresh"] is True
    assert payload["coverage"]["verified_metrics"] == 1
    assert payload["idempotency"]["safe_to_repeat"] is True


def test_backfill_payload_redacts_sensitive_keys():
    import scripts.backfill_financial_metric_provenance as script

    payload = script._redact_sensitive({
        "database_url": "postgres://secret",
        "nested": {"api_key": "secret", "safe": "ok"},
        "items": [{"jwt": "secret"}],
    })
    assert payload["database_url"] == "[REDACTED]"
    assert payload["nested"]["api_key"] == "[REDACTED]"
    assert payload["nested"]["safe"] == "ok"
    assert payload["items"][0]["jwt"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_annual_request_does_not_upgrade_legacy_latest_value(monkeypatch):
    from app.services.company_chat_data_service import company_chat_data_service

    async def _dashboard(*args, **kwargs):
        return {
            "modules": {
                "profitability": {
                    "period_type": "annual",
                    "history": [
                        {
                            "period": "2025-12-31",
                            "report_year": 2025,
                            "report_period_type": "annual",
                            "revenue": 405.29,
                        }
                    ],
                    "latest": {},
                }
            }
        }

    monkeypatch.setattr("app.services.company_chat_data_service.build_company_history_dashboard", _dashboard)
    monkeypatch.setattr("app.services.company_chat_data_service.stock_data_service.get_quote_optional", lambda *a, **k: None)
    result = await company_chat_data_service.get_financial_metrics(
        {"market": "CN", "symbol": "000858"},
        ["revenue"],
        target_period_type="annual",
        target_report_year=2025,
        allow_fallback=False,
    )
    assert "revenue" not in result["financial_fields"]
    assert result["unavailable_metrics"]["revenue"]["validation_status"] == "unverified"
    assert result["metric_coverage"]["verified_metrics"] == 0
