#!/usr/bin/env python3
"""HTTP live shadow acceptance for official_report_pdf_pi_v1."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.agent_runtime.contracts import new_id  # noqa: E402
from app.agent_runtime.shadow_acceptance import (  # noqa: E402
    ARTIFACT_DIR,
    blocker_subset_cases,
    blocker_subset_manifest,
    build_agent_gate,
    build_live_shadow_case_result,
    build_runtime_gate,
    build_write_attribution,
    capture_side_effect_snapshot,
    compute_pi_side_effect_count,
    list_new_chat_messages,
    list_new_chat_sessions,
    planned_official_report_shadow_cases,
    summarize_shadow_results,
    write_shadow_artifacts,
)
from app.agent_runtime.shadow_correlation import SHADOW_CORRELATION_HEADER  # noqa: E402
from app.agent_runtime.shadow_diagnostics import (  # noqa: E402
    pi_shadow_diagnostics_sink,
    query_hash,
    stable_payload_hash,
    user_hash,
)
from app.agent_runtime.shadow_taxonomy import (  # noqa: E402
    clarification_applicable,
    clarification_correct,
    classify_deadline,
    normalize_status,
)
from app.agent_runtime.shadow_write_attribution import attribute_turn_writes  # noqa: E402
from app.agent_runtime.shadow_runner import pi_compatible_shadow_runner  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.security_entity_resolver import get_security_index_metrics  # noqa: E402


DIAGNOSTICS_POLL_INTERVAL_SECONDS = 0.2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="official_report_pdf Pi shadow live acceptance")
    parser.add_argument("--execute", action="store_true", help="execute all live HTTP Chat shadow cases")
    parser.add_argument("--preflight-only", action="store_true", help="run preflight and write artifacts without executing cases")
    parser.add_argument("--environment-type", choices=["staging", "local_live", "local_fixture"], default=os.getenv("PI_SHADOW_ACCEPTANCE_ENVIRONMENT_TYPE", ""), help="acceptance environment type")
    parser.add_argument("--limit", type=int, default=30, help="maximum planned cases to execute; must remain 30 for Gate pass")
    parser.add_argument("--smoke", action="store_true", help="execute the fixed P1.5 three-case smoke set only")
    parser.add_argument("--stage2", action="store_true", help="execute the P1.6.5 three-case correlation regression (A01/C01/E01)")
    parser.add_argument("--blocker-subset", action="store_true", help="execute the fixed P1.6.5 blocker subset serially (not a formal Full30)")
    parser.add_argument("--base-url", default=os.getenv("PI_SHADOW_ACCEPTANCE_BASE_URL", ""), help="local/staging backend base URL")
    parser.add_argument("--frontend-base-url", default=os.getenv("PI_SHADOW_ACCEPTANCE_FRONTEND_BASE_URL", ""), help="local/staging frontend base URL")
    parser.add_argument("--access-token", default=os.getenv("PI_SHADOW_ACCEPTANCE_ACCESS_TOKEN", ""), help="acceptance service-account access token")
    parser.add_argument("--user-id", default=os.getenv("PI_SHADOW_ACCEPTANCE_USER_ID", ""), help="acceptance service-account user UUID")
    parser.add_argument("--allow-local-fixture-user", action="store_true", help="create/reuse a local fixture user and generate a short-lived project JWT")
    parser.add_argument("--stream", action="store_true", help="use SSE message endpoint and require stream completion")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    if not args.environment_type:
        args.environment_type = _infer_environment_type(args)
    if args.smoke:
        cases = _smoke_cases()
    elif args.stage2:
        cases = _stage2_cases()
    elif getattr(args, "blocker_subset", False):
        cases = blocker_subset_cases()
    else:
        cases = planned_official_report_shadow_cases()[: max(0, args.limit)]
    acceptance_run_id = new_id("acc")
    env_report = await build_environment_report(args)
    side_effect_report: dict[str, Any] = {"schema_version": "pi_shadow_side_effects_v1", "cases": []}
    side_effect_report["write_attribution"] = {"schema_version": "pi_shadow_write_attribution_v1", "cases": []}
    resolver_diagnostics: dict[str, Any] = {"schema_version": "pi_shadow_resolver_cache_diagnostics_v1", "cases": []}
    browser_markdown = _browser_markdown(executed=False, passed=False, notes="not_run: no authenticated browser session was provided to this runner")
    results: list[dict[str, Any]] = []

    blockers = list(env_report.get("blockers") or [])
    if not args.execute and not args.preflight_only:
        blockers.append("Runner was called without --execute.")
    identity = await resolve_acceptance_identity(args, env_report)
    if not identity.get("ready"):
        blockers.extend(identity.get("blockers") or [])

    acceptance_session_ids: set[str] = set()
    if args.execute and not blockers and not args.preflight_only:
        # max_concurrency=1: cases execute strictly serially; concurrent
        # execution corrupted P1.6.4 window-based write accounting.
        for case in cases:
            result, side_effect, resolver_case = await execute_http_case(
                case,
                args=args,
                identity=identity,
                acceptance_run_id=acceptance_run_id,
                acceptance_session_ids=acceptance_session_ids,
            )
            results.append(result)
            side_effect_report["cases"].append(side_effect)
            side_effect_report["write_attribution"]["cases"].append(side_effect["write_attribution"])
            resolver_diagnostics["cases"].append(resolver_case)

    summary = summarize_shadow_results(results, planned_samples=len(cases))
    _apply_v2_metrics(summary, results, cases)
    summary["acceptance_run_id"] = acceptance_run_id
    summary["environment"] = env_report
    summary["identity"] = {
        "method": identity.get("method"),
        "created_user": bool(identity.get("created_user")),
        "user_hash": user_hash(identity.get("user_id")),
        "token_present": bool(identity.get("access_token")),
    }
    summary["browser_acceptance"] = {"executed": False, "passed": False, "notes": "not_run"}
    summary["resolver_diagnostics"] = resolver_diagnostics
    if len(cases) == 3 and len(results) == 3:
        resolver_full_scans = sum(int(item.get("security_index_full_scan_count") or 0) for item in resolver_diagnostics["cases"])
        sql_exposure = 0 if (not bool(getattr(settings, "database_sql_echo", False)) and bool(getattr(settings, "database_sql_hide_parameters", True))) else 1
        if resolver_full_scans or sql_exposure:
            summary["smoke_passed"] = False
            summary["recommended_to_run_full_30"] = False
            summary["blockers"] = list(dict.fromkeys([
                *summary.get("blockers", []),
                *(["Warm resolver full scans were observed during smoke."] if resolver_full_scans else []),
                *(["SQL parameter logging is not safely disabled."] if sql_exposure else []),
            ]))
    if blockers:
        summary["blockers"] = list(dict.fromkeys([*summary.get("blockers", []), *blockers]))

    agent_gate = build_agent_gate(summary)
    runtime_gate = build_runtime_gate(agent_gate)
    if args.stage2 or getattr(args, "blocker_subset", False):
        subset_passed = _write_subset_artifacts(
            mode="stage2" if args.stage2 else "blocker_subset",
            results=results,
            summary=summary,
            side_effects=side_effect_report,
            env_report=env_report,
            planned=len(cases),
        )
        print(
            f"mode={'stage2' if args.stage2 else 'blocker_subset'} planned={len(cases)} executed={len(results)} "
            f"accepted={summary['accepted_samples']} subset_passed={subset_passed} decision=do_not_enable_pi_compatible"
        )
        if args.preflight_only:
            return 0 if env_report.get("environment_ready") and identity.get("ready") else 1
        return 0 if subset_passed else 1
    write_shadow_artifacts(
        results,
        summary,
        agent_gate,
        runtime_gate,
        environment=env_report,
        side_effects=side_effect_report,
        browser_acceptance_markdown=browser_markdown,
    )
    print(f"planned={len(cases)} executed={len(results)} accepted={summary['accepted_samples']} passed={agent_gate['passed']} decision={runtime_gate['decision']}")
    if args.preflight_only:
        return 0 if env_report.get("environment_ready") and identity.get("ready") else 1
    if not args.execute:
        return 0
    if len(cases) == 3 and agent_gate.get("smoke_passed"):
        return 0
    return 0 if agent_gate["passed"] else 1


def _apply_v2_metrics(summary: dict[str, Any], results: list[dict[str, Any]], cases: list[Any]) -> None:
    """P1.6.5 correlation-verified metrics.

    Unlike the legacy summarize path, these metrics are computed for any sample
    size, use the manifest-based clarification denominator, use status-specific
    provenance semantics, and count trace matches by exact shadow_run_id."""
    executed = len(results)
    metrics = summary.setdefault("metrics", {})
    case_by_id = {case.case_id: case for case in cases}
    trace_mismatch = 0
    terminal_missing = 0
    unknown_writes = 0
    pi_business_writes = 0
    double_writes = 0
    other_case_writes = 0
    status_matches = 0
    provenance_ok = 0
    clar_applicable = 0
    clar_correct = 0
    expected_deadline = 0
    unexpected_deadline = 0
    safety_ok = 0
    for item in results:
        comparison = item.get("comparison") or {}
        pi = item.get("pi_compatible") or {}
        case = case_by_id.get(item.get("case_id"))
        if not item.get("trace_match"):
            trace_mismatch += 1
        if not item.get("shadow_terminal_received"):
            terminal_missing += 1
        side = item.get("side_effects") or {}
        double_writes += int(side.get("double_write_count") or 0)
        attribution_v2 = ((item.get("write_attribution_v2") or {}) if isinstance(item.get("write_attribution_v2"), dict) else {})
        unknown_writes += int(attribution_v2.get("unknown_owner_write_count") or item.get("unknown_owner_write_count") or 0)
        pi_business_writes += int(attribution_v2.get("pi_business_write_delta") or item.get("pi_business_write_delta") or 0)
        other_case_writes += int(attribution_v2.get("other_case_write_count") or item.get("other_case_write_count") or 0)
        if comparison.get("status_match"):
            status_matches += 1
        if comparison.get("provenance_complete"):
            provenance_ok += 1
        if comparison.get("safety_correctness"):
            safety_ok += 1
        classification = item.get("deadline_classification") or "none"
        if classification == "expected_timeout":
            expected_deadline += 1
        elif classification == "unexpected_timeout":
            unexpected_deadline += 1
        if case is not None and clarification_applicable(case.query_type, case.expected_status):
            clar_applicable += 1
            normalized_pi = normalize_status(pi.get("status"), pi.get("error_code"))
            answer = pi.get("structured_answer") or item.get("structured_answer") or {}
            ok, _reasons = clarification_correct(
                normalized_pi_status=normalized_pi,
                clarification_options=(answer.get("clarification_options") if isinstance(answer, dict) else None),
                pi_pdf_url=pi.get("pdf_url"),
                pi_tool_call_count=int(pi.get("tool_call_count") or 0),
            )
            if ok:
                clar_correct += 1
    def _rate(numerator: int) -> float | None:
        return round(numerator / executed, 4) if executed else None

    metrics.update({
        "status_match_rate": _rate(status_matches),
        "provenance_rate": _rate(provenance_ok),
        "status_specific_provenance_completeness": _rate(provenance_ok),
        "safety_correctness_rate": _rate(safety_ok),
        "clarification_applicable_samples": clar_applicable,
        "clarification_correct_samples": clar_correct,
        "clarification_correctness_rate": (round(clar_correct / clar_applicable, 4) if clar_applicable else 1.0),
        "shadow_terminal_trace_mismatch_count": trace_mismatch,
        "terminal_missing_count": terminal_missing,
        "unknown_owner_write_count": unknown_writes,
        "pi_business_write_delta": pi_business_writes,
        "other_case_write_count": other_case_writes,
        "double_write_count": double_writes,
        "side_effect_count": pi_business_writes + unknown_writes,
        "expected_deadline_exceeded_count": expected_deadline,
        "unexpected_deadline_exceeded_count": unexpected_deadline,
        "agent_deadline_exceeded_count": expected_deadline + unexpected_deadline,
        "raw_500_count": sum(1 for item in results if (item.get("legacy") or {}).get("http_status") == 500),
        "raw_503_count": sum(1 for item in results if (item.get("legacy") or {}).get("http_status") == 503),
    })


def _write_subset_artifacts(
    *,
    mode: str,
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    side_effects: dict[str, Any],
    env_report: dict[str, Any],
    planned: int,
) -> bool:
    metrics = summary.get("metrics") or {}
    executed = len(results)
    decisions = [((item.get("comparison") or {}).get("decision")) for item in results]
    review = sum(1 for item in decisions if item == "review")
    failed = sum(
        1
        for item in results
        if normalize_status((item.get("pi_compatible") or {}).get("status"), (item.get("pi_compatible") or {}).get("error_code")) in {"failed"}
        and (item.get("deadline_classification") or "none") == "none"
    )
    fabricated = sum(int((item.get("comparison") or {}).get("unsupported_url_count") or 0) for item in results)
    subset_passed = all([
        executed == planned,
        metrics.get("shadow_terminal_trace_mismatch_count") == 0,
        metrics.get("terminal_missing_count") == 0,
        metrics.get("pi_business_write_delta") == 0,
        metrics.get("double_write_count") == 0,
        metrics.get("unknown_owner_write_count") == 0,
        metrics.get("unexpected_deadline_exceeded_count") == 0,
        metrics.get("clarification_correctness_rate") == 1.0,
        metrics.get("status_specific_provenance_completeness") == 1.0,
        fabricated == 0,
        metrics.get("raw_500_count") == 0,
        metrics.get("raw_503_count") == 0,
    ])
    manifest = blocker_subset_manifest()
    payload = {
        "schema_version": f"pi_official_report_{mode}_results_v1",
        "phase": "6V-P1.6.5",
        "mode": mode,
        "is_formal_full30": False,
        "acceptance_run_id": summary.get("acceptance_run_id"),
        "generated_at": summary.get("generated_at"),
        "environment_type": env_report.get("environment_type"),
        "commit_sha": env_report.get("commit_sha"),
        "manifest_hash": manifest.get("manifest_hash"),
        "planned": planned,
        "executed": executed,
        "accepted": summary.get("accepted_samples"),
        "review": review,
        "failed": failed,
        "metrics": metrics,
        "subset_passed": subset_passed,
        "recommended_to_retry_full30": subset_passed,
        "recommended_for_next_authorization": False,
        "pi_executor_enabled": False,
        "authorized_agents": [],
        "decision": "do_not_enable_pi_compatible",
        "cases": results,
        "side_effects": side_effects,
    }
    prefix = "pi_official_report_blocker_subset" if mode == "blocker_subset" else "pi_official_report_stage2"
    (ARTIFACT_DIR / f"{prefix}_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    if mode == "blocker_subset":
        (ARTIFACT_DIR / "pi_official_report_blocker_subset_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (ARTIFACT_DIR / "pi_official_report_blocker_subset_summary.md").write_text(
            _subset_summary_markdown(payload), encoding="utf-8"
        )
    return subset_passed


def _subset_summary_markdown(payload: dict[str, Any]) -> str:
    metrics = payload.get("metrics") or {}
    lines = [
        "# official_report_pdf Pi Blocker Subset Summary (6V-P1.6.5)",
        "",
        f"- Mode: `{payload.get('mode')}` (not a formal Full30)",
        f"- Acceptance run: `{payload.get('acceptance_run_id')}`",
        f"- Commit SHA: `{payload.get('commit_sha')}`",
        f"- Manifest hash: `{payload.get('manifest_hash')}`",
        f"- Planned / executed / accepted / review / failed: `{payload.get('planned')}` / `{payload.get('executed')}` / `{payload.get('accepted')}` / `{payload.get('review')}` / `{payload.get('failed')}`",
        f"- Trace mismatch / terminal missing: `{metrics.get('shadow_terminal_trace_mismatch_count')}` / `{metrics.get('terminal_missing_count')}`",
        f"- Pi business writes / double writes / unknown writes / other-case writes: `{metrics.get('pi_business_write_delta')}` / `{metrics.get('double_write_count')}` / `{metrics.get('unknown_owner_write_count')}` / `{metrics.get('other_case_write_count')}`",
        f"- Status match: `{metrics.get('status_match_rate')}`; safety correctness: `{metrics.get('safety_correctness_rate')}`",
        f"- Clarification applicable/correct: `{metrics.get('clarification_applicable_samples')}` / `{metrics.get('clarification_correct_samples')}` (rate `{metrics.get('clarification_correctness_rate')}`)",
        f"- Status-specific provenance completeness: `{metrics.get('status_specific_provenance_completeness')}`",
        f"- Deadline expected/unexpected: `{metrics.get('expected_deadline_exceeded_count')}` / `{metrics.get('unexpected_deadline_exceeded_count')}`",
        f"- raw500/raw503: `{metrics.get('raw_500_count')}` / `{metrics.get('raw_503_count')}`",
        f"- Subset passed: `{payload.get('subset_passed')}`",
        f"- Recommended to retry Full30: `{payload.get('recommended_to_retry_full30')}`",
        "- Formal Pi path remains disabled: `pi_executor_enabled=false`, `authorized_agents=[]`, decision `do_not_enable_pi_compatible`.",
        "",
        "| Case | Type | Decision | Legacy | Pi(norm) | TraceMatch | PiWrites | DoubleWrites | Prov |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for item in payload.get("cases") or []:
        comparison = item.get("comparison") or {}
        side = item.get("side_effects") or {}
        lines.append(
            f"| {item.get('case_id')} | {item.get('query_type')} | {comparison.get('decision')} "
            f"| {comparison.get('normalized_legacy_status')} | {comparison.get('normalized_pi_status')} "
            f"| {item.get('trace_match')} | {comparison.get('side_effect_count')} "
            f"| {side.get('double_write_count')} | {comparison.get('provenance_complete')} |"
        )
    lines.append("")
    return "\n".join(lines)


async def build_environment_report(args: argparse.Namespace) -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    diagnostics_path = _diagnostics_path()
    git_info = _git_info()
    environment_type = args.environment_type or _infer_environment_type(args)
    checks = {
        "environment_ready": False,
        "auth_ready": False,
        "db_ready": False,
        "chat_ready": False,
        "sse_ready": False,
        "report_tool_ready": False,
        "shadow_enabled": pi_compatible_shadow_runner.enabled(),
        "shadow_ready": pi_compatible_shadow_runner.enabled(),
        "acceptance_identity_ready": bool(args.access_token and args.user_id) or bool(args.allow_local_fixture_user),
        "backend_health_passed": False,
        "resolver_ready": False,
        "diagnostics_ready": _path_writable(diagnostics_path),
        "shadow_callback_ready": _path_writable(diagnostics_path),
        "artifact_output_writable": _path_writable(ARTIFACT_DIR / ".write_test"),
        "chat_runtime_mode_legacy": settings.chat_runtime_mode == "legacy",
        "no_production_mode": _no_production_mode(environment_type),
        "branch_ready": git_info.get("branch") == "release/demo-staging",
        "commit_sha_present": bool(git_info.get("commit_sha")),
    }
    blockers: list[str] = []
    if not checks["branch_ready"]:
        blockers.append("Current branch must be release/demo-staging for live acceptance.")
    if not checks["no_production_mode"]:
        blockers.append("Production mode is forbidden for Pi shadow acceptance.")
    if environment_type not in {"staging", "local_live"}:
        blockers.append("local_fixture is allowed only for runner self-test and cannot count as live acceptance.")
    if args.allow_local_fixture_user:
        blockers.append("Local fixture identity cannot count as live shadow acceptance.")
    if not checks["shadow_enabled"]:
        blockers.append("Pi shadow env is not enabled with the explicit P1.3 values.")
    if not checks["chat_runtime_mode_legacy"]:
        blockers.append("CHAT_RUNTIME_MODE must remain legacy during shadow acceptance.")
    if not diagnostics_path:
        blockers.append("PI_AGENT_SHADOW_DIAGNOSTICS_PATH is required for HTTP shadow result polling.")
    if args.execute and not (args.base_url or "").strip():
        blockers.append("PI_SHADOW_ACCEPTANCE_BASE_URL / --base-url is required for HTTP Chat acceptance.")
    async with AsyncSessionLocal() as db:
        try:
            await db.execute(select(User.id).limit(1))
            checks["db_ready"] = True
            checks["resolver_ready"] = True
            checks["report_tool_ready"] = True
        except Exception:
            blockers.append("Database readiness check failed.")
    if args.base_url:
        checks["backend_health_passed"] = await _http_health(args.base_url)
        if not checks["backend_health_passed"]:
            blockers.append("Backend health check failed or was unreachable.")
        checks["auth_ready"] = await _http_auth_ready(args.base_url, args.access_token)
        if not checks["auth_ready"] and args.execute:
            blockers.append("Auth readiness check failed for the acceptance identity.")
        checks["chat_ready"] = await _http_chat_ready(args.base_url, args.access_token)
        if not checks["chat_ready"] and args.execute:
            blockers.append("Chat API readiness check failed.")
        checks["sse_ready"] = checks["chat_ready"]
    else:
        checks["backend_health_passed"] = not args.execute
    if not args.base_url:
        checks["auth_ready"] = bool(args.access_token and args.user_id) or bool(args.allow_local_fixture_user)
    checks["environment_ready"] = all([
        checks["db_ready"],
        checks["report_tool_ready"],
        checks["shadow_enabled"],
        checks["acceptance_identity_ready"],
        checks["diagnostics_ready"],
        checks["artifact_output_writable"],
        checks["chat_runtime_mode_legacy"],
        checks["backend_health_passed"],
        checks["auth_ready"],
        checks["chat_ready"] or not args.execute,
        checks["sse_ready"] or not args.execute,
        checks["no_production_mode"],
        checks["branch_ready"],
        environment_type in {"staging", "local_live"},
        not args.allow_local_fixture_user,
    ])
    return {
        "schema_version": "pi_shadow_acceptance_environment_v1",
        **checks,
        "environment_type": environment_type,
        "commit_sha": git_info.get("commit_sha"),
        "branch": git_info.get("branch"),
        "backend_base_url": "redacted" if args.base_url else "",
        "frontend_base_url": "redacted" if args.frontend_base_url else "",
        "database_mode": settings.database_connection_mode,
        "auth_mode": "bearer_service_account" if args.access_token else ("local_fixture" if args.allow_local_fixture_user else "missing"),
        "provider_mode": getattr(settings, "data_mode", ""),
        "limitations": blockers[:],
        "config": {
            "agent_executor_mode": settings.agent_executor_mode,
            "pi_agent_shadow_enabled": bool(settings.pi_agent_shadow_enabled),
            "pi_agent_allowed_agents": settings.pi_agent_allowed_agents,
            "chat_runtime_mode": settings.chat_runtime_mode,
            "diagnostics_path_present": bool(diagnostics_path),
            "base_url_present": bool(args.base_url),
            "access_token_present": bool(args.access_token),
            "user_id_present": bool(args.user_id),
        },
        "blockers": blockers,
    }


async def resolve_acceptance_identity(args: argparse.Namespace, env_report: dict[str, Any]) -> dict[str, Any]:
    if args.access_token and args.user_id:
        try:
            uuid.UUID(args.user_id)
        except ValueError:
            return {"ready": False, "method": "service_account_env", "blockers": ["PI_SHADOW_ACCEPTANCE_USER_ID is not a UUID."]}
        return {"ready": True, "method": "service_account_env", "user_id": args.user_id, "access_token": args.access_token, "created_user": False}
    if not args.allow_local_fixture_user:
        return {"ready": False, "method": "none", "blockers": ["No acceptance service account token/user id and local fixture creation was not explicitly allowed."]}
    if str(getattr(settings, "app_env", "local")).lower() not in {"local", "test", "staging", "development"}:
        return {"ready": False, "method": "local_fixture_user", "blockers": ["Local fixture user creation is forbidden outside local/test/staging environments."]}
    async with AsyncSessionLocal() as db:
        username = "pi_shadow_acceptance"
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        created = False
        if user is None:
            user = User(
                username=username,
                email="pi_shadow_acceptance@example.invalid",
                hashed_password=hash_password(secrets.token_urlsafe(24)),
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            created = True
        return {
            "ready": True,
            "method": "local_fixture_user",
            "user_id": str(user.id),
            "access_token": create_access_token(str(user.id)),
            "created_user": created,
        }


async def execute_http_case(
    case: Any,
    *,
    args: argparse.Namespace,
    identity: dict[str, Any],
    acceptance_run_id: str = "",
    acceptance_session_ids: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    import httpx

    acceptance_session_ids = acceptance_session_ids if acceptance_session_ids is not None else set()
    headers = {"Authorization": f"Bearer {identity['access_token']}"}
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), headers=headers, timeout=60.0, trust_env=False) as client:
        session_id = await _create_http_session(client, case.case_id)
        acceptance_session_ids.add(session_id)
        setup_legacy: dict[str, Any] | None = None
        setup_pi_result: dict[str, Any] | None = None
        setup_correlation: dict[str, Any] | None = None
        if case.setup_query:
            setup_correlation = _build_correlation(
                acceptance_run_id=acceptance_run_id,
                case=case,
                session_id=session_id,
                turn_index=1,
            )
            setup_legacy, setup_pi_result = await _send_http_chat(
                client,
                session_id,
                case.setup_query,
                args=args,
                identity=identity,
                wait_for_shadow=True,
                correlation=setup_correlation,
            )
            if not setup_legacy.get("sse_terminal_received", True):
                raise RuntimeError(f"Setup SSE terminal missing for {case.case_id}")
            if not setup_pi_result.get("shadow_terminal_received", False):
                raise RuntimeError(f"Setup shadow terminal missing for {case.case_id}")
        correlation = _build_correlation(
            acceptance_run_id=acceptance_run_id,
            case=case,
            session_id=session_id,
            turn_index=2 if case.setup_query else 1,
        )
        async with AsyncSessionLocal() as db:
            before = await capture_side_effect_snapshot(db, session_id=session_id)
            window_start = await _db_now(db)
        resolver_before = get_security_index_metrics()
        started = time.perf_counter()
        legacy, pi_result = await _send_http_chat(
            client,
            session_id,
            case.query,
            args=args,
            identity=identity,
            wait_for_shadow=True,
            correlation=correlation,
        )
        legacy["latency_ms"] = int((time.perf_counter() - started) * 1000)
        derived_status = _legacy_status_from_answer(legacy.get("answer") or "")
        if derived_status != "success" and legacy.get("http_status", 200) < 500:
            legacy["status"] = derived_status
        legacy.setdefault("symbol", case.expected_symbol or "")
        legacy.setdefault("report_year", case.expected_report_year)
        legacy.setdefault("report_type", case.expected_report_type)
        correlation["legacy_run_id"] = str(legacy.get("assistant_message_id") or legacy.get("message_id") or "")
        async with AsyncSessionLocal() as db:
            after = await capture_side_effect_snapshot(db, session_id=session_id)
            new_messages = await list_new_chat_messages(db, since=window_start)
            new_sessions = await list_new_chat_sessions(db, since=window_start)
        resolver_after = get_security_index_metrics()
        expected_context_delta = 2
        side_effect_count = compute_pi_side_effect_count(
            before,
            after,
            expected_legacy_chat_message_delta=2,
            expected_legacy_context_version_delta=expected_context_delta,
        )
        target_context_delta = max(0, after.target_session_context_version - before.target_session_context_version)
        context_extra_updates = max(0, target_context_delta - expected_context_delta)
        attribution_v2 = attribute_turn_writes(
            case_id=case.case_id,
            correlation=correlation,
            target_session_id=session_id,
            new_messages=new_messages,
            new_sessions=[row for row in new_sessions if row.session_id != session_id],
            acceptance_session_ids=set(acceptance_session_ids),
        )
        attribution = build_write_attribution(
            case_id=case.case_id,
            before=before,
            after=after,
            legacy_run_id=correlation.get("legacy_run_id"),
            pi_shadow_run_id=pi_result.get("run_id"),
            trace_id=pi_result.get("trace_id"),
            expected_legacy_chat_message_delta=2,
            expected_legacy_context_version_delta=expected_context_delta,
        )
        attribution["v2"] = attribution_v2.to_dict()
        pi_side_effect_count = attribution_v2.pi_business_write_delta + attribution_v2.unknown_owner_write_count
        assistant_double_writes = attribution_v2.assistant_double_write_count
        trace_match = bool(
            pi_result.get("shadow_terminal_received")
            and pi_result.get("run_id")
            and pi_result.get("run_id") == correlation.get("shadow_run_id")
        )
        side_effect = {
            "case_id": case.case_id,
            "correlation": {key: value for key, value in correlation.items() if key != "session_id"},
            "before": before.to_dict(),
            "after": after.to_dict(),
            "legacy_expected_writes": {"chat_messages": 2, "chat_sessions": 0, "context_version_delta": expected_context_delta},
            "expected_legacy_chat_message_delta": 2,
            "expected_legacy_context_version_delta": expected_context_delta,
            "table_count_side_effect_estimate": side_effect_count,
            "pi_shadow_business_write_delta": attribution_v2.pi_business_write_delta,
            "pi_side_effect_count": pi_side_effect_count,
            "unknown_owner_write_count": attribution_v2.unknown_owner_write_count,
            "other_case_write_count": attribution_v2.other_case_write_count,
            "context_extra_updates": context_extra_updates,
            "context_mutation_count": context_extra_updates,
            "assistant_double_writes": assistant_double_writes,
            "double_write_count": assistant_double_writes,
            "write_attribution": attribution,
        }
        result = build_live_shadow_case_result(
            runner=pi_compatible_shadow_runner,
            case=case,
            legacy=legacy,
            pi_result=pi_result,
            side_effect_count=pi_side_effect_count,
        )
        result["correlation"] = {key: value for key, value in correlation.items() if key != "session_id"}
        result["structured_answer"] = pi_result.get("structured_answer") or {}
        result["write_attribution_v2"] = attribution_v2.to_dict()
        result["trace_match"] = trace_match
        result["shadow_terminal_received"] = bool(pi_result.get("shadow_terminal_received"))
        result["deadline_classification"] = classify_deadline(
            normalized_pi_status=normalize_status(
                (result.get("pi_compatible") or {}).get("status"),
                (result.get("pi_compatible") or {}).get("error_code"),
            ),
            expected_status=case.expected_status,
        )
        result["side_effects"] = {
            "context_mutation_count": side_effect["context_mutation_count"],
            "double_write_count": side_effect["double_write_count"],
        }
        snapshot_hash = pi_result.get("input_snapshot_hash")
        if snapshot_hash:
            result["legacy"]["input_snapshot_hash"] = snapshot_hash
            result["pi_compatible"]["input_snapshot_hash"] = snapshot_hash
            result["comparison"]["input_snapshot_hash_match"] = True
        if setup_legacy is not None or setup_pi_result is not None:
            result["setup_turn"] = {
                "legacy": _compact_turn_status(setup_legacy or {}),
                "pi_compatible": _compact_turn_status(setup_pi_result or {}),
            }
        resolver_full_scan_delta = max(0, int(resolver_after.get("security_index_db_full_scan") or 0) - int(resolver_before.get("security_index_db_full_scan") or 0))
        resolver_rebuild_delta = max(0, int(resolver_after.get("security_index_rebuild") or 0) - int(resolver_before.get("security_index_rebuild") or 0))
        tool_breakdown = ((result.get("pi_compatible") or {}).get("metrics") or {}).get("tool_latency_breakdown") or {}
        entity_snapshot_reused = (
            resolver_full_scan_delta == 0
            and resolver_rebuild_delta == 0
            and int(tool_breakdown.get("resolver_ms") or 0) == 0
        )
        resolver_case = {
            "case_id": case.case_id,
            "before": resolver_before,
            "after": resolver_after,
            "security_index_cache_hit": (
                int(resolver_after.get("security_index_cache_hit") or 0) > int(resolver_before.get("security_index_cache_hit") or 0)
                or entity_snapshot_reused
            ),
            "entity_snapshot_reused": entity_snapshot_reused,
            "security_index_full_scan_count": resolver_full_scan_delta,
            "security_index_rebuild_count": resolver_rebuild_delta,
            "security_index_snapshot_id": resolver_after.get("security_index_snapshot_id"),
        }
        return result, side_effect, resolver_case


async def _create_http_session(client: Any, case_id: str) -> str:
    response = await client.post("/api/v1/chat/sessions", json={"title": f"pi-shadow-{case_id}"})
    response.raise_for_status()
    return str(response.json()["session_id"])


def _build_correlation(
    *,
    acceptance_run_id: str,
    case: Any,
    session_id: str,
    turn_index: int,
    case_attempt: int = 1,
) -> dict[str, Any]:
    turn_id = f"{case.case_id}.a{case_attempt}.t{turn_index}"
    query = case.setup_query if (turn_index == 1 and case.setup_query) else case.query
    return {
        "acceptance_run_id": acceptance_run_id,
        "case_id": case.case_id,
        "case_attempt": case_attempt,
        "session_id": session_id,
        "turn_id": turn_id,
        "request_trace_id": new_id("trace"),
        "legacy_run_id": "",
        "shadow_run_id": new_id("run"),
        "input_snapshot_hash": stable_payload_hash({"query_hash": query_hash(query), "conversation_id": session_id}),
    }


async def _db_now(db: Any) -> Any:
    from sqlalchemy import func as sa_func  # noqa: PLC0415

    try:
        return (await db.execute(select(sa_func.now()))).scalar_one()
    except Exception:
        from datetime import datetime, timezone  # noqa: PLC0415

        return datetime.now(timezone.utc)


def _correlation_header(correlation: dict[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in correlation.items() if key != "legacy_run_id"}
    return {SHADOW_CORRELATION_HEADER: json.dumps(payload, ensure_ascii=False)}


async def _send_http_chat(
    client: Any,
    session_id: str,
    content: str,
    *,
    args: argparse.Namespace,
    identity: dict[str, Any],
    wait_for_shadow: bool,
    correlation: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    headers = _correlation_header(correlation) if correlation else {}
    if args.stream:
        legacy = await _send_http_chat_stream(client, session_id, content, extra_headers=headers)
    else:
        response = await client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            json={"content": content, "output_language": "zh-CN"},
            headers=headers,
        )
        legacy = {
            "http_status": response.status_code,
            "status": "failed" if response.status_code >= 500 else "success",
            "error_code": None if response.status_code < 400 else f"HTTP_{response.status_code}",
        }
        response.raise_for_status()
        payload = response.json()
        legacy.update({
            "answer": payload.get("answer", ""),
            "message_id": payload.get("message_id"),
            "assistant_message_id": payload.get("assistant_message_id"),
        })
    if not wait_for_shadow:
        return legacy, {}
    timeout_seconds = max(2.0, settings.pi_agent_default_deadline_ms / 1000 + 3.0)
    if correlation and correlation.get("shadow_run_id"):
        pi_result = await _poll_shadow_run(
            shadow_run_id=str(correlation["shadow_run_id"]),
            timeout_seconds=timeout_seconds,
        )
    else:
        pi_result = await _poll_shadow_diagnostic(
            conversation_id=session_id,
            raw_query=content,
            user_id=identity.get("user_id", ""),
            timeout_seconds=timeout_seconds,
        )
    return legacy, pi_result


async def _poll_shadow_run(*, shadow_run_id: str, timeout_seconds: float) -> dict[str, Any]:
    """Poll the per-run diagnostics record addressed exactly by shadow_run_id.

    Recency / conversation / query-hash matching is intentionally not used:
    a record only counts when its run_id equals the pre-generated shadow_run_id
    for this exact turn.
    """
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        record = pi_shadow_diagnostics_sink.read_run(shadow_run_id)
        if record is not None and record.get("terminal") is True and record.get("run_id") == shadow_run_id:
            return _diagnostic_to_pi_result(record)
        await asyncio.sleep(DIAGNOSTICS_POLL_INTERVAL_SECONDS)
    return {
        "status": "failed",
        "terminal": False,
        "shadow_terminal_received": False,
        "error": {"code": "PI_SHADOW_TIMEOUT"},
        "metrics": {"latency_ms": 0, "model_calls": 0},
        "findings": [],
    }


def _stage2_cases() -> list[Any]:
    by_id = {case.case_id: case for case in planned_official_report_shadow_cases()}
    return [by_id["A01"], by_id["C01"], by_id["E01"]]


async def _send_http_chat_stream(client: Any, session_id: str, content: str, *, extra_headers: dict[str, str] | None = None) -> dict[str, Any]:
    events: list[str] = []
    answer_parts: list[str] = []
    terminal_payloads: list[dict[str, Any]] = []
    async with client.stream(
        "POST",
        f"/api/v1/chat/sessions/{session_id}/messages/stream",
        json={"content": content, "output_language": "zh-CN"},
        headers=extra_headers or {},
    ) as response:
        legacy = {
            "http_response_started": True,
            "http_status": response.status_code,
            "status": "failed" if response.status_code >= 500 else "success",
            "error_code": None if response.status_code < 400 else f"HTTP_{response.status_code}",
            "sse_terminal_received": False,
            "sse_terminal_event_count": 0,
            "legacy_terminal_status": None,
            "legacy_message_persisted": False,
        }
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            try:
                payload = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            event_type = payload.get("event_type")
            if event_type:
                events.append(event_type)
            event_payload = payload.get("payload") or {}
            if event_type == "agent_completed":
                terminal_payloads.append(event_payload)
            if event_type == "message_persisted":
                legacy["legacy_message_persisted"] = True
            if event_type == "answer_delta":
                answer_parts.append(str(event_payload.get("delta") or ""))
        terminal_count = len(terminal_payloads)
        legacy["sse_terminal_event_count"] = terminal_count
        legacy["sse_terminal_received"] = terminal_count == 1
        if terminal_count != 1:
            raise RuntimeError(f"SSE stream must emit exactly one agent_completed; observed {terminal_count}")
        terminal_payload = terminal_payloads[-1]
        legacy["legacy_terminal_status"] = terminal_payload.get("status") or "completed"
        legacy["answer"] = "".join(answer_parts)
        derived_status = _legacy_status_from_answer(legacy["answer"])
        if derived_status != "success" and legacy["http_status"] < 500:
            legacy["status"] = derived_status
        if legacy["legacy_terminal_status"] == "failed":
            legacy["status"] = "failed"
            legacy["error_code"] = terminal_payload.get("error_code") or legacy.get("error_code")
        legacy["sse_completed"] = True
        return legacy


async def _poll_shadow_diagnostic(*, conversation_id: str, raw_query: str, user_id: str, timeout_seconds: float) -> dict[str, Any]:
    target_hash = query_hash(raw_query)
    target_user = user_hash(user_id)
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        for record in reversed(_read_diagnostics()[-200:]):
            if record.get("conversation_id") == conversation_id and record.get("query_hash") == target_hash and record.get("user_hash") == target_user:
                if record.get("terminal") is True:
                    return _diagnostic_to_pi_result(record)
        await asyncio.sleep(DIAGNOSTICS_POLL_INTERVAL_SECONDS)
    return {
        "status": "failed",
        "terminal": False,
        "shadow_terminal_received": False,
        "error": {"code": "PI_SHADOW_TIMEOUT"},
        "metrics": {"latency_ms": 0, "model_calls": 0},
        "findings": [],
    }


def _diagnostic_to_pi_result(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace_id": record.get("trace_id"),
        "run_id": record.get("run_id"),
        "status": record.get("status"),
        "terminal": bool(record.get("terminal")),
        "shadow_terminal_received": bool(record.get("terminal")),
        "completed_at": record.get("completed_at"),
        "agent_id": record.get("agent_id"),
        "turn_count": record.get("turn_count", 0),
        "tool_call_count": record.get("tool_call_count", 0),
        "metrics": record.get("metrics") or {},
        "findings": record.get("findings") or [],
        "structured_answer": record.get("structured_answer_compact") or {},
        "correlation": record.get("correlation") or {},
        "evidence_ids": ["compact_evidence_present"] if int(record.get("evidence_ids_count") or 0) > 0 else [],
        "error": {"code": record.get("error_code")} if record.get("error_code") else None,
        "events": record.get("events") or [],
        "input_snapshot_hash": record.get("input_snapshot_hash"),
    }


def _read_diagnostics() -> list[dict[str, Any]]:
    path = _diagnostics_path()
    if path is None or not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _diagnostics_path() -> Path | None:
    raw = str(getattr(settings, "pi_agent_shadow_diagnostics_path", "") or "").strip()
    return Path(raw).expanduser() if raw else None


def _path_writable(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        target = path if path.suffix or path.name.startswith(".") else path / ".write_test"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8"):
            pass
        if target.name == ".write_test":
            target.unlink(missing_ok=True)
        return True
    except OSError:
        return False


async def _http_health(base_url: str) -> bool:
    try:
        import httpx

        async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=10.0, trust_env=False) as client:
            response = await client.get("/api/v1/health")
            return response.status_code == 200 and response.json().get("db_status") == "ok"
    except Exception:
        return False


async def _http_auth_ready(base_url: str, access_token: str) -> bool:
    if not access_token:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(base_url=base_url.rstrip("/"), headers={"Authorization": f"Bearer {access_token}"}, timeout=10.0, trust_env=False) as client:
            response = await client.get("/api/v1/auth/me")
            return response.status_code == 200
    except Exception:
        return False


async def _http_chat_ready(base_url: str, access_token: str) -> bool:
    if not access_token:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(base_url=base_url.rstrip("/"), headers={"Authorization": f"Bearer {access_token}"}, timeout=10.0, trust_env=False) as client:
            response = await client.get("/api/v1/chat/sessions", params={"limit": 1, "offset": 0})
            return response.status_code == 200
    except Exception:
        return False


def _infer_environment_type(args: argparse.Namespace) -> str:
    if args.allow_local_fixture_user:
        return "local_fixture"
    base = (args.base_url or "").lower()
    if "localhost" in base or "127.0.0.1" in base or "::1" in base:
        return "local_live"
    if base:
        return "staging"
    return "local_fixture"


def _smoke_cases() -> list[Any]:
    from app.agent_runtime.shadow_acceptance import OfficialReportShadowCase

    return [
        OfficialReportShadowCase("A01", "smoke_multi_turn_current_report", "这份报告的官方 PDF 在哪里？", setup_query="贵州茅台最新财报表现如何？", expected_symbol="600519", expected_report_type="annual"),
        OfficialReportShadowCase("A02", "smoke_explicit_stock_code", "600519官方年报链接", expected_symbol="600519", expected_report_type="annual"),
        OfficialReportShadowCase("A03", "smoke_ambiguity", "平安的年报PDF在哪里？", expected_status="clarification_required", expected_report_type="annual"),
    ]


def _compact_turn_status(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "http_status": payload.get("http_status"),
        "sse_terminal_received": payload.get("sse_terminal_received"),
        "sse_terminal_event_count": payload.get("sse_terminal_event_count"),
        "legacy_terminal_status": payload.get("legacy_terminal_status"),
        "legacy_message_persisted": payload.get("legacy_message_persisted"),
        "shadow_terminal_received": payload.get("shadow_terminal_received"),
        "shadow_terminal_status": payload.get("status"),
        "error_code": (payload.get("error") or {}).get("code") or payload.get("error_code"),
        "run_id": payload.get("run_id"),
        "trace_id": payload.get("trace_id"),
    }


def _legacy_status_from_answer(answer: str) -> str:
    text = str(answer or "")
    if (
        "请选择" in text
        or "需要进一步确认" in text
        or "没有识别到明确" in text
        or "请明确" in text
        or ("多个" in text and "平安" in text)
    ):
        return "clarification_required"
    if "暂未找到" in text or "不可用" in text or "没有找到" in text:
        return "unavailable"
    return "success"


def _no_production_mode(environment_type: str) -> bool:
    app_env = str(getattr(settings, "app_env", "") or "").lower()
    return environment_type in {"staging", "local_live", "local_fixture"} and app_env not in {"prod", "production"}


def _git_info() -> dict[str, str]:
    return {
        "branch": _git_value(["git", "branch", "--show-current"]),
        "commit_sha": _git_value(["git", "rev-parse", "HEAD"]),
    }


def _git_value(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def _browser_markdown(*, executed: bool, passed: bool, notes: str) -> str:
    return "\n".join([
        "# Pi Shadow Browser Acceptance",
        "",
        f"- Executed: `{executed}`",
        f"- Passed: `{passed}`",
        f"- Notes: `{notes}`",
        "",
        "Required manual conversations:",
        "- 贵州茅台最新财报表现如何？ -> 这份报告的官方 PDF 在哪里？",
        "- 五粮液2025年年度报告PDF在哪里？",
        "- 平安的年报PDF在哪里？",
    ])


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
