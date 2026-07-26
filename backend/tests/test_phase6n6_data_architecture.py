"""
tests/test_phase6n6_data_architecture.py

Phase 6N-6: Data Completeness Architecture

Covers:
  DataField model:
  T01  DataField.ok() sets status=ok and value
  T02  DataField.computed() sets status=computed and formula/dependencies
  T03  DataField.missing() sets status=missing and reason_code
  T04  DataField.provider_failed() sets status=provider_failed
  T05  DataField.disabled() sets status=disabled
  T06  DataField.has_value: True when value is not None
  T07  DataField.has_value: False when value is None
  T08  DataField.is_ok: True for ok/computed/estimated statuses
  T09  DataField.is_ok: False for missing/provider_failed/disabled
  T10  DataField.to_dict() includes all required keys

  ReasonCode completeness:
  T11  ReasonCode includes PROVIDER_TIMEOUT, FIELD_MISSING, NOT_IMPLEMENTED
  T12  ReasonCode includes FIELD_MISSING_DEPENDENCY
  T13  ReasonCode includes CACHE_UNAVAILABLE, RAG_NOT_INDEXED

  CoreSchema / CORE_FIELDS:
  T14  CORE_FIELDS has at least 30 registered fields
  T15  All 7 expected categories present: quote/valuation/income/balance/cashflow/indicators/rag
  T16  get_computed_fields() returns only fields with computed=True
  T17  get_non_nullable_fields() excludes nullable fields
  T18  get_fields_by_category('quote') returns FieldSpec list
  T19  CORE_FIELDS includes market_cap with computed=True and dependencies
  T20  CORE_FIELDS includes roe with computed=True
  T21  CORE_FIELDS includes rag_status in 'rag' category

  FieldComputeService:
  T22  compute_all with full raw_fields computes market_cap
  T23  compute_all returns DataField.COMPUTED status for successful field
  T24  compute_all returns FIELD_MISSING_DEPENDENCY when dependency missing
  T25  compute_all handles zero-division safely (returns missing not exception)
  T26  compute_all computes gross_margin from gross_profit/revenue
  T27  compute_all computes net_margin from net_profit/revenue
  T28  compute_all computes debt_ratio from total_liabilities/total_assets
  T29  compute_all chains: gross_profit computed first, then gross_margin uses it
  T30  compute_one returns single DataField
  T31  completeness_score returns 0.0 for empty dict
  T32  completeness_score returns 1.0 when all fields have values

  CoverageAuditService:
  T33  CategoryCoverage.completeness = ok / total
  T34  CategoryCoverage.to_dict() has all required keys
  T35  CoverageReport.overall_completeness aggregates across categories
  T36  CoverageReport.missing_fields filters out ok/computed/estimated entries
  T37  CoverageReport.to_dict() is JSON-serialisable
  T38  CoverageAuditService._field_entry: has_value=True gives status=ok
  T39  CoverageAuditService._field_entry: None value gives status=missing
  T40  _empty_report returns CoverageReport with 0.0 completeness

  DB Models:
  T41  DataCoverageSnapshot model has correct __tablename__
  T42  DataCoverageSnapshot has unique constraint uq_coverage_ts_date
  T43  MissingFieldQueue has unique constraint uq_missing_field_ts_field_date
  T44  ProviderErrorLog has ts_code and field_name columns

  CLI script:
  T45  coverage_audit.py exists and is importable as module
  T46  _normalize_symbol converts bare code to ts_code with suffix
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND = Path(__file__).resolve().parent.parent


# ── T01–T10  DataField ────────────────────────────────────────────────────────

from app.models.data_field import DataField, DataFieldStatus, ReasonCode


def test_t01_datafield_ok():
    df = DataField.ok("latest_price", 1780.0, "tushare", as_of="2024-01-15")
    assert df.value == 1780.0
    assert df.status == DataFieldStatus.OK
    assert df.source == "tushare"
    assert df.as_of == "2024-01-15"


def test_t02_datafield_computed():
    df = DataField.computed(
        "market_cap", 1_000_000.0,
        formula="latest_price * total_share",
        dependencies=["latest_price", "total_share"],
        as_of="2024-01-15",
    )
    assert df.status == DataFieldStatus.COMPUTED
    assert df.formula == "latest_price * total_share"
    assert "latest_price" in df.dependencies
    assert df.value == 1_000_000.0


def test_t03_datafield_missing():
    df = DataField.missing("net_profit", ReasonCode.FIELD_MISSING)
    assert df.value is None
    assert df.status == DataFieldStatus.MISSING
    assert df.reason_code == ReasonCode.FIELD_MISSING


def test_t04_datafield_provider_failed():
    df = DataField.provider_failed(
        "revenue",
        attempted_sources=["tushare", "baostock"],
        provider_errors={"tushare": "timeout", "baostock": "empty"},
    )
    assert df.status == DataFieldStatus.PROVIDER_FAILED
    assert "tushare" in df.attempted_sources


def test_t05_datafield_disabled():
    df = DataField.disabled("pe_ttm", ReasonCode.TOKEN_MISSING)
    assert df.status == DataFieldStatus.DISABLED
    assert df.reason_code == ReasonCode.TOKEN_MISSING


def test_t06_datafield_has_value_true():
    df = DataField.ok("close", 100.5, "tushare")
    assert df.has_value is True


def test_t07_datafield_has_value_false():
    df = DataField.missing("close")
    assert df.has_value is False


def test_t08_datafield_is_ok_true():
    for status in (DataFieldStatus.OK, DataFieldStatus.COMPUTED, DataFieldStatus.ESTIMATED):
        df = DataField(field_name="x", value=1.0, status=status)
        assert df.is_ok is True


def test_t09_datafield_is_ok_false():
    for status in (DataFieldStatus.MISSING, DataFieldStatus.PROVIDER_FAILED, DataFieldStatus.DISABLED):
        df = DataField(field_name="x", value=None, status=status)
        assert df.is_ok is False


def test_t10_datafield_to_dict():
    df = DataField.ok("latest_price", 1780.0, "tushare", as_of="2024-01-15")
    d = df.to_dict()
    required_keys = [
        "field_name", "value", "status", "source", "source_priority",
        "as_of", "fiscal_period", "is_stale", "is_estimated",
        "formula", "dependencies", "reason_code",
        "attempted_sources", "provider_errors",
    ]
    for k in required_keys:
        assert k in d, f"Missing key: {k}"
    assert d["field_name"] == "latest_price"
    assert d["value"] == 1780.0


# ── T11–T13  ReasonCode ───────────────────────────────────────────────────────

def test_t11_reason_code_basic():
    assert ReasonCode.PROVIDER_TIMEOUT.value == "PROVIDER_TIMEOUT"
    assert ReasonCode.FIELD_MISSING.value == "FIELD_MISSING"
    assert ReasonCode.NOT_IMPLEMENTED.value == "NOT_IMPLEMENTED"


def test_t12_reason_code_dependency():
    assert ReasonCode.FIELD_MISSING_DEPENDENCY.value == "FIELD_MISSING_DEPENDENCY"


def test_t13_reason_code_cache_rag():
    assert ReasonCode.CACHE_UNAVAILABLE.value == "CACHE_UNAVAILABLE"
    assert ReasonCode.RAG_NOT_INDEXED.value == "RAG_NOT_INDEXED"


# ── T14–T21  CoreSchema ───────────────────────────────────────────────────────

from app.models.core_schema import (
    CORE_FIELDS, FIELD_CATEGORIES,
    get_computed_fields, get_fields_by_category, get_non_nullable_fields,
)


def test_t14_core_fields_count():
    assert len(CORE_FIELDS) >= 30, f"Expected ≥30 fields, got {len(CORE_FIELDS)}"


def test_t15_all_categories_present():
    expected = {"quote", "valuation", "income", "balance", "cashflow", "indicators", "rag"}
    assert expected.issubset(FIELD_CATEGORIES.keys()), (
        f"Missing categories: {expected - set(FIELD_CATEGORIES)}"
    )


def test_t16_get_computed_fields():
    computed = get_computed_fields()
    assert len(computed) > 0
    for spec in computed:
        assert spec.computed is True


def test_t17_get_non_nullable_fields():
    non_null = get_non_nullable_fields()
    for spec in non_null:
        assert spec.nullable is False
    # nullable fields (e.g. dividend_yield) should not appear
    nullable_names = {s.name for s in CORE_FIELDS.values() if s.nullable}
    non_null_names = {s.name for s in non_null}
    assert nullable_names.isdisjoint(non_null_names)


def test_t18_get_fields_by_category():
    quote_fields = get_fields_by_category("quote")
    assert len(quote_fields) > 0
    for spec in quote_fields:
        assert spec.category == "quote"


def test_t19_market_cap_computed():
    spec = CORE_FIELDS["market_cap"]
    assert spec.computed is True
    assert "latest_price" in spec.dependencies
    assert "total_share" in spec.dependencies


def test_t20_roe_computed():
    spec = CORE_FIELDS["roe"]
    assert spec.computed is True
    assert spec.category == "indicators"


def test_t21_rag_status_in_rag_category():
    spec = CORE_FIELDS["rag_status"]
    assert spec.category == "rag"


# ── T22–T32  FieldComputeService ─────────────────────────────────────────────

from app.services.field_compute_service import FieldComputeService


def test_t22_compute_market_cap():
    raw = {"latest_price": 1780.0, "total_share": 12581.0}
    results = FieldComputeService.compute_all(raw)
    mc = results.get("market_cap")
    assert mc is not None
    assert mc.has_value
    # market_cap = 1780 * 12581 * 10000 (total_share in 万股)
    expected = 1780.0 * 12581.0 * 10000
    assert abs(mc.value - expected) < 1.0


def test_t23_computed_status():
    raw = {"latest_price": 1780.0, "total_share": 12581.0}
    results = FieldComputeService.compute_all(raw)
    mc = results.get("market_cap")
    assert mc.status == DataFieldStatus.COMPUTED


def test_t24_missing_dependency():
    # no pre_close — change_pct should fail with FIELD_MISSING_DEPENDENCY
    raw = {"close": 100.0}
    results = FieldComputeService.compute_all(raw)
    cp = results.get("change_pct")
    assert cp is not None
    assert cp.reason_code == ReasonCode.FIELD_MISSING_DEPENDENCY
    assert cp.value is None


def test_t25_zero_division_safe():
    # net_margin with revenue=0 should return missing, not raise
    raw = {"net_profit": 1000.0, "revenue": 0.0}
    results = FieldComputeService.compute_all(raw)
    nm = results.get("net_margin")
    assert nm is not None
    assert nm.value is None


def test_t26_gross_margin():
    raw = {"gross_profit": 30_000.0, "revenue": 100_000.0}
    results = FieldComputeService.compute_all(raw)
    gm = results.get("gross_margin")
    assert gm is not None and gm.has_value
    assert abs(gm.value - 0.30) < 1e-9


def test_t27_net_margin():
    raw = {"net_profit": 20_000.0, "revenue": 100_000.0}
    results = FieldComputeService.compute_all(raw)
    nm = results.get("net_margin")
    assert nm is not None and nm.has_value
    assert abs(nm.value - 0.20) < 1e-9


def test_t28_debt_ratio():
    raw = {"total_liabilities": 60_000.0, "total_assets": 100_000.0}
    results = FieldComputeService.compute_all(raw)
    dr = results.get("debt_ratio")
    assert dr is not None and dr.has_value
    assert abs(dr.value - 0.60) < 1e-9


def test_t29_chain_gross_profit_to_gross_margin():
    """gross_profit computed from revenue-cost, then gross_margin uses it."""
    raw = {
        "revenue": 100_000.0,
        "cost_of_revenue": 70_000.0,
    }
    results = FieldComputeService.compute_all(raw)
    gp = results.get("gross_profit")
    assert gp is not None and gp.has_value
    assert abs(gp.value - 30_000.0) < 1.0

    gm = results.get("gross_margin")
    assert gm is not None and gm.has_value
    assert abs(gm.value - 0.30) < 1e-6


def test_t30_compute_one():
    raw = {"latest_price": 10.0, "total_share": 5000.0}
    df = FieldComputeService.compute_one("market_cap", raw)
    assert isinstance(df, DataField)
    assert df.has_value


def test_t31_completeness_score_empty():
    score = FieldComputeService.completeness_score({})
    assert score == 0.0


def test_t32_completeness_score_full():
    fields = {
        "a": DataField.ok("a", 1.0, "src"),
        "b": DataField.ok("b", 2.0, "src"),
    }
    score = FieldComputeService.completeness_score(fields)
    assert score == 1.0


# ── T33–T40  CoverageAuditService ────────────────────────────────────────────

from app.services.coverage_audit_service import (
    CategoryCoverage, CoverageAuditService, CoverageReport,
)


def test_t33_category_coverage_completeness():
    cc = CategoryCoverage("quote", 5, 3, [])
    assert abs(cc.completeness - 0.6) < 1e-6


def test_t34_category_coverage_to_dict():
    cc = CategoryCoverage("quote", 5, 3, [{"field_name": "close", "status": "ok"}])
    d = cc.to_dict()
    assert d["category"] == "quote"
    assert d["total_fields"] == 5
    assert d["ok_fields"] == 3
    assert "completeness" in d
    assert "fields" in d


def test_t35_coverage_report_overall():
    cats = {
        "quote":     CategoryCoverage("quote",     5, 5, []),
        "valuation": CategoryCoverage("valuation", 4, 0, []),
    }
    rpt = CoverageReport("600519.SH", "2024-01-15", cats)
    # 5 ok out of 9 total → 0.5556
    assert abs(rpt.overall_completeness - 5 / 9) < 1e-3


def test_t36_coverage_report_missing_fields():
    fields_data = [
        {"field_name": "close",    "status": "ok"},
        {"field_name": "pe_ttm",   "status": "missing", "reason_code": "PROVIDER_EMPTY"},
        {"field_name": "revenue",  "status": "computed"},
    ]
    cats = {"quote": CategoryCoverage("quote", 3, 2, fields_data)}
    rpt = CoverageReport("600519.SH", "2024-01-15", cats)
    assert len(rpt.missing_fields) == 1
    assert rpt.missing_fields[0]["field_name"] == "pe_ttm"


def test_t37_coverage_report_json_serialisable():
    cats = {"quote": CategoryCoverage("quote", 2, 1, [{"field_name": "x", "status": "ok"}])}
    rpt = CoverageReport("000725.SZ", "2024-01-15", cats, rag_status="empty")
    d = rpt.to_dict()
    serialised = json.dumps(d)  # must not raise
    assert "000725.SZ" in serialised
    assert "empty" in serialised


def test_t38_field_entry_has_value():
    svc = CoverageAuditService.__new__(CoverageAuditService)
    entry = svc._field_entry("close", 100.5, "etl_daily_basic")
    assert entry["status"] == "ok"
    assert entry["value"] == 100.5


def test_t39_field_entry_none_value():
    svc = CoverageAuditService.__new__(CoverageAuditService)
    entry = svc._field_entry("revenue", None, "tushare_income")
    assert entry["status"] == "missing"
    assert entry["value"] is None
    assert entry["reason_code"] is not None


def test_t40_empty_report():
    svc = CoverageAuditService.__new__(CoverageAuditService)
    svc._trade_date = "2024-01-15"
    rpt = svc._empty_report("600519.SH", "DB unavailable")
    assert rpt.overall_completeness == 0.0
    assert rpt.rag_status == "unknown"
    # every category exists with completeness=0
    for cat in ("quote", "valuation", "income", "balance", "cashflow", "indicators", "rag"):
        assert cat in rpt.categories
        assert rpt.categories[cat].completeness == 0.0


# ── T41–T44  DB Models ────────────────────────────────────────────────────────

from app.models.data_coverage import DataCoverageSnapshot, MissingFieldQueue, ProviderErrorLog


def test_t41_coverage_snapshot_tablename():
    assert DataCoverageSnapshot.__tablename__ == "data_coverage_snapshot"


def test_t42_coverage_snapshot_unique_constraint():
    constraint_names = {c.name for c in DataCoverageSnapshot.__table__.constraints}
    assert "uq_coverage_ts_date" in constraint_names


def test_t43_missing_field_queue_unique_constraint():
    constraint_names = {c.name for c in MissingFieldQueue.__table__.constraints}
    assert "uq_missing_field_ts_field_date" in constraint_names


def test_t44_provider_error_log_columns():
    col_names = {c.name for c in ProviderErrorLog.__table__.columns}
    assert "ts_code" in col_names
    assert "field_name" in col_names
    assert "provider" in col_names
    assert "reason_code" in col_names


# ── T45–T46  CLI script ───────────────────────────────────────────────────────

def test_t45_coverage_audit_script_exists():
    script = _BACKEND / "scripts" / "coverage_audit.py"
    assert script.exists(), "scripts/coverage_audit.py not found"


def test_t46_normalize_symbol():
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        "coverage_audit_script",
        _BACKEND / "scripts" / "coverage_audit.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod._normalize_symbol("600519") == "600519.SH"
    assert mod._normalize_symbol("000725") == "000725.SZ"
    assert mod._normalize_symbol("300750") == "300750.SZ"
    # already has suffix — pass through
    assert mod._normalize_symbol("601318.SH") == "601318.SH"
