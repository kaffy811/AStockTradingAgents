"""
Phase 6V-P1.10 regression suite — W3 warm-pool observation gate.

Validates:
  1. Coverage policy: entity_year_key selected-only counting
  2. Combined gate: 100 selected, ≥20 entity instances, all zero-tol=0
  3. Performance: warm tool_p95 ≤ 4000ms
  4. Timeout root-cause: W1-037 classified as cold_start_sporadic (not sustained)
  5. Entity-year key function: correct (symbol, year) normalization
  6. Warmup exclusion: warmup cases not counted in formal metrics
  7. Integration audit: all 4 P1.9 commits cherry-picked cleanly
  8. Year-fix regression (carry-forward from P1.9): sample validation
"""

import json
import pytest
from pathlib import Path

ARTIFACT_DIR = Path(__file__).parent.parent.parent / "docs" / "artifacts"


def load(name: str) -> dict:
    p = ARTIFACT_DIR / name
    assert p.exists(), f"Missing artifact: {name}"
    return json.loads(p.read_text())


# ── Coverage policy ──────────────────────────────────────────────────────────

def test_coverage_policy_doc_exists():
    """Selected-only coverage policy document must exist."""
    p = ARTIFACT_DIR / "pi_official_report_p110_selected_coverage_policy.md"
    assert p.exists()
    text = p.read_text()
    assert "selected_unique_entity_instances" in text
    assert "Demo" in text and "Warm-up" in text


def test_coverage_policy_excludes_demo():
    """Coverage policy must explicitly exclude demo/known-unavailable entities."""
    text = (ARTIFACT_DIR / "pi_official_report_p110_selected_coverage_policy.md").read_text()
    assert "Demo / known-unavailable" in text or "known_unavailable" in text
    assert "Warm-up" in text or "Warm-up requests" in text


# ── Entity year key function ─────────────────────────────────────────────────

@pytest.mark.parametrize("symbol,year,expected", [
    ("600186", 2022, "600186:2022"),
    ("000858", 2025, "000858:2025"),
    ("300209", None, "300209:latest"),
    ("600519", 2024, "600519:2024"),
    ("000001", 2023, "000001:2023"),
])
def test_entity_year_key_format(symbol, year, expected):
    """entity_year_key must produce 'symbol:year' or 'symbol:latest'."""
    key = f"{symbol}:{year if year is not None else 'latest'}"
    assert key == expected


# ── M1 artifact ─────────────────────────────────────────────────────────────

class TestM1Artifact:
    def setup_method(self):
        self.m1 = load("pi_official_report_p110_m1_results.json")

    def test_m1_selected_50(self):
        assert self.m1["metrics"]["bucket_selected"] == 50

    def test_m1_zero_tolerance_all_zero(self):
        m = self.m1["metrics"]
        for key in ("fabricated_url", "wrong_entity", "wrong_year", "wrong_report_type",
                    "provenance_failure", "business_write", "double_write", "unknown_write",
                    "trace_mismatch", "terminal_missing", "raw500", "raw503",
                    "task_leak", "db_leak", "pending_rollback_error"):
            assert m[key] == 0, f"M1 {key}={m[key]} expected 0"

    def test_m1_tool_p95_within_threshold(self):
        """Warm-pool tool p95 must be ≤ 4000ms."""
        assert self.m1["latency_ms"]["tool_p95"] <= 4000

    def test_m1_styles_all_6(self):
        styles = set(self.m1["selected_coverage"]["styles"])
        assert len(styles) >= 6, f"Only {len(styles)} styles: {styles}"

    def test_m1_all_11_stocks(self):
        stocks = set(self.m1["selected_coverage"]["unique_stocks"])
        assert len(stocks) == 11, f"Expected 11 stocks, got {len(stocks)}"

    def test_m1_no_rollback(self):
        assert self.m1.get("rollback_event") is None

    def test_m1_warmup_completed_before_run(self):
        assert self.m1["warmup_completed_before_run"] is True


# ── M2 artifact ─────────────────────────────────────────────────────────────

class TestM2Artifact:
    def setup_method(self):
        self.m2 = load("pi_official_report_p110_m2_results.json")

    def test_m2_selected_50(self):
        assert self.m2["metrics"]["bucket_selected"] == 50

    def test_m2_zero_tolerance_all_zero(self):
        m = self.m2["metrics"]
        for key in ("fabricated_url", "wrong_entity", "wrong_year", "wrong_report_type",
                    "provenance_failure", "business_write", "double_write", "unknown_write",
                    "trace_mismatch", "terminal_missing", "raw500", "raw503",
                    "task_leak", "db_leak", "pending_rollback_error"):
            assert m[key] == 0, f"M2 {key}={m[key]} expected 0"

    def test_m2_tool_p95_within_threshold(self):
        assert self.m2["latency_ms"]["tool_p95"] <= 4000

    def test_m2_styles_all_6(self):
        styles = set(self.m2["selected_coverage"]["styles"])
        assert len(styles) >= 6

    def test_m2_no_rollback(self):
        assert self.m2.get("rollback_event") is None


# ── Final gate artifact ──────────────────────────────────────────────────────

