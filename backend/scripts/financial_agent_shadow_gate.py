"""Generate layered financial runtime shadow-gate artifacts.

The default mode is hermetic and contract-only: it does not call live DB,
CNINFO, BaoStock, RAG workers, or LLMs. It creates a stable artifact shape for
legacy-vs-layered shadow comparison and keeps the cutover gate closed until
real browser/live shadow evidence is supplied.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_DIR = Path("backend/docs/artifacts")
RESULTS_PATH = ARTIFACT_DIR / "financial_agent_shadow_results.json"
SUMMARY_PATH = ARTIFACT_DIR / "financial_agent_shadow_summary.md"
GATE_PATH = ARTIFACT_DIR / "financial_agent_runtime_gate.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scenario_matrix() -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for intent, cases in {
        "financial_report": [
            "explicit_cn_name",
            "explicit_code",
            "continuous_chinese_name",
            "report_indexed",
            "rag_unavailable_cached_snapshot",
        ],
        "financial_comparison": [
            "two_explicit_companies",
            "pronoun_plus_second_entity",
            "three_companies",
            "period_mismatch",
            "one_side_missing_fields",
        ],
        "official_report_pdf": [
            "current_report_context",
            "explicit_company",
            "report_not_found",
            "official_url_available",
        ],
        "financial_snapshot": [
            "company_cache_hit",
            "partial_fields",
            "industry_not_applicable",
            "provider_unavailable",
        ],
        "quote_query": [
            "cn_quote",
            "hk_quote",
            "us_no_data_architecture",
            "stale_quote",
            "market_closed",
        ],
    }.items():
        for case in cases:
            scenarios.append({"intent": intent, "case": case})
    return scenarios


def _run_contract_shadow() -> dict[str, Any]:
    started = time.perf_counter()
    runs: list[dict[str, Any]] = []
    for idx, scenario in enumerate(_scenario_matrix(), start=1):
        trace_id = f"shadow_contract_{idx:03d}"
        intent = scenario["intent"]
        entities = [{"market": "CN", "symbol": "SAMPLE", "entity_type": "equity"}]
        if intent == "financial_comparison":
            entities.append({"market": "CN", "symbol": "SAMPLE2", "entity_type": "equity"})
        if scenario["case"] == "us_no_data_architecture":
            entities = [{"market": "US", "symbol": "SAMPLE", "entity_type": "equity"}]
        if scenario["case"] == "hk_quote":
            entities = [{"market": "HK", "symbol": "00001", "entity_type": "equity"}]

        legacy_status = "success"
        layered_status = "success"
        if "unavailable" in scenario["case"] or "missing" in scenario["case"] or "not_found" in scenario["case"]:
            layered_status = "partial_success" if scenario["case"] != "report_not_found" else "unavailable"
        runs.append({
            "trace_id": trace_id,
            "intent": intent,
            "scenario": scenario,
            "entities": entities,
            "legacy": {
                "route": "legacy_skill_registry",
                "status": legacy_status,
                "answer_present": True,
                "metrics": [],
                "evidence_ids": [],
                "latency_ms": 120,
                "error_code": None,
            },
            "layered": {
                "route": "layered_v1_contract",
                "plan": {"intent": intent, "tools": _tools_for_intent(intent)},
                "tools": [{"capability": cap, "status": layered_status} for cap in _tools_for_intent(intent)],
                "status": layered_status,
                "answer_present": layered_status in {"success", "partial_success"},
                "metrics": [],
                "evidence_ids": [],
                "latency_ms": 100,
                "error_code": None if layered_status != "unavailable" else "DATA_UNAVAILABLE",
            },
            "comparison": {
                "intent_match": True,
                "entity_match": True,
                "period_match": True,
                "numeric_fact_match": True,
                "unsupported_fact_count": 0,
                "missing_fact_count": 0 if layered_status == "success" else 1,
                "latency_delta_ms": -20,
                "tool_call_count_delta": len(_tools_for_intent(intent)) - 1,
                "decision": "contract_pass_live_required",
            },
        })
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "schema_version": "financial_agent_shadow.v1",
        "generated_at": _now(),
        "mode": "hermetic_contract",
        "sample_count": len(runs),
        "market_sample": {
            "CN": {"requested": 100, "executed": 0, "reason": "live security master sampling not run in hermetic mode"},
            "HK": {"requested": 30, "executed": 0, "reason": "live security master sampling not run in hermetic mode"},
            "US": {"requested": 0, "executed": 0, "reason": "current local security master coverage is not asserted by hermetic gate"},
        },
        "runs": runs,
        "metrics": _metrics(runs, elapsed_ms),
    }


def _tools_for_intent(intent: str) -> list[str]:
    return {
        "financial_report": ["get_official_reports", "get_structured_report_financials", "query_report_evidence"],
        "financial_comparison": ["get_official_reports", "get_structured_report_financials", "compare_financials"],
        "official_report_pdf": ["get_official_report_url"],
        "financial_snapshot": ["get_financial_snapshot"],
        "quote_query": ["get_quote_snapshot"],
    }.get(intent, [])


def _metrics(runs: list[dict[str, Any]], elapsed_ms: int) -> dict[str, Any]:
    total = max(1, len(runs))
    intent_match = sum(1 for item in runs if item["comparison"]["intent_match"])
    entity_match = sum(1 for item in runs if item["comparison"]["entity_match"])
    latencies = [float(item["layered"]["latency_ms"]) for item in runs]
    return {
        "elapsed_ms": elapsed_ms,
        "intent_match_rate": round(intent_match / total, 4),
        "entity_match_rate": round(entity_match / total, 4),
        "unsupported_numeric_fact_count": sum(item["comparison"]["unsupported_fact_count"] for item in runs),
        "unsupported_causal_claim_count": 0,
        "stale_as_realtime_count": 0,
        "annual_quarter_mismatch_count": 0,
        "null_filled_as_zero_count": 0,
        "context_corruption_count": 0,
        "message_double_write_count": 0,
        "db_session_across_llm_count": 0,
        "private_daemon_loop_in_layered_path": 0,
        "latency_p50_ms": statistics.median(latencies) if latencies else None,
        "latency_p95_ms": sorted(latencies)[int(0.95 * (len(latencies) - 1))] if latencies else None,
    }


def _gate_payload(results: dict[str, Any], *, default_full_local_passed: bool | None = None) -> dict[str, Any]:
    metrics = results["metrics"]
    blockers = [
        "real_legacy_vs_layered_shadow_not_run",
        "browser_acceptance_not_recorded",
        "live_security_master_sampling_not_run",
        "full_backend_live_external_tests_are_excluded_from_default_and_require_separate_environment",
    ]
    return {
        "schema_version": "financial_agent_runtime_gate.v1",
        "generated_at": _now(),
        "default_full_passed": bool(default_full_local_passed),
        "default_full_local_passed": default_full_local_passed,
        "shadow_passed": False,
        "layered_enabled": False,
        "authorized_intents": [],
        "criteria": {
            "intent_match_rate": metrics["intent_match_rate"],
            "entity_match_rate": metrics["entity_match_rate"],
            "unsupported_numeric_fact_count": metrics["unsupported_numeric_fact_count"],
            "context_corruption_count": metrics["context_corruption_count"],
            "message_double_write_count": metrics["message_double_write_count"],
            "private_daemon_loop_in_layered_path": metrics["private_daemon_loop_in_layered_path"],
        },
        "blockers": blockers,
        "decision": "do_not_enable_layered_v1",
    }


def _summary_markdown(results: dict[str, Any], gate: dict[str, Any]) -> str:
    metrics = results["metrics"]
    return "\n".join([
        "# Financial Agent Shadow Summary",
        "",
        f"- Mode: `{results['mode']}`",
        f"- Shadow sample count: `{results['sample_count']}`",
        f"- Intent match: `{metrics['intent_match_rate']}`",
        f"- Entity match: `{metrics['entity_match_rate']}`",
        f"- Unsupported numeric facts: `{metrics['unsupported_numeric_fact_count']}`",
        f"- Context corruption: `{metrics['context_corruption_count']}`",
        f"- Message double write: `{metrics['message_double_write_count']}`",
        f"- Default full local passed: `{gate['default_full_local_passed']}`",
        f"- Layered enabled: `{gate['layered_enabled']}`",
        "",
        "## Gate Decision",
        "",
        f"`{gate['decision']}`",
        "",
        "## Blockers",
        "",
        *[f"- {item}" for item in gate["blockers"]],
        "",
        "This artifact is a contract gate, not a live browser acceptance report.",
    ]) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ARTIFACT_DIR))
    parser.add_argument(
        "--default-full-local-passed",
        action="store_true",
        help="Record that the local default backend suite has been run and passed.",
    )
    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = _run_contract_shadow()
    gate = _gate_payload(results, default_full_local_passed=args.default_full_local_passed)
    (out_dir / RESULTS_PATH.name).write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / GATE_PATH.name).write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / SUMMARY_PATH.name).write_text(_summary_markdown(results, gate), encoding="utf-8")
    print(json.dumps({"results": str(out_dir / RESULTS_PATH.name), "gate": str(out_dir / GATE_PATH.name), "summary": str(out_dir / SUMMARY_PATH.name)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
