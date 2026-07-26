"""Phase 6U-E1.2 live shadow acceptance gate.

This script owns the artifact schema for real legacy-vs-layered shadow
acceptance. By default it is intentionally non-executing: live browser, DB, RAG,
and market-provider traffic must be explicitly enabled in a prepared
environment. The blocked artifact prevents hermetic latency or contract samples
from being mistaken for real cutover evidence.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_DIR = Path("backend/docs/artifacts")
RESULTS_PATH = ARTIFACT_DIR / "financial_agent_live_shadow_results.json"
SUMMARY_PATH = ARTIFACT_DIR / "financial_agent_live_shadow_summary.md"
INTENT_GATES_PATH = ARTIFACT_DIR / "financial_agent_intent_gates.json"
RUNTIME_GATE_PATH = ARTIFACT_DIR / "financial_agent_runtime_gate.json"

FIRST_BATCH_INTENTS = [
    "official_report_pdf",
    "quote_query",
    "financial_snapshot",
    "financial_report",
    "financial_comparison",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = [
        {
            "conversation_case": "A1_report_explicit_name",
            "query": "贵州茅台最新财报表现如何？",
            "intent": "financial_report",
            "coverage": ["explicit_cn_name", "continuous_chinese_entity", "report_indexed"],
        },
        {
            "conversation_case": "A2_comparison_pronoun_second_entity",
            "query": "那它和五粮液相比呢？",
            "intent": "financial_comparison",
            "coverage": ["pronoun_followup", "two_company_comparison"],
        },
        {
            "conversation_case": "A3_pdf_context",
            "query": "这份报告的官方 PDF 在哪里？",
            "intent": "official_report_pdf",
            "coverage": ["current_report_context", "official_url_available"],
        },
        {
            "conversation_case": "B1_quote_explicit_name",
            "query": "五粮液最新价是多少？",
            "intent": "quote_query",
            "coverage": ["explicit_cn_name", "quote_snapshot"],
        },
        {
            "conversation_case": "B2_snapshot_pronoun",
            "query": "它目前的财务表现呢？",
            "intent": "financial_snapshot",
            "coverage": ["pronoun_followup", "company_cache_hit"],
        },
        {
            "conversation_case": "C1_ambiguous_pingan",
            "query": "平安最新财报如何？",
            "intent": "financial_report",
            "coverage": ["ambiguous_entity", "clarification_required"],
        },
    ]
    dimensions = {
        "official_report_pdf": [
            "explicit_company",
            "report_not_found",
            "official_url_available",
            "current_report_context",
            "stale_cache",
            "auth_db_503",
            "rag_unavailable",
            "page_context",
            "code_query",
            "continuous_chinese_entity",
        ],
        "quote_query": [
            "cn_quote",
            "hk_quote",
            "us_no_current_coverage",
            "stale_quote",
            "market_closed",
            "code_query",
            "page_context",
            "auth_db_503",
            "partial_data",
            "continuous_chinese_entity",
        ],
        "financial_snapshot": [
            "company_cache_hit",
            "partial_fields",
            "industry_not_applicable",
            "provider_unavailable",
            "stale_cache",
            "different_industry",
            "page_context",
            "code_query",
            "auth_db_503",
            "rag_unavailable",
        ],
        "financial_report": [
            "explicit_cn_name",
            "explicit_code",
            "continuous_chinese_entity",
            "report_indexed",
            "rag_unavailable_cached_snapshot",
            "report_year_mismatch",
            "page_context",
            "auth_db_503",
            "partial_data",
            "different_industry",
        ],
        "financial_comparison": [
            "two_explicit_companies",
            "pronoun_plus_second_entity",
            "three_company_comparison",
            "period_mismatch",
            "one_side_missing_fields",
            "different_industry",
            "page_context",
            "auth_db_503",
            "rag_unavailable_cached_snapshot",
            "stale_cache",
        ],
    }
    for intent, items in dimensions.items():
        for idx, item in enumerate(items, start=1):
            cases.append({
                "conversation_case": f"{intent}_{idx:02d}_{item}",
                "query": f"{intent} acceptance case: {item}",
                "intent": intent,
                "coverage": [item],
            })
    return cases


def _blocked_case(case: dict[str, Any], idx: int, reason: str) -> dict[str, Any]:
    return {
        "trace_id": f"live_shadow_blocked_{idx:03d}",
        "intent": case["intent"],
        "entities": [],
        "conversation_case": case["conversation_case"],
        "query_fingerprint": f"case_{idx:03d}",
        "coverage": case.get("coverage") or [],
        "legacy": {
            "status": "not_run",
            "route": None,
            "answer_present": False,
            "numeric_facts": [],
            "periods": [],
            "latency_ms": None,
            "db_queries": None,
            "tool_calls": [],
            "llm_calls": None,
            "error_code": reason,
        },
        "layered": {
            "status": "not_run",
            "route": None,
            "plan": {},
            "answer_present": False,
            "numeric_facts": [],
            "periods": [],
            "evidence_ids": [],
            "latency_ms": None,
            "db_queries": None,
            "tool_calls": [],
            "llm_calls": None,
            "error_code": reason,
        },
        "comparison": {
            "intent_match": None,
            "entity_match": None,
            "period_match": None,
            "numeric_fact_match_rate": None,
            "unsupported_numeric_fact_count": None,
            "unsupported_causal_claim_count": None,
            "missing_fact_count": None,
            "latency_delta_ms": None,
            "decision": "blocked_live_not_executed",
        },
    }


def _metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    executed = [case for case in cases if case["legacy"]["status"] != "not_run" or case["layered"]["status"] != "not_run"]
    if not executed:
        return {
            "executed_sample_count": 0,
            "intent_match_rate": None,
            "entity_match_rate": None,
            "numeric_fact_match_rate": None,
            "unsupported_numeric_fact_count": None,
            "unsupported_causal_claim_count": None,
            "stale_as_realtime_count": None,
            "annual_quarter_mismatch_count": None,
            "null_filled_as_zero_count": None,
            "cross_company_evidence_contamination_count": None,
            "context_corruption_count": None,
            "message_double_write_count": None,
            "db_session_across_llm_count": None,
            "private_daemon_loop_in_layered_path": None,
            "cold_latency_p50_ms": None,
            "cold_latency_p95_ms": None,
            "warm_latency_p50_ms": None,
            "warm_latency_p95_ms": None,
            "db_query_delta_p50": None,
            "tool_call_delta_p50": None,
            "llm_call_delta_p50": None,
        }
    # The live execution implementation will populate concrete per-case values.
    raise NotImplementedError("live execution metrics require executed cases")


def _blocked_results(
    reason: str,
    *,
    live_external_status: str = "not_run",
    live_external_passed: int | None = None,
    live_external_skipped: int | None = None,
    live_external_failed: int | None = None,
    live_external_reason: str | None = None,
    soak_status: str = "not_run",
    soak_passed: int | None = None,
    soak_skipped: int | None = None,
    soak_failed: int | None = None,
    soak_reason: str | None = None,
) -> dict[str, Any]:
    planned = _base_cases()
    cases = [_blocked_case(case, idx, reason) for idx, case in enumerate(planned, start=1)]
    counts = Counter(case["intent"] for case in planned)
    return {
        "schema_version": "financial_agent_live_shadow.v1",
        "generated_at": _now(),
        "mode": "live_shadow_required_not_executed",
        "execution_status": "blocked",
        "block_reason": reason,
        "requested_sample_count": len(planned),
        "executed_sample_count": 0,
        "intent_sample_counts": dict(sorted(counts.items())),
        "market_sampling": {
            "CN": {"requested": 100, "executed": 0, "reason": "live StockMaster sampling not executed"},
            "HK": {"requested": 30, "executed": 0, "reason": "live StockMaster sampling not executed"},
            "US": {"requested": 0, "executed": 0, "reason": "current requested coverage is 0 and must not be overstated"},
        },
        "cases": cases,
        "metrics": _metrics(cases),
        "db_reliability": {
            "auth_cache_hit_verified": False,
            "db_timeout_503_verified": False,
            "pool_checked_out_returned_to_baseline": False,
            "cancelled_connection_rollback_storm": "not_run",
            "session_across_llm": "not_run",
        },
        "browser_acceptance": {
            "status": "not_run",
            "normal_user_saw_legacy_only": None,
            "trace_concise": None,
            "sources_collapsed": None,
            "disclaimer_once": None,
            "input_preserved_after_503": None,
            "shadow_hidden": None,
        },
        "live_external_suite": {
            "integration_live_or_live_external": {
                "status": live_external_status,
                "passed": live_external_passed,
                "skipped": live_external_skipped,
                "failed": live_external_failed,
                "reason": live_external_reason,
            },
            "soak": {
                "status": soak_status,
                "passed": soak_passed,
                "skipped": soak_skipped,
                "failed": soak_failed,
                "reason": soak_reason,
            },
        },
        "side_effects": {
            "message_writes": 0,
            "context_writes": 0,
            "watchlist_writes": 0,
            "report_writes": 0,
            "job_writes": 0,
        },
    }


def _intent_gates(results: dict[str, Any]) -> dict[str, Any]:
    gates: dict[str, Any] = {
        "schema_version": "financial_agent_intent_gates.v1",
        "generated_at": _now(),
        "authorized_intents": [],
        "intents": {},
    }
    counts = results.get("intent_sample_counts") or {}
    for intent in FIRST_BATCH_INTENTS:
        gates["intents"][intent] = {
            "passed": False,
            "requested_samples": int(counts.get(intent) or 0),
            "executed_samples": 0,
            "intent_match_rate": None,
            "entity_match_rate": None,
            "unsupported_facts": None,
            "required_data_provenance": None,
            "browser_acceptance_passed": False,
            "p95_latency_acceptable": False,
            "db_session_reliability_passed": False,
            "fallback_behavior_passed": False,
            "blockers": [
                "live_shadow_samples_not_executed",
                "browser_acceptance_not_recorded",
                "live_external_suite_not_run",
            ],
        }
    return gates


def _runtime_gate(results: dict[str, Any], intent_gates: dict[str, Any], *, default_full_local_passed: bool | None) -> dict[str, Any]:
    metrics = results.get("metrics") or {}
    blockers = [
        "live_shadow_samples_not_executed",
        "browser_acceptance_not_recorded",
        "live_security_master_sampling_not_run",
        "live_external_suite_not_run",
    ]
    return {
        "schema_version": "financial_agent_runtime_gate.v1",
        "generated_at": _now(),
        "default_full_passed": bool(default_full_local_passed),
        "default_full_local_passed": default_full_local_passed,
        "shadow_passed": False,
        "live_shadow_passed": False,
        "layered_enabled": False,
        "authorized_intents": [],
        "recommended_next_intent": None,
        "intent_gates": intent_gates["intents"],
        "criteria": {
            "executed_sample_count": metrics.get("executed_sample_count"),
            "intent_match_rate": metrics.get("intent_match_rate"),
            "entity_match_rate": metrics.get("entity_match_rate"),
            "numeric_fact_match_rate": metrics.get("numeric_fact_match_rate"),
            "unsupported_numeric_fact_count": metrics.get("unsupported_numeric_fact_count"),
            "unsupported_causal_claim_count": metrics.get("unsupported_causal_claim_count"),
            "context_corruption_count": metrics.get("context_corruption_count"),
            "message_double_write_count": metrics.get("message_double_write_count"),
            "db_session_across_llm_count": metrics.get("db_session_across_llm_count"),
            "private_daemon_loop_in_layered_path": metrics.get("private_daemon_loop_in_layered_path"),
            "warm_latency_p95_ms": metrics.get("warm_latency_p95_ms"),
            "cold_latency_p95_ms": metrics.get("cold_latency_p95_ms"),
        },
        "blockers": blockers,
        "decision": "do_not_enable_layered_v1",
    }


def _summary(results: dict[str, Any], intent_gates: dict[str, Any], runtime_gate: dict[str, Any]) -> str:
    metrics = results["metrics"]
    lines = [
        "# Financial Agent Live Shadow Summary",
        "",
        f"- Mode: `{results['mode']}`",
        f"- Execution status: `{results['execution_status']}`",
        f"- Requested sample count: `{results['requested_sample_count']}`",
        f"- Executed sample count: `{results['executed_sample_count']}`",
        f"- Intent sample counts: `{json.dumps(results['intent_sample_counts'], ensure_ascii=False)}`",
        f"- Intent match: `{metrics['intent_match_rate']}`",
        f"- Entity match: `{metrics['entity_match_rate']}`",
        f"- Numeric fact match: `{metrics['numeric_fact_match_rate']}`",
        f"- Unsupported numeric facts: `{metrics['unsupported_numeric_fact_count']}`",
        f"- Cold latency p50/p95: `{metrics['cold_latency_p50_ms']}` / `{metrics['cold_latency_p95_ms']}`",
        f"- Warm latency p50/p95: `{metrics['warm_latency_p50_ms']}` / `{metrics['warm_latency_p95_ms']}`",
        f"- Live external suite: `{json.dumps(results['live_external_suite']['integration_live_or_live_external'], ensure_ascii=False)}`",
        f"- Soak suite: `{json.dumps(results['live_external_suite']['soak'], ensure_ascii=False)}`",
        f"- Layered enabled: `{runtime_gate['layered_enabled']}`",
        f"- Authorized intents: `{runtime_gate['authorized_intents']}`",
        "",
        "## Intent Gates",
        "",
    ]
    for intent, gate in intent_gates["intents"].items():
        lines.append(f"- `{intent}`: passed=`{gate['passed']}`, executed_samples=`{gate['executed_samples']}`, blockers=`{', '.join(gate['blockers'])}`")
    lines.extend([
        "",
        "## Runtime Gate",
        "",
        f"`{runtime_gate['decision']}`",
        "",
        "## Blockers",
        "",
        *[f"- {item}" for item in runtime_gate["blockers"]],
        "",
        "This is not a hermetic latency artifact. If live execution is blocked, no sample is counted as accepted.",
    ])
    return "\n".join(lines) + "\n"


def generate_blocked_artifacts(
    *,
    output_dir: Path,
    reason: str,
    default_full_local_passed: bool | None,
    live_external_status: str = "not_run",
    live_external_passed: int | None = None,
    live_external_skipped: int | None = None,
    live_external_failed: int | None = None,
    live_external_reason: str | None = None,
    soak_status: str = "not_run",
    soak_passed: int | None = None,
    soak_skipped: int | None = None,
    soak_failed: int | None = None,
    soak_reason: str | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = _blocked_results(
        reason,
        live_external_status=live_external_status,
        live_external_passed=live_external_passed,
        live_external_skipped=live_external_skipped,
        live_external_failed=live_external_failed,
        live_external_reason=live_external_reason,
        soak_status=soak_status,
        soak_passed=soak_passed,
        soak_skipped=soak_skipped,
        soak_failed=soak_failed,
        soak_reason=soak_reason,
    )
    intent_gates = _intent_gates(results)
    runtime_gate = _runtime_gate(results, intent_gates, default_full_local_passed=default_full_local_passed)
    paths = {
        "results": output_dir / RESULTS_PATH.name,
        "summary": output_dir / SUMMARY_PATH.name,
        "intent_gates": output_dir / INTENT_GATES_PATH.name,
        "runtime_gate": output_dir / RUNTIME_GATE_PATH.name,
    }
    paths["results"].write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["intent_gates"].write_text(json.dumps(intent_gates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["runtime_gate"].write_text(json.dumps(runtime_gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["summary"].write_text(_summary(results, intent_gates, runtime_gate), encoding="utf-8")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ARTIFACT_DIR))
    parser.add_argument("--execute-live", action="store_true", help="Reserved for prepared live environments; not enabled by default.")
    parser.add_argument("--default-full-local-passed", action="store_true")
    parser.add_argument("--live-external-status", default="not_run")
    parser.add_argument("--live-external-passed", type=int)
    parser.add_argument("--live-external-skipped", type=int)
    parser.add_argument("--live-external-failed", type=int)
    parser.add_argument("--live-external-reason")
    parser.add_argument("--soak-status", default="not_run")
    parser.add_argument("--soak-passed", type=int)
    parser.add_argument("--soak-skipped", type=int)
    parser.add_argument("--soak-failed", type=int)
    parser.add_argument("--soak-reason")
    args = parser.parse_args()
    reason = "LIVE_SHADOW_NOT_EXECUTED"
    if args.execute_live:
        reason = "LIVE_SHADOW_EXECUTION_NOT_CONFIGURED_IN_THIS_RUNNER"
    paths = generate_blocked_artifacts(
        output_dir=Path(args.output_dir),
        reason=reason,
        default_full_local_passed=args.default_full_local_passed,
        live_external_status=args.live_external_status,
        live_external_passed=args.live_external_passed,
        live_external_skipped=args.live_external_skipped,
        live_external_failed=args.live_external_failed,
        live_external_reason=args.live_external_reason,
        soak_status=args.soak_status,
        soak_passed=args.soak_passed,
        soak_skipped=args.soak_skipped,
        soak_failed=args.soak_failed,
        soak_reason=args.soak_reason,
    )
    print(json.dumps({key: str(path) for key, path in paths.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