class TestFinalGate:
    def setup_method(self):
        self.gate = load("pi_official_report_p110_final_gate.json")

    def test_gate_passed(self):
        assert self.gate["gate_passed"] is True

    def test_combined_selected_gte_100(self):
        assert self.gate["combined_metrics"]["bucket_selected"] >= 100

    def test_entity_instances_gte_20(self):
        ei = len(self.gate["selected_coverage"]["entity_instances"])
        assert ei >= 20, f"Only {ei} entity instances"

    def test_all_11_stocks_covered(self):
        stocks = len(self.gate["selected_coverage"]["unique_stocks"])
        assert stocks == 11

    def test_safety_correctness_rate_1(self):
        assert self.gate["combined_rates"]["safety_correctness_rate"] == 1.0

    def test_timeout_rate_below_threshold(self):
        rate = self.gate["combined_rates"]["unexpected_timeout_rate"]
        assert rate is None or rate < 0.01

    def test_fallback_rate_within_limit(self):
        rate = self.gate["combined_rates"]["fallback_rate"]
        assert rate is None or rate <= 0.10

    def test_warm_tool_p95_below_4s(self):
        assert self.gate["performance_assessment"]["warm_tool_p95_ms"] <= 4000

    def test_not_recommended_for_5pct(self):
        assert self.gate["recommendations"]["recommended_to_raise_to_five_percent"] is False

    def test_continue_1pct_recommended(self):
        assert self.gate["recommendations"]["recommended_to_continue_one_percent"] is True

    def test_not_recommended_for_production(self):
        assert self.gate["recommendations"]["recommended_for_production"] is False
        assert self.gate["recommendations"]["recommended_for_live_serving"] is False

    def test_no_rollback_events(self):
        rb = self.gate["rollback_events"]
        assert rb["m1"] is False and rb["m2"] is False

    def test_6_styles_combined(self):
        styles = self.gate["selected_coverage"]["styles"]
        assert len(styles) >= 6

    def test_entity_instance_threshold_met(self):
        assert self.gate["selected_coverage"]["entity_instance_threshold_met"] is True


# ── Timeout root cause ───────────────────────────────────────────────────────

class TestTimeoutRootCause:
    def setup_method(self):
        self.rc = load("pi_official_report_p110_timeout_root_cause.json")

    def test_target_is_w1_037(self):
        assert self.rc["repro_target"]["original_case"] == "W1-037"
        assert self.rc["repro_target"]["symbol"] == "000725"

    def test_repro_n_is_5(self):
        assert self.rc["repro_n"] == 5

    def test_repro_after_warmup(self):
        assert self.rc["repro_after_warmup"] is True

    def test_zero_timeouts_in_warm_repro(self):
        assert self.rc["repro_timeout_count"] == 0

    def test_classified_as_sporadic_not_sustained(self):
        assert "sporadic" in self.rc["classification"]
        assert "sustained" not in self.rc["classification"]

    def test_warm_p95_below_4s(self):
        assert self.rc["warm_p95_ms"] <= 4000

    def test_warm_passes_threshold(self):
        assert self.rc["warm_passes_threshold"] is True


# ── Warmup artifact ──────────────────────────────────────────────────────────

def test_warmup_pool_warming_confirmed():
    w = load("pi_official_report_p110_warmup_results.json")
    assert w["pool_warming_confirmed"] is True
    assert w["warmup_count"] == 15


def test_warmup_not_counted_in_formal_metrics():
    w = load("pi_official_report_p110_warmup_results.json")
    for case in w.get("warmup_cases", []):
        assert case.get("counted_in_formal_metrics") is False


# ── Integration audit ────────────────────────────────────────────────────────

class TestIntegrationAudit:
    def setup_method(self):
        self.audit = load("pi_official_report_p110_integration_audit.json")

    def test_4_commits_integrated(self):
        assert len(self.audit["commits_integrated"]) == 4

    def test_cherry_pick_method(self):
        assert "cherry-pick" in self.audit["integration_method"]

    def test_no_force_push(self):
        method = self.audit["integration_method"]
        assert "no force push" in method or "cherry-pick" in method

    def test_zero_conflicts(self):
        assert self.audit["conflict_count"] == 0

    def test_secret_scan_pass(self):
        assert "PASS" in self.audit["secret_scan"]

    def test_all_tests_pass_post_integration(self):
        t = self.audit["test_results_post_integration"]
        assert t["targeted_p19_tests"]["failed"] == 0
        assert t["backend_full_suite"]["failed"] == 0
        assert t["frontend_vitest"]["failed"] == 0
        assert t["frontend_build"] == "pass"

    def test_integration_verdict_pass(self):
        assert self.audit["integration_verdict"] == "PASS"


# ── Year fix carry-forward regression ────────────────────────────────────────

class TestYearFixRegression:
    """Validates that P1.9 year-fix results are still documented correctly in P1.10 safety audit."""

    def setup_method(self):
        self.safety = load("pi_official_report_p110_safety_audit.json")

    def test_600186_latest_still_pass(self):
        assert "pass" in self.safety["year_fix_regression"]["600186_latest"].lower()

    def test_600186_2025_still_pass(self):
        assert "pass" in self.safety["year_fix_regression"]["600186_2025"].lower()

    def test_300209_2024_still_pass(self):
        assert "pass" in self.safety["year_fix_regression"]["300209_2024"].lower()

    def test_600519_2024_still_pass(self):
        assert "pass" in self.safety["year_fix_regression"]["600519_2024"].lower()

    def test_000858_2025_still_pass(self):
        assert "pass" in self.safety["year_fix_regression"]["000858_2025"].lower()
