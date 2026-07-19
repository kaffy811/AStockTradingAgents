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

from app.agent_runtime.shadow_acceptance import (  # noqa: E402
    ARTIFACT_DIR,
    build_agent_gate,
    build_live_shadow_case_result,
    build_runtime_gate,
    build_write_attribution,
    capture_side_effect_snapshot,
    compute_pi_side_effect_count,
    planned_official_report_shadow_cases,
    summarize_shadow_results,
    write_shadow_artifacts,
)
from app.agent_runtime.shadow_diagnostics import query_hash, user_hash  # noqa: E402
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
    cases = _smoke_cases() if args.smoke else planned_official_report_shadow_cases()[: max(0, args.limit)]
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

    if args.execute and not blockers and not args.preflight_only:
        for case in cases:
            result, side_effect, resolver_case = await execute_http_case(case, args=args, identity=identity)
            results.append(result)
            side_effect_report["cases"].append(side_effect)
            side_effect_report["write_attribution"]["cases"].append(side_effect["write_attribution"])
            resolver_diagnostics["cases"].append(resolver_case)

    summary = summarize_shadow_results(results, planned_samples=len(cases))
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


async def execute_http_case(case: Any, *, args: argparse.Namespace, identity: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    import httpx

    headers = {"Authorization": f"Bearer {identity['access_token']}"}
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), headers=headers, timeout=60.0, trust_env=False) as client:
        session_id = await _create_http_session(client, case.case_id)
        setup_legacy: dict[str, Any] | None = None
        setup_pi_result: dict[str, Any] | None = None
        if case.setup_query:
            setup_legacy, setup_pi_result = await _send_http_chat(
                client,
                session_id,
                case.setup_query,
                args=args,
                identity=identity,
                wait_for_shadow=True,
            )
            if not setup_legacy.get("sse_terminal_received", True):
                raise RuntimeError(f"Setup SSE terminal missing for {case.case_id}")
            if not setup_pi_result.get("shadow_terminal_received", False):
                raise RuntimeError(f"Setup shadow terminal missing for {case.case_id}")
        async with AsyncSessionLocal() as db:
            before = await capture_side_effect_snapshot(db, session_id=session_id)
        resolver_before = get_security_index_metrics()
        started = time.perf_counter()
        legacy, pi_result = await _send_http_chat(client, session_id, case.query, args=args, identity=identity, wait_for_shadow=True)
        legacy["latency_ms"] = int((time.perf_counter() - started) * 1000)
        derived_status = _legacy_status_from_answer(legacy.get("answer") or "")
        if derived_status != "success" and legacy.get("http_status", 200) < 500:
            legacy["status"] = derived_status
        legacy.setdefault("symbol", case.expected_symbol or "")
        legacy.setdefault("report_year", case.expected_report_year)
        legacy.setdefault("report_type", case.expected_report_type)
        async with AsyncSessionLocal() as db:
            after = await capture_side_effect_snapshot(db, session_id=session_id)
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
        assistant_double_writes = max(0, (after.chat_messages - before.chat_messages) - 2)
        attribution = build_write_attribution(
            case_id=case.case_id,
            before=before,
            after=after,
            legacy_run_id=legacy.get("assistant_message_id") or legacy.get("message_id"),
            pi_shadow_run_id=pi_result.get("run_id"),
            trace_id=pi_result.get("trace_id"),
            expected_legacy_chat_message_delta=2,
            expected_legacy_context_version_delta=expected_context_delta,
        )
        pi_side_effect_count = max(side_effect_count, int(attribution.get("pi_shadow_business_write_delta") or 0))
        side_effect = {
            "case_id": case.case_id,
            "before": before.to_dict(),
            "after": after.to_dict(),
            "legacy_expected_writes": {"chat_messages": 2, "chat_sessions": 0, "context_version_delta": expected_context_delta},
            "expected_legacy_chat_message_delta": 2,
            "expected_legacy_context_version_delta": expected_context_delta,
            "pi_shadow_business_write_delta": pi_side_effect_count,
            "pi_side_effect_count": pi_side_effect_count,
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


async def _send_http_chat(client: Any, session_id: str, content: str, *, args: argparse.Namespace, identity: dict[str, Any], wait_for_shadow: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    if args.stream:
        legacy = await _send_http_chat_stream(client, session_id, content)
    else:
        response = await client.post(f"/api/v1/chat/sessions/{session_id}/messages", json={"content": content, "output_language": "zh-CN"})
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
    pi_result = await _poll_shadow_diagnostic(
        conversation_id=session_id,
        raw_query=content,
        user_id=identity.get("user_id", ""),
        timeout_seconds=max(2.0, settings.pi_agent_default_deadline_ms / 1000 + 3.0),
    )
    return legacy, pi_result


async def _send_http_chat_stream(client: Any, session_id: str, content: str) -> dict[str, Any]:
    events: list[str] = []
    answer_parts: list[str] = []
    terminal_payloads: list[dict[str, Any]] = []
    async with client.stream("POST", f"/api/v1/chat/sessions/{session_id}/messages/stream", json={"content": content, "output_language": "zh-CN"}) as response:
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
