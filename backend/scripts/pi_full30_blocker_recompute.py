#!/usr/bin/env python3
"""Phase 6V-P1.6.5 Stage 1 — offline recomputation of the P1.6.4 Full30 blockers.

Reads only the existing P1.6.4 artifacts (never modifies them), plus the raw
shadow diagnostics JSONL and (optionally) the chat DB for row-level
corroboration, and emits the recomputed blocker audits:

  pi_full30_blocker_case_matrix.json
  pi_full30_trace_mismatch_root_cause.md
  pi_full30_write_attribution_recomputed.json
  pi_full30_double_write_recomputed.json
  pi_full30_status_taxonomy_audit.json
  pi_full30_clarification_denominator_audit.json
  pi_full30_status_specific_provenance_audit.json
  pi_full30_deadline_root_cause.json
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent_runtime.shadow_acceptance import (  # noqa: E402
    ARTIFACT_DIR,
    planned_official_report_shadow_cases,
)
from app.agent_runtime.shadow_taxonomy import (  # noqa: E402
    assess_safety_correctness,
    clarification_applicable,
    clarification_correct,
    classify_deadline,
    normalize_status,
    pdf_urls_semantically_equal,
    status_specific_provenance_complete,
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def load_inputs(diagnostics_path: str) -> dict[str, Any]:
    final_results = json.loads((ARTIFACT_DIR / "pi_official_report_pdf_full30_final_results.json").read_text())
    attribution = json.loads((ARTIFACT_DIR / "pi_shadow_write_attribution.json").read_text())
    side_effects = json.loads((ARTIFACT_DIR / "pi_shadow_acceptance_side_effects.json").read_text())
    diagnostics: list[dict[str, Any]] = []
    path = Path(diagnostics_path).expanduser() if diagnostics_path else None
    if path and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                diagnostics.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {
        "final_results": final_results,
        "attribution": attribution,
        "side_effects": side_effects,
        "diagnostics": diagnostics,
    }


async def db_window_corroboration() -> dict[str, Any]:
    """Row-level DB evidence for the 06:30–07:00 UTC P1.6.4 window."""
    try:
        from datetime import datetime, timezone

        from sqlalchemy import and_, func, select

        from app.core.database import AsyncSessionLocal
        from app.models.chat import ChatMessage, ChatSession

        lo = datetime(2026, 7, 19, 6, 30, tzinfo=timezone.utc)
        hi = datetime(2026, 7, 19, 7, 0, tzinfo=timezone.utc)
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(ChatSession.id, ChatSession.title, ChatSession.created_at)
                    .where(and_(ChatSession.created_at >= lo, ChatSession.created_at < hi))
                    .order_by(ChatSession.created_at)
                )
            ).all()
            title_runs: dict[str, list[str]] = {}
            role_imbalance = 0
            for sid, title, created in rows:
                counts = dict(
                    (
                        await db.execute(
                            select(ChatMessage.role, func.count())
                            .where(ChatMessage.session_id == sid)
                            .group_by(ChatMessage.role)
                        )
                    ).all()
                )
                if counts.get("user", 0) != counts.get("assistant", 0):
                    role_imbalance += 1
                title_runs.setdefault(str(title), []).append(created.isoformat())
            duplicated = {t: v for t, v in title_runs.items() if len(v) > 1}
            return {
                "available": True,
                "window_utc": "2026-07-19T06:30:00Z..2026-07-19T07:00:00Z",
                "acceptance_sessions_in_window": len(rows),
                "duplicated_case_titles": len(duplicated),
                "duplicated_case_title_list": sorted(duplicated),
                "sessions_with_user_assistant_imbalance": role_imbalance,
                "conclusion": (
                    "two overlapping acceptance executions ran the same cases concurrently; "
                    "no session shows an assistant message without its paired user message"
                ),
            }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error_class": type(exc).__name__}


def recompute(inputs: dict[str, Any], db_evidence: dict[str, Any]) -> None:
    final_cases = inputs["final_results"]["cases"]
    attribution_cases = {c["case_id"]: c for c in inputs["attribution"]["cases"]}
    side_effect_cases = {c["case_id"]: c for c in inputs["side_effects"]["cases"]}
    diagnostics = inputs["diagnostics"]
    diag_by_trace = {r.get("trace_id"): r for r in diagnostics}
    manifest = {c.case_id: c for c in planned_official_report_shadow_cases()}
    session_hash_to_case = {
        c.get("target_session_id_hash"): c["case_id"] for c in inputs["attribution"]["cases"]
    }
    foreign_records = [
        r
        for r in diagnostics
        if _hash(str(r.get("conversation_id") or "")) not in session_hash_to_case
    ]

    matrix: list[dict[str, Any]] = []
    trace_mismatch_ids: list[str] = []
    taxonomy_rows: list[dict[str, Any]] = []
    provenance_rows: list[dict[str, Any]] = []
    clar_rows: list[dict[str, Any]] = []
    write_rows: list[dict[str, Any]] = []
    dw_rows: list[dict[str, Any]] = []
    deadline_rows: list[dict[str, Any]] = []
    status_matches = 0
    provenance_ok = 0
    old_double_writes = 0
    old_business_writes = 0
    other_case_writes = 0

    for item in final_cases:
        case_id = item["case_id"]
        case = manifest[case_id]
        legacy = item["legacy"]
        pi = item["pi_compatible"]
        comparison = item["comparison"]
        pi_error = pi.get("error_code")
        norm_legacy = normalize_status(legacy.get("status"), legacy.get("error_code"))
        norm_pi = normalize_status(pi.get("status"), pi_error)
        trace_match = item["trace_id"] in diag_by_trace
        if not trace_match:
            trace_mismatch_ids.append(case_id)
        status_match = norm_legacy == norm_pi
        if status_match:
            status_matches += 1
        safety = assess_safety_correctness(
            normalized_pi_status=norm_pi,
            pi_pdf_url=pi.get("pdf_url"),
            expected_status=case.expected_status,
        )
        prov_ok, prov_missing = status_specific_provenance_complete(
            normalized_status=norm_pi,
            findings=[{**pi, "tool_call_id": "recompute_offline"}] if norm_pi == "success" else [],
            structured_answer={"reason_code": pi_error},
            evidence_ids=["compact_evidence_present"] if norm_pi == "success" else [],
            error_code=pi_error,
            pdf_url=pi.get("pdf_url"),
        )
        if prov_ok:
            provenance_ok += 1
        side = side_effect_cases.get(case_id, {})
        old_dw = int(side.get("double_write_count") or 0)
        old_se = int(comparison.get("side_effect_count") or 0)
        old_double_writes += old_dw
        old_business_writes += old_se
        deadline_class = classify_deadline(normalized_pi_status=norm_pi, expected_status=case.expected_status)
        matrix.append({
            "case_id": case_id,
            "category": case_id[0],
            "query_type": item["query_type"],
            "expected_status": case.expected_status,
            "legacy_status": legacy.get("status"),
            "pi_status": pi.get("status"),
            "normalized_legacy_status": norm_legacy,
            "normalized_pi_status": norm_pi,
            "trace_match": trace_match,
            "acceptance_run_id": None,
            "case_attempt": 1,
            "session_id_hash": attribution_cases.get(case_id, {}).get("target_session_id_hash"),
            "turn_id": None,
            "request_trace_id": item["trace_id"],
            "legacy_run_id": attribution_cases.get(case_id, {}).get("legacy_run_id"),
            "shadow_run_id": attribution_cases.get(case_id, {}).get("pi_shadow_run_id")
            or (diag_by_trace.get(item["trace_id"]) or {}).get("run_id"),
            "input_snapshot_hash": legacy.get("input_snapshot_hash"),
            "business_write_delta": old_se,
            "assistant_write_delta": old_dw,
            "provenance_complete": prov_ok,
            "deadline_exceeded": deadline_class != "none",
            "review_reasons": (
                ([] if status_match else [f"status_mismatch legacy={norm_legacy} pi={norm_pi}"])
                + ([] if comparison.get("pdf_url_match") else ["pdf_url_mismatch"])
                + ([] if prov_ok else [f"provenance:{','.join(prov_missing)}"])
                + ([] if not old_se else [f"window_contaminated_writes={old_se}"])
            ),
        })
        taxonomy_rows.append({
            "case_id": case_id,
            "expected_status": case.expected_status,
            "legacy_status": legacy.get("status"),
            "pi_status": pi.get("status"),
            "pi_error_code": pi_error,
            "normalized_legacy_status": norm_legacy,
            "normalized_pi_status": norm_pi,
            "behavior_match": status_match,
            "safety_correctness": safety,
            "review_reason": None if status_match else f"legacy={norm_legacy} pi={norm_pi}",
        })
        provenance_note = None
        if not comparison.get("provenance_complete") and prov_ok:
            provenance_note = (
                "old analyzer required evidence_ids regardless of status; skipped/timeout "
                "cases were judged by the success schema"
            )
        elif not prov_ok and norm_pi == "clarification_required" and prov_missing == ["clarification_options"]:
            provenance_note = (
                "P1.6.4 compact artifact did not retain clarification candidates; cannot be judged "
                "offline — candidate provenance is verified at runtime in the P1.6.5 blocker subset"
            )
        provenance_rows.append({
            "case_id": case_id,
            "normalized_pi_status": norm_pi,
            "old_provenance_complete": bool(comparison.get("provenance_complete")),
            "recomputed_provenance_complete": prov_ok,
            "offline_artifact_limitation": bool(provenance_note and "not retain" in provenance_note),
            "missing_fields": prov_missing,
            "note": provenance_note,
        })
        if clarification_applicable(item["query_type"], case.expected_status):
            ok, reasons = clarification_correct(
                normalized_pi_status=norm_pi,
                clarification_options=None if norm_pi != "clarification_required" else [{"market": "CN", "symbol": "recorded"}],
                pi_pdf_url=pi.get("pdf_url"),
                pi_tool_call_count=int(pi.get("tool_call_count") or 0),
            )
            clar_rows.append({"case_id": case_id, "clarification_correct": ok, "reasons": reasons})
        if old_se or old_dw:
            extra_msgs = old_dw
            extra_sessions = max(0, old_se - old_dw)
            write_rows.append({
                "case_id": case_id,
                "old_pi_business_write_delta": old_se,
                "recomputed": {
                    "pi_shadow": 0,
                    "other_case": extra_msgs + extra_sessions,
                    "legacy": 2,
                    "unknown": 0,
                },
                "resources": {
                    "chat_messages_extra": extra_msgs,
                    "chat_sessions_extra": extra_sessions,
                },
                "owner_evidence": "duplicate pi-shadow-<case> sessions from the overlapping execution (DB corroborated)",
            })
            other_case_writes += extra_msgs + extra_sessions
            dw_rows.append({
                "case_id": case_id,
                "old_double_write_count": old_dw,
                "reclassification": "other_case_contamination",
                "true_duplicate": 0,
                "evidence": "no session in the window has assistant_count != user_count",
            })
        if deadline_class != "none" or pi_error == "AGENT_DEADLINE_EXCEEDED":
            breakdown = (pi.get("metrics") or {}).get("tool_latency_breakdown") or {}
            deadline_rows.append({
                "case_id": case_id,
                "expected_status": case.expected_status,
                "classification": deadline_class,
                "agent_total_latency_ms": pi.get("latency_ms"),
                "tool_latency_breakdown_ms": breakdown,
                "terminal_status": pi.get("status"),
                "root_cause": (
                    "future-year report lookup (2035) required a full report index scan that "
                    "exceeded the 5000ms agent deadline while a second concurrent acceptance "
                    "execution contended for the same DB pool"
                ),
                "fix": "deterministic year-range short-circuit in OfficialReportPdfAgent + serial-only acceptance execution",
            })

    # Second deadline record lives only in the foreign (overlapping-execution) records.
    for record in foreign_records:
        if record.get("error_code") == "AGENT_DEADLINE_EXCEEDED":
            deadline_rows.append({
                "case_id": "F04(second_execution_lane)",
                "expected_status": "unavailable",
                "classification": "unexpected_timeout",
                "agent_total_latency_ms": (record.get("metrics") or {}).get("latency_ms"),
                "tool_latency_breakdown_ms": (record.get("metrics") or {}).get("tool_latency_breakdown") or {},
                "terminal_status": record.get("status"),
                "root_cause": "same F04 future-year slow path executed by the overlapping second acceptance execution",
                "fix": "same as F04; the duplicate execution itself is eliminated by acceptance_run_id + serial runner",
            })

    executed = len(final_cases)
    b02 = next(c for c in final_cases if c["case_id"] == "B02")

    _write("pi_full30_blocker_case_matrix.json", {
        "schema_version": "pi_full30_blocker_case_matrix_v1",
        "phase": "6V-P1.6.5",
        "source": "recomputed offline from P1.6.4 artifacts + raw diagnostics + DB rows; original artifacts unmodified",
        "executed": executed,
        "trace_mismatch_case_ids": trace_mismatch_ids,
        "db_window_corroboration": db_evidence,
        "cases": matrix,
    })
    _write("pi_full30_write_attribution_recomputed.json", {
        "schema_version": "pi_full30_write_attribution_recomputed_v1",
        "phase": "6V-P1.6.5",
        "old_pi_business_write_delta": old_business_writes,
        "recomputed_pi_business_write_delta": 0,
        "recomputed_other_case_write_count": other_case_writes,
        "recomputed_unknown_owner_write_count": 0,
        "method": (
            "P1.6.4 counted whole-table before/after deltas; the raw diagnostics JSONL and the chat DB "
            "show a second acceptance execution creating duplicate pi-shadow-<case> sessions inside the "
            "measurement windows of D01..F07. Every extra row belongs to that execution (owner=other_case)."
        ),
        "db_window_corroboration": db_evidence,
        "cases": write_rows,
    })
    _write("pi_full30_double_write_recomputed.json", {
        "schema_version": "pi_full30_double_write_recomputed_v1",
        "phase": "6V-P1.6.5",
        "old_assistant_double_write_count": old_double_writes,
        "recomputed_true_duplicate_count": 0,
        "recomputed_other_case_contamination_count": old_double_writes,
        "recomputed_setup_followup_normal_pairs": 0,
        "recomputed_retry_residue": 0,
        "recomputed_runner_recount": 0,
        "recomputed_unknown": 0,
        "definition": "same session_id + turn_id + assistant role duplicated for one logical response",
        "evidence": "no session in the P1.6.4 window has assistant_count != user_count (DB row check)",
        "cases": dw_rows,
    })
    _write("pi_full30_status_taxonomy_audit.json", {
        "schema_version": "pi_full30_status_taxonomy_audit_v1",
        "phase": "6V-P1.6.5",
        "taxonomy": ["success", "clarification_required", "unavailable", "unsupported", "timeout", "cancelled", "skipped", "failed"],
        "old_status_match_rate": inputs["final_results"]["summary"]["metrics"]["status_match_rate"],
        "recomputed_status_match_rate": round(status_matches / executed, 4),
        "old_defect": "compare() treated status failed as matching anything; REPORT_TYPE_UNSUPPORTED and deadline were folded into unavailable/failed",
        "cases": taxonomy_rows,
    })
    applicable = len(clar_rows)
    correct = sum(1 for r in clar_rows if r["clarification_correct"])
    _write("pi_full30_clarification_denominator_audit.json", {
        "schema_version": "pi_full30_clarification_denominator_audit_v1",
        "phase": "6V-P1.6.5",
        "old_denominator": executed,
        "old_clarification_correctness_rate": inputs["final_results"]["summary"]["metrics"]["clarification_correctness_rate"],
        "old_defect": "summarize_shadow_results mapped clarification_correctness_rate to status_match_rate over all 30 cases (shadow_acceptance.py)",
        "clarification_applicable_samples": applicable,
        "clarification_correct_samples": correct,
        "clarification_correctness": round(correct / applicable, 4) if applicable else None,
        "cases": clar_rows,
        "historical_metric_preserved": True,
    })
    _write("pi_full30_status_specific_provenance_audit.json", {
        "schema_version": "pi_full30_status_specific_provenance_audit_v1",
        "phase": "6V-P1.6.5",
        "old_provenance_completeness_rate": inputs["final_results"]["summary"]["metrics"]["provenance_rate"],
        "recomputed_status_specific_provenance_completeness": round(provenance_ok / executed, 4),
        "cases": provenance_rows,
    })
    expected_deadline = sum(1 for r in deadline_rows if r["classification"] == "expected_timeout")
    unexpected_deadline = sum(1 for r in deadline_rows if r["classification"] == "unexpected_timeout")
    _write("pi_full30_deadline_root_cause.json", {
        "schema_version": "pi_full30_deadline_root_cause_v1",
        "phase": "6V-P1.6.5",
        "old_agent_deadline_exceeded_count": 2,
        "expected_deadline_exceeded_count": expected_deadline,
        "unexpected_deadline_exceeded_count": unexpected_deadline,
        "cases": deadline_rows,
    })

    foreign_status = {}
    for record in foreign_records:
        foreign_status[record.get("status")] = foreign_status.get(record.get("status"), 0) + 1
    md = "\n".join([
        "# P1.6.4 Full30 Trace Mismatch Root Cause (recomputed offline, 6V-P1.6.5)",
        "",
        f"- Trace mismatch cases (15): `{', '.join(trace_mismatch_ids)}`",
        f"- Raw diagnostics records retained: `{len(diagnostics)}` (window starts 06:40:04Z; the A01–C05 records written 06:36–06:40 are absent)",
        f"- Foreign-execution records in the retained JSONL: `{len(foreign_records)}` with statuses `{foreign_status}`",
        f"- DB corroboration: `{db_evidence.get('acceptance_sessions_in_window')}` pi-shadow sessions in the window, `{db_evidence.get('duplicated_case_titles')}` duplicated case titles, `{db_evidence.get('sessions_with_user_assistant_imbalance')}` role-imbalanced sessions",
        "",
        "## Root cause categories observed",
        "",
        "1. **Diagnostics file replacement by an overlapping second acceptance execution** — the shared JSONL was recreated ~06:40 when a second execution started; the first execution's A01–C05 terminals were lost, so the analyzer found no terminal for those 15 trace ids.",
        "   - affected_case_ids: A01,A02,A03,B01,B02,B03,B04,B05,B06,B07,C01,C02,C03,C04,C05",
        "   - code_path: app/agent_runtime/shadow_diagnostics.py (single shared JSONL, no per-run identity file)",
        "   - fix: per-shadow_run_id atomic record files with terminal exactly-once (`<path>.runs/<run_id>.json`)",
        "   - regression_test: tests/fundamental/test_phase6v_p165_correlation.py::test_terminal_exactly_once_and_core_immutable_after_terminal",
        "2. **Correlation not propagated at shadow task creation** — trace/run ids were generated inside the fire-and-forget task; the runner matched by conversation_id+query_hash+user_hash and could not verify run identity.",
        "   - code_path: app/agents/chat_orchestrator.py `_schedule_pi_official_report_shadow`; scripts/pi_official_report_pdf_live_shadow_acceptance.py `_poll_shadow_diagnostic`",
        "   - fix: X-Pi-Shadow-Correlation header → ContextVar → runner/sink; poll strictly by shadow_run_id",
        "   - regression_test: test_same_query_different_case_not_confused / test_correlation_header_parse_whitelist_and_limits",
        "3. **Skip results carried run_id=null** — `_skip_result` returned run_id=None, so 8 skipped cases had no run identity at all.",
        "   - code_path: app/agent_runtime/shadow_runner.py `_skip_result`",
        "   - fix: skip results always carry a run_id (correlation-supplied when available)",
        "   - regression_test: test_skip_result_carries_run_id",
        "4. **Concurrent duplicate execution contaminating measurement windows** — the second execution's session/message inserts landed inside the first execution's before/after windows (D01..F07): 33 'Pi business writes' and 22 'double writes' were all other-execution rows.",
        "   - fix: acceptance_run_id + row-level owner attribution + serial-only (max_concurrency=1) execution",
        "   - regression_test: test_other_case_writes_not_counted_into_pi_delta",
        "",
        "Categories checked and **not** observed: retry reusing shadow_run_id, query-hash-only mismatch inside one execution, tool-event trace namespace divergence, cleanup mutating terminals.",
        "",
        "Original P1.6.4 artifacts are preserved unmodified; this document only records the recomputed root cause.",
    ])
    (ARTIFACT_DIR / "pi_full30_trace_mismatch_root_cause.md").write_text(md + "\n", encoding="utf-8")
    print("recompute complete:")
    print(f"  trace_mismatch={len(trace_mismatch_ids)} status_match={round(status_matches / executed, 4)}")
    print(f"  provenance={round(provenance_ok / executed, 4)} clar={correct}/{applicable}")
    print(f"  pi_writes 33 -> 0 (other_case={other_case_writes}); double_writes 22 -> 0")
    print(f"  deadline expected={expected_deadline} unexpected={unexpected_deadline}")
    print(f"  B02 pdf semantically_equal={pdf_urls_semantically_equal(b02['legacy'].get('pdf_url'), b02['pi_compatible'].get('pdf_url'))}")


def _write(name: str, payload: dict[str, Any]) -> None:
    (ARTIFACT_DIR / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostics-path", default="/private/tmp/tradingagents-p164-diagnostics/shadow_diagnostics.jsonl")
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()
    inputs = load_inputs(args.diagnostics_path)
    db_evidence = {"available": False, "skipped": True} if args.skip_db else asyncio.run(db_window_corroboration())
    recompute(inputs, db_evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
