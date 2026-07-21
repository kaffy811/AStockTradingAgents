"""
tests/fundamental/test_phase6v_p111_staging_coverage.py — Phase 6V-P1.11 regression suite

Validates:
  1. Staging universe fixture (100 companies, required fields, canary overlap)
  2. ETL script invariants (environment guard, is_annual_full, validate_pdf_url)
  3. Dry-run gate artifact (gate_passed, year coverage thresholds, zero non-annual)
  4. Coverage report artifact (structure, company count, known exception)
  5. Regression manifest (311 entries, available/unavailable, no-fallback policy, 300209:2024 exception)
  6. Year-fix carry-forward (no wrong-year substitution policy)
  7. Environment guard (rejects non-staging, empty, production)
  8. is_annual_full() logic (include/exclude keywords, confidence threshold)
  9. validate_pdf_url() whitelist (CNINFO hosts, scheme, suffix)
  10. Integration audit (no schema changes, source SHA, universe size)
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_BACKEND = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_BACKEND))

_FIXTURES = _BACKEND / "tests" / "fixtures"
_ARTIFACTS = _BACKEND / "docs" / "artifacts"
_SCRIPTS = _BACKEND / "scripts"

# ── Helper: import ETL module without side-effects ────────────────────────────

def _import_etl():
    """Import ingest_official_annual_reports without executing argparse/__main__."""
    mod_name = "ingest_official_annual_reports"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(
        mod_name,
        _SCRIPTS / "ingest_official_annual_reports.py",
    )
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules before exec so dataclasses can resolve __module__
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def etl():
    return _import_etl()


@pytest.fixture(scope="module")
def universe() -> dict[str, Any]:
    p = _FIXTURES / "official_report_staging_universe_v1.json"
    assert p.exists(), f"Universe fixture not found: {p}"
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def gate_artifact() -> dict[str, Any]:
    p = _ARTIFACTS / "pi_official_report_p111_dry_run_gate.json"
    assert p.exists(), f"Gate artifact not found: {p}"
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def coverage_report() -> dict[str, Any]:
    p = _ARTIFACTS / "pi_official_report_p111_coverage_report.json"
    assert p.exists(), f"Coverage report not found: {p}"
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def regression_manifest() -> dict[str, Any]:
    p = _ARTIFACTS / "pi_official_report_p111_regression_manifest.json"
    assert p.exists(), f"Regression manifest not found: {p}"
    return json.loads(p.read_text())


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Universe fixture
# ═══════════════════════════════════════════════════════════════════════════════

class TestUniverseFixture:
    def test_schema_version(self, universe):
        assert universe["schema_version"] == "official_report_staging_universe_v1"

    def test_exactly_100_companies(self, universe):
        assert len(universe["companies"]) == 100
        assert universe["total_companies"] == 100

    def test_target_years(self, universe):
        assert universe["target_years"] == [2022, 2023, 2024]

    def test_report_type_annual(self, universe):
        assert universe["report_type"] == "annual"

    def test_required_fields_per_company(self, universe):
        # Actual fields: symbol, ts_code, name, exchange, sector
        required = {"symbol", "ts_code", "name", "exchange"}
        for c in universe["companies"]:
            missing = required - set(c.keys())
            assert not missing, f"{c.get('symbol')} missing fields: {missing}"

    def test_ts_code_format(self, universe):
        """ts_code must be {6-digit}.{SH|SZ}."""
        for c in universe["companies"]:
            ts = c["ts_code"]
            parts = ts.split(".")
            assert len(parts) == 2, f"Bad ts_code: {ts}"
            assert len(parts[0]) == 6, f"Bad ts_code prefix: {ts}"
            assert parts[1] in ("SH", "SZ"), f"Bad ts_code suffix: {ts}"

    def test_symbol_matches_ts_code(self, universe):
        for c in universe["companies"]:
            assert c["symbol"] == c["ts_code"].split(".")[0]

    def test_no_duplicate_symbols(self, universe):
        symbols = [c["symbol"] for c in universe["companies"]]
        assert len(symbols) == len(set(symbols)), "Duplicate symbols in universe"

    def test_exchange_valid(self, universe):
        valid_exchanges = {"SH", "SZ"}
        for c in universe["companies"]:
            assert c["exchange"] in valid_exchanges, \
                f"{c['symbol']} has invalid exchange: {c['exchange']}"

    def test_canary_eligible_overlap(self, universe):
        """Known canary-eligible stocks must appear in universe."""
        canary_stocks = set(universe.get("canary_eligible_overlap", []))
        assert len(canary_stocks) >= 5, "Expected at least 5 canary-eligible stocks"
        universe_symbols = {c["symbol"] for c in universe["companies"]}
        for s in canary_stocks:
            assert s in universe_symbols, f"Canary stock {s} not in universe"

    def test_canary_overlap_known_members(self, universe):
        """Spot-check: key staging canary stocks present."""
        canary = set(universe.get("canary_eligible_overlap", []))
        for expected in ("000001", "000725", "600519", "688146"):
            assert expected in canary, f"{expected} missing from canary_eligible_overlap"

    def test_universe_has_both_exchanges(self, universe):
        """Universe must cover both SH and SZ stocks."""
        sh = [c for c in universe["companies"] if c["ts_code"].endswith(".SH")]
        sz = [c for c in universe["companies"] if c["ts_code"].endswith(".SZ")]
        assert len(sh) >= 20, f"Too few SH stocks: {len(sh)}"
        assert len(sz) >= 20, f"Too few SZ stocks: {len(sz)}"

    def test_universe_has_diverse_sectors(self, universe):
        sectors = {c.get("sector", "") for c in universe["companies"]}
        assert len(sectors) >= 5, f"Expected diverse sectors, got only: {sectors}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Environment guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnvironmentGuard:
    def test_staging_accepted(self, etl):
        # Should not raise
        etl.validate_environment("staging")

    def test_production_rejected(self, etl):
        with pytest.raises(SystemExit):
            etl.validate_environment("production")

    def test_prod_rejected(self, etl):
        with pytest.raises(SystemExit):
            etl.validate_environment("prod")

    def test_empty_rejected(self, etl):
        with pytest.raises(SystemExit):
            etl.validate_environment("")

    def test_dev_rejected(self, etl):
        with pytest.raises(SystemExit):
            etl.validate_environment("dev")

    def test_live_rejected(self, etl):
        with pytest.raises(SystemExit):
            etl.validate_environment("live")

    def test_only_staging_in_allowed_set(self, etl):
        assert etl.ALLOWED_ENVIRONMENTS == {"staging"}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. is_annual_full() — KIND_ANNUAL_FULL classification logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsAnnualFull:
    # --- PASS cases ---
    @pytest.mark.parametrize("title,report_type,confidence", [
        ("平安银行股份有限公司2023年度报告", "annual", 0.92),
        ("比亚迪股份有限公司2022年报", "annual", 0.88),
        ("贵州茅台酒股份有限公司Annual Report 2023", "annual", 0.95),
        ("中国平安保险集团2024年度报告全文", "annual", 0.80),
        ("腾讯控股2022 Annual Report Full Text", "annual", 0.76),
    ])
    def test_annual_full_pass(self, etl, title, report_type, confidence):
        ok, reason = etl.is_annual_full(title, report_type, confidence)
        assert ok is True, f"Expected PASS for '{title}': {reason}"
        assert reason == "annual_full_all_checks_pass"

    # --- FAIL: excluded keywords ---
    @pytest.mark.parametrize("title,excl_kw", [
        # Titles with annual keyword + exclusion keyword → fails at excluded_keyword check
        ("平安银行2023年度报告摘要", "摘要"),
        ("贵州茅台2022年度报告（更正稿）", "更正"),
        ("腾讯2022 Annual Report Summary", "summary"),
        ("平安银行2023年度报告独立版", "独立"),
        ("某公司2022年度报告英文版", "英文版"),
    ])
    def test_excluded_keywords_rejected(self, etl, title, excl_kw):
        ok, reason = etl.is_annual_full(title, "annual", 0.92)
        assert ok is False
        # reason should mention the excluded keyword
        assert "excluded_keyword" in reason or excl_kw.lower() in reason.lower()

    @pytest.mark.parametrize("title", [
        # Titles without annual keyword: rejected at not_annual_keyword stage
        "比亚迪2023年社会责任报告",
        "中国平安2023 ESG报告",
        "某公司2023可持续发展报告",
    ])
    def test_non_annual_titles_rejected(self, etl, title):
        """Titles without annual keywords are rejected (no annual keyword check fails first)."""
        ok, reason = etl.is_annual_full(title, "annual", 0.92)
        assert ok is False
        # Could fail at not_annual_keyword or excluded_keyword — both are correct
        assert reason in ("not_annual_keyword",) or "excluded_keyword" in reason

    # --- FAIL: missing annual keyword ---
    def test_no_annual_keyword_rejected(self, etl):
        ok, reason = etl.is_annual_full("某公司招股说明书2023", "annual", 0.92)
        assert ok is False
        assert reason == "not_annual_keyword"

    # --- FAIL: low confidence ---
    @pytest.mark.parametrize("conf", [0.0, 0.5, 0.74])
    def test_low_confidence_rejected(self, etl, conf):
        ok, reason = etl.is_annual_full("某公司2023年度报告", "annual", conf)
        assert ok is False
        assert "low_confidence" in reason or "confidence" in reason.lower()

    # --- PASS: confidence exactly at threshold ---
    def test_confidence_at_threshold_pass(self, etl):
        """Exactly 0.75 should pass (≥ threshold)."""
        ok, reason = etl.is_annual_full("某公司2023年度报告", "annual", 0.75)
        assert ok is True

    # --- FAIL: missing title ---
    def test_missing_title_rejected(self, etl):
        ok, reason = etl.is_annual_full(None, "annual", 0.92)
        assert ok is False
        assert reason == "title_missing"

    def test_empty_title_rejected(self, etl):
        ok, reason = etl.is_annual_full("", "annual", 0.92)
        assert ok is False
        assert reason == "title_missing"

    # --- FAIL: wrong report_type ---
    def test_wrong_report_type_rejected(self, etl):
        ok, reason = etl.is_annual_full("某公司2023年度报告", "half_year", 0.92)
        assert ok is False
        assert "wrong_report_type" in reason

    # --- PASS: report_type=None is allowed (optional field) ---
    def test_none_report_type_accepted(self, etl):
        ok, reason = etl.is_annual_full("某公司2023年度报告", None, 0.92)
        assert ok is True


# ═══════════════════════════════════════════════════════════════════════════════
# 4. validate_pdf_url() — CNINFO whitelist
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidatePdfUrl:
    # --- PASS ---
    @pytest.mark.parametrize("url", [
        "https://static.cninfo.com.cn/finalpage/2023-04-28/1216784500.pdf",
        "https://www.cninfo.com.cn/new/disclosure/detail/announcements/report.pdf",
        "http://cninfo.com.cn/some/path/report.pdf",
        "https://static.cninfo.com.cn/reports/2022/annual_report.pdf",
    ])
    def test_valid_cninfo_urls(self, etl, url):
        ok, reason = etl.validate_pdf_url(url)
        assert ok is True, f"Expected valid URL: {url} — {reason}"

    # --- FAIL: non-whitelisted host ---
    @pytest.mark.parametrize("url", [
        "https://evil.com/report.pdf",
        "https://not-cninfo.com.cn/report.pdf",
        "https://cninfo.com.cn.evil.com/report.pdf",
        "https://fake-cninfo.com/annual.pdf",
    ])
    def test_non_whitelisted_host_rejected(self, etl, url):
        ok, reason = etl.validate_pdf_url(url)
        assert ok is False
        assert "host_not_whitelisted" in reason or "whitelist" in reason.lower()

    # --- FAIL: missing .pdf suffix ---
    def test_non_pdf_rejected(self, etl):
        ok, reason = etl.validate_pdf_url("https://static.cninfo.com.cn/report.html")
        assert ok is False
        assert "not_pdf" in reason or "pdf" in reason.lower()

    # --- FAIL: missing URL ---
    def test_none_url_rejected(self, etl):
        ok, reason = etl.validate_pdf_url(None)
        assert ok is False
        assert "missing" in reason

    # --- FAIL: wrong scheme ---
    def test_ftp_scheme_rejected(self, etl):
        ok, reason = etl.validate_pdf_url("ftp://static.cninfo.com.cn/report.pdf")
        assert ok is False
        assert "scheme" in reason or "invalid" in reason.lower()

    # --- Constants check ---
    def test_allowed_pdf_hosts_whitelist(self, etl):
        assert "static.cninfo.com.cn" in etl.ALLOWED_PDF_HOSTS
        assert "www.cninfo.com.cn" in etl.ALLOWED_PDF_HOSTS
        assert "cninfo.com.cn" in etl.ALLOWED_PDF_HOSTS
        assert len(etl.ALLOWED_PDF_HOSTS) == 3

    def test_rate_limit_constant(self, etl):
        """Rate limit must be ≥1.0s to respect CNINFO."""
        assert etl.RATE_LIMIT_SECONDS >= 1.0

    def test_confidence_threshold_constant(self, etl):
        assert etl.CONFIDENCE_THRESHOLD == 0.75


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Dry-run gate artifact
# ═══════════════════════════════════════════════════════════════════════════════

class TestDryRunGateArtifact:
    def test_schema_version(self, gate_artifact):
        assert gate_artifact["schema_version"] == "pi_official_report_p111_gate_v1"

    def test_gate_passed(self, gate_artifact):
        assert gate_artifact["gate_passed"] is True

    def test_phase(self, gate_artifact):
        assert gate_artifact["phase"] == "6V-P1.11"

    def test_mode_dry_run(self, gate_artifact):
        assert gate_artifact["mode"] == "dry_run"

    def test_environment_staging(self, gate_artifact):
        assert gate_artifact["environment"] == "staging"

    def test_production_disabled(self, gate_artifact):
        assert gate_artifact["production_enabled"] is False

    def test_source_sha_present(self, gate_artifact):
        sha = gate_artifact.get("source_sha", "")
        assert len(sha) == 40, f"Expected 40-char SHA, got: {sha!r}"

    def test_source_sha_value(self, gate_artifact):
        """Source SHA must be P1.10A integration result."""
        assert gate_artifact["source_sha"] == "09ff79d8c91ea80a9b4cc53aeadb23afa4d131b9"

    def test_universe_100_companies(self, gate_artifact):
        assert gate_artifact["universe"]["total_companies"] == 100

    def test_universe_target_years(self, gate_artifact):
        assert gate_artifact["universe"]["target_years"] == [2022, 2023, 2024]

    def test_accepted_candidates_gt_100(self, gate_artifact):
        summary = gate_artifact["discovery_summary"]
        assert summary["candidates_accepted"] >= 100

    def test_year_2022_coverage_gt_50pct(self, gate_artifact):
        summary = gate_artifact["discovery_summary"]
        cov_2022 = summary["year_coverage"]["2022"]
        assert cov_2022 / 100 >= 0.50, f"2022 coverage {cov_2022}/100 < 50%"

    def test_year_2023_coverage_gt_50pct(self, gate_artifact):
        summary = gate_artifact["discovery_summary"]
        cov_2023 = summary["year_coverage"]["2023"]
        assert cov_2023 / 100 >= 0.50, f"2023 coverage {cov_2023}/100 < 50%"

    def test_year_2024_coverage_positive(self, gate_artifact):
        summary = gate_artifact["discovery_summary"]
        cov_2024 = summary["year_coverage"]["2024"]
        assert cov_2024 > 0, "2024 coverage should be > 0"

    def test_gate_conditions_all_pass(self, gate_artifact):
        conditions = gate_artifact["gate_conditions"]
        for k, v in conditions.items():
            assert v is True, f"Gate condition '{k}' is False"

    def test_zero_non_annual_reports(self, gate_artifact):
        """Must not accept non-annual reports."""
        conditions = gate_artifact["gate_conditions"]
        assert conditions.get("zero_non_annual_accepted") is True

    def test_zero_low_confidence_accepted(self, gate_artifact):
        conditions = gate_artifact["gate_conditions"]
        assert conditions.get("zero_low_confidence_accepted") is True

    def test_zero_invalid_url_accepted(self, gate_artifact):
        conditions = gate_artifact["gate_conditions"]
        assert conditions.get("zero_invalid_url_accepted") is True

    def test_confidence_threshold_in_params(self, gate_artifact):
        params = gate_artifact.get("run_parameters", {})
        assert params.get("confidence_threshold") == 0.75

    def test_pdf_whitelist_in_params(self, gate_artifact):
        params = gate_artifact.get("run_parameters", {})
        whitelist = params.get("pdf_whitelist", [])
        assert any("cninfo" in w for w in whitelist), f"CNINFO missing from whitelist: {whitelist}"

    def test_db_environment_no_raw_url(self, gate_artifact):
        """Raw DB URL must NOT be in artifact."""
        raw = json.dumps(gate_artifact).lower()
        for bad in ("postgresql://", "postgres://", "mysql://", "password="):
            assert bad not in raw, f"Artifact may contain DB credential: {bad!r}"

    def test_db_environment_info_present(self, gate_artifact):
        info = gate_artifact.get("db_environment_info", {})
        assert info.get("environment") == "staging"
        assert info.get("production_enabled") is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Coverage report artifact
# ═══════════════════════════════════════════════════════════════════════════════

class TestCoverageReportArtifact:
    def test_schema_version(self, coverage_report):
        assert "p111" in coverage_report["schema_version"]

    def test_100_companies(self, coverage_report):
        assert len(coverage_report["companies"]) == 100

    def test_company_required_fields(self, coverage_report):
        # Actual fields: symbol, ts_code, name, found_years, missing_years, ...
        required = {"symbol", "ts_code", "name"}
        for c in coverage_report["companies"]:
            missing = required - set(c.keys())
            assert not missing, f"Coverage company {c.get('symbol')} missing: {missing}"

    def test_300209_has_missing_2024(self, coverage_report):
        """Known exception: 300209 (天泽信息) has no ANNUAL_FULL for 2024."""
        companies = {c["symbol"]: c for c in coverage_report["companies"]}
        assert "300209" in companies, "300209 should be in coverage report"
        c = companies["300209"]
        missing = c.get("missing_years", [])
        assert 2024 in missing, f"Expected 2024 in missing_years for 300209, got: {missing}"

    def test_no_wrong_year_substitution_in_coverage(self, coverage_report):
        """Coverage report must NOT suggest substituting a different year."""
        raw = json.dumps(coverage_report)
        assert "fallback_year" not in raw
        assert "substitute_year" not in raw

    def test_accepted_candidates_gt_100(self, coverage_report):
        """accepted_count must be ≥100."""
        total = coverage_report.get("accepted_count", 0)
        assert total >= 100, f"Expected ≥100 accepted candidates, got {total}"

    def test_target_years_present(self, coverage_report):
        assert coverage_report.get("target_years") == [2022, 2023, 2024]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Regression manifest
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegressionManifest:
    def test_schema_version(self, regression_manifest):
        assert "p111" in regression_manifest["schema_version"]

    def test_total_entries_311(self, regression_manifest):
        assert regression_manifest["total_entries"] == 311
        assert len(regression_manifest["entries"]) == 311

    def test_available_entries_273(self, regression_manifest):
        available = [e for e in regression_manifest["entries"]
                     if e["expected_status"] == "available"]
        assert len(available) == 273
        assert regression_manifest["available_entries"] == 273

    def test_unavailable_entries_38(self, regression_manifest):
        unavailable = [e for e in regression_manifest["entries"]
                       if e["expected_status"] == "unavailable"]
        assert len(unavailable) == 38
        assert regression_manifest["unavailable_entries"] == 38

    def test_available_entries_have_expected_kind(self, regression_manifest):
        for e in regression_manifest["entries"]:
            if e["expected_status"] == "available" and e.get("requested_year") != "latest":
                assert e.get("expected_kind") == "annual_full", \
                    f"{e['symbol']}:{e.get('requested_year')} missing expected_kind"

    def test_no_year_fallback_policy_present(self, regression_manifest):
        policy = regression_manifest.get("no_year_fallback_policy")
        assert policy is not None, "no_year_fallback_policy must be present"
        assert policy != "", "no_year_fallback_policy must not be empty"

    def test_no_year_fallback_policy_content(self, regression_manifest):
        policy = str(regression_manifest["no_year_fallback_policy"]).lower()
        # Must express no-substitution semantics
        assert any(kw in policy for kw in ("never", "must not", "no substitut", "no fallback",
                                            "empty", "unavailable", "must_not_fallback")), \
            f"Policy must express no-substitution: {policy!r}"

    def test_target_years(self, regression_manifest):
        assert regression_manifest["target_years"] == [2022, 2023, 2024]

    def test_300209_2024_unavailable(self, regression_manifest):
        """300209:2024 is known unavailable (inquiry reply pollution)."""
        match = [e for e in regression_manifest["entries"]
                 if e.get("symbol") == "300209" and e.get("requested_year") == 2024]
        assert len(match) == 1, "Should have exactly one entry for 300209:2024"
        e = match[0]
        assert e["expected_status"] == "unavailable"
        assert e.get("must_not_fallback_to_other_year") is True

    def test_300209_2024_reason(self, regression_manifest):
        match = [e for e in regression_manifest["entries"]
                 if e.get("symbol") == "300209" and e.get("requested_year") == 2024]
        e = match[0]
        reason = e.get("unavailable_reason", "")
        assert "inquiry" in reason.lower() or "pollution" in reason.lower() or "annual_full" in reason.lower()

    def test_300209_2022_available(self, regression_manifest):
        """300209 should be available for 2022."""
        match = [e for e in regression_manifest["entries"]
                 if e.get("symbol") == "300209" and e.get("requested_year") == 2022]
        assert len(match) == 1
        assert match[0]["expected_status"] == "available"

    def test_unavailable_entries_have_must_not_fallback(self, regression_manifest):
        for e in regression_manifest["entries"]:
            if e["expected_status"] == "unavailable":
                assert e.get("must_not_fallback_to_other_year") is True, \
                    f"{e.get('symbol')}:{e.get('requested_year')} missing must_not_fallback_to_other_year"

    def test_entry_requested_year_valid(self, regression_manifest):
        """All year-specific entries must be for 2022, 2023, or 2024; 'latest' is allowed for canary."""
        valid_years = {2022, 2023, 2024, "latest"}
        for e in regression_manifest["entries"]:
            year = e.get("requested_year")
            assert year in valid_years, \
                f"Unexpected year {year!r} in manifest for {e.get('symbol')}"

    def test_latest_entries_are_canary_eligible(self, regression_manifest):
        """Entries with requested_year='latest' must be canary_eligible stocks."""
        for e in regression_manifest["entries"]:
            if e.get("requested_year") == "latest":
                assert e.get("canary_eligible") is True, \
                    f"{e.get('symbol')} has requested_year=latest but canary_eligible is not True"

    def test_latest_entries_have_year_range(self, regression_manifest):
        """'latest' entries must specify expected_report_year_gte / expected_report_year_lte."""
        for e in regression_manifest["entries"]:
            if e.get("requested_year") == "latest" and e.get("expected_status") == "available":
                assert "expected_report_year_gte" in e, \
                    f"{e.get('symbol')} latest entry missing expected_report_year_gte"
                assert "expected_report_year_lte" in e, \
                    f"{e.get('symbol')} latest entry missing expected_report_year_lte"

    def test_canary_eligible_field_present(self, regression_manifest):
        """At least some entries should be marked canary_eligible=True."""
        eligible = [e for e in regression_manifest["entries"] if e.get("canary_eligible") is True]
        assert len(eligible) >= 10

    def test_known_canary_stocks_eligible(self, regression_manifest):
        """Key staging canary stocks must be marked eligible for 2022."""
        for symbol in ("000001", "000725", "600519", "688146"):
            match = [e for e in regression_manifest["entries"]
                     if e.get("symbol") == symbol and e.get("requested_year") == 2022
                     and e["expected_status"] == "available"]
            assert match, f"{symbol}:2022 should be available+canary_eligible"
            assert match[0].get("canary_eligible") is True


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Year-fix carry-forward (no wrong-year substitution)
# ═══════════════════════════════════════════════════════════════════════════════

class TestYearFixCarryForward:
    def test_no_year_fallback_in_etl_constants(self):
        """ETL script must not define any year-fallback/substitution logic."""
        src = (_SCRIPTS / "ingest_official_annual_reports.py").read_text()
        forbidden = ["fallback_year", "substitute_year", "alternative_year", "nearest_year"]
        for pattern in forbidden:
            assert pattern not in src, f"ETL contains forbidden pattern: {pattern}"

    def test_unavailable_does_not_fallback(self, regression_manifest):
        """All unavailable entries in manifest must have must_not_fallback_to_other_year=True."""
        unavailable = [e for e in regression_manifest["entries"]
                       if e["expected_status"] == "unavailable"]
        assert len(unavailable) > 0
        for e in unavailable:
            assert e.get("must_not_fallback_to_other_year") is True

    def test_p1_9_year_fix_sha_in_gate(self, gate_artifact):
        """Gate artifact must be built against P1.10A integrated SHA (which includes P1.9 year fix)."""
        sha = gate_artifact.get("source_sha", "")
        assert sha == "09ff79d8c91ea80a9b4cc53aeadb23afa4d131b9"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Integration audit (no schema changes)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegrationAudit:
    def test_no_new_alembic_migration_in_p111(self):
        """P1.11 must not introduce new DB schema changes."""
        alembic_dir = _BACKEND / "alembic" / "versions"
        if alembic_dir.exists():
            for f in alembic_dir.glob("*.py"):
                content = f.read_text().lower()
                assert "p111" not in content, f"Unexpected P1.11 migration: {f.name}"

    def test_ingest_script_uses_existing_upsert(self):
        """ETL script must use ReportDocumentService.upsert_discovered_report (no raw SQL)."""
        src = (_SCRIPTS / "ingest_official_annual_reports.py").read_text()
        assert "upsert_discovered_report" in src
        import re
        raw_inserts = re.findall(r'\bINSERT\s+INTO\b', src, re.IGNORECASE)
        assert len(raw_inserts) == 0, "ETL should not use raw INSERT INTO"

    def test_etl_allowed_environments_only_staging(self, etl):
        assert etl.ALLOWED_ENVIRONMENTS == {"staging"}

    def test_etl_allowed_report_types_only_annual(self, etl):
        assert etl.ALLOWED_REPORT_TYPES == {"annual"}

    def test_universe_fixture_path(self):
        p = _FIXTURES / "official_report_staging_universe_v1.json"
        assert p.exists(), f"Universe fixture missing: {p}"

    def test_artifacts_all_present(self):
        for name in (
            "pi_official_report_p111_dry_run_gate.json",
            "pi_official_report_p111_coverage_report.json",
            "pi_official_report_p111_regression_manifest.json",
        ):
            p = _ARTIFACTS / name
            assert p.exists(), f"P1.11 artifact missing: {name}"

    def test_etl_script_present(self):
        p = _SCRIPTS / "ingest_official_annual_reports.py"
        assert p.exists(), f"ETL script missing: {p}"

    def test_universe_company_count_matches_artifact(self, universe, gate_artifact):
        assert len(universe["companies"]) == gate_artifact["universe"]["total_companies"]

    def test_no_raw_db_url_in_any_artifact(self, gate_artifact, coverage_report, regression_manifest):
        """No artifact should contain raw database credentials or URL."""
        for name, artifact in (
            ("gate", gate_artifact),
            ("coverage", coverage_report),
            ("manifest", regression_manifest),
        ):
            raw = json.dumps(artifact).lower()
            for bad in ("postgresql://", "postgres://", "mysql://", "password="):
                assert bad not in raw, f"Artifact '{name}' may contain DB credential: {bad!r}"

    def test_etl_has_dry_run_default_comment(self):
        """ETL script docstring must mention dry-run as default."""
        src = (_SCRIPTS / "ingest_official_annual_reports.py").read_text().lower()
        assert "dry-run" in src or "dry_run" in src

    def test_etl_has_staging_guard_comment(self):
        """ETL script must mention staging guard."""
        src = (_SCRIPTS / "ingest_official_annual_reports.py").read_text().lower()
        assert "staging" in src
        assert "production" in src  # mentions production is forbidden
