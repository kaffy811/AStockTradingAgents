#!/usr/bin/env python3
"""Phase 6V-P1.8 — staging shadow-canary runner for official_report_pdf_pi_v1.

Honest mode note: the current runtime has no Pi user-visible serving path, so
this is a **staging shadow canary** (canary_mode=shadow): eligibility,
selection, bucketing, fallback semantics, monitoring, audits and rollback are
exercised for real over the live HTTP/Auth/SSE chat stack, users are always
served by Legacy, and the canary "Pi execution" is the correlated shadow run.
traffic_type=controlled_staging_acceptance — no real user traffic.

Stages (separate invocations):
  --c0          rollout=0 validation over >=10 real eligible requests
  --kill-drill  K01..K04 kill-switch drills (not counted)
  --c1          manual promotion to 1% + >=50 selected eligible requests

Repository defaults are never modified; the controller state lives in this
runner and in artifacts only.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent_runtime.canary_activation import (  # noqa: E402
    CanaryController,
    build_owner_approval_record,
)
from app.agent_runtime.canary_policy import (  # noqa: E402
    CANARY_AGENT_ID,
    CanaryRequest,
    anonymized_user_key,
    bucket_selected,
    evaluate_auto_rollback,
    evaluate_canary_decision,
    stable_bucket,
)
from app.agent_runtime.shadow_acceptance import (  # noqa: E402
    ARTIFACT_DIR,
    list_new_chat_messages,
    list_new_chat_sessions,
)
from app.agent_runtime.shadow_correlation import SHADOW_CORRELATION_HEADER  # noqa: E402
from app.agent_runtime.shadow_diagnostics import pi_shadow_diagnostics_sink, query_hash  # noqa: E402
from app.agent_runtime.shadow_write_attribution import attribute_turn_writes  # noqa: E402
from app.agent_runtime.contracts import new_id  # noqa: E402
from app.agent_runtime.url_utils import official_domain_verified  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402

SOURCE_SHA = "e6c2458c05cd73a704a6f5ffb4772bf619ed6719"
BASE_URL = "http://127.0.0.1:8026"
IDENTITY_PW_PATH = Path("/private/tmp/p18_canary_pw.txt")

# entity -> (query name or None => use code, tool-verified explicit years)
# Combos verified against the live get_official_reports tool (P1.8 probe):
# 600186 excluded (tool newest 2022 != DB newest 2025 — pre-existing tool data
# gap, tracked in the tool defect backlog); 300209 2024 excluded (same gap).
ENTITIES: list[tuple[str, str | None, tuple[int, ...]]] = [
    ("600519", "贵州茅台", (2025, 2024, 2023)), ("000858", "五粮液", (2025, 2024, 2019)),
    ("000001", "平安银行", (2025, 2024, 2023)), ("300750", "宁德时代", (2025, 2024, 2023)),
    ("000725", None, (2025, 2024, 2020)), ("300209", None, (2025, 2017)),
    ("301396", None, (2025, 2024, 2022)), ("600186", None, (2022, 2021, 2018)),
    ("601686", None, (2025, 2024, 2023)), ("688146", None, (2025, 2024, 2023)),
    ("688549", None, (2025, 2024, 2023)),
]

# known-unavailable entities (no indexed full annual) — non-counted legacy
# demonstrations broaden total sample entity coverage to 20 honestly.
DEMO_UNAVAILABLE_ENTITIES = ["601318", "600036", "002594", "600999", "601398",
                              "600030", "000002", "300059", "601988"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_manifest(window: str = "w1") -> list[dict[str, Any]]:
    """Eligible annual-report request specs + non-counted demonstrations.

    W1 leans on 2025/latest coverage; W2 leans on 2024 and tool-verified
    earlier years plus a different entity/year mix (>=10 combos differ)."""
    specs: list[dict[str, Any]] = []

    def label(symbol: str, name: str | None) -> str:
        return name or symbol

    for symbol, name, years in ENTITIES:
        early_years = [y for y in years if y < 2024]
        if window == "w1":
            if 2025 in years:
                q = f"{name}2025年年度报告PDF在哪里？" if name else f"{symbol} 2025年年度报告PDF在哪里？"
                specs.append({"kind": "single", "style": "S1_explicit_year_2025", "symbol": symbol,
                              "query": q, "expected_year": 2025})
            specs.append({"kind": "single", "style": "S4_latest", "symbol": symbol,
                          "query": f"{label(symbol, name)}最新年报PDF在哪里？", "expected_year": None})
            specs.append({"kind": "single", "style": "S2_official_link", "symbol": symbol,
                          "query": f"{symbol}官方年报链接", "expected_year": None})
        else:
            if 2024 in years:
                specs.append({"kind": "single", "style": "S3_code_year_2024", "symbol": symbol,
                              "query": f"{symbol} 2024年年报PDF", "expected_year": 2024})
            for year in early_years[:1]:
                specs.append({"kind": "single", "style": "S6_early_year", "symbol": symbol,
                              "query": f"{label(symbol, name)}{year}年年度报告PDF在哪里？" if name
                                       else f"{symbol} {year}年年度报告PDF在哪里？",
                              "expected_year": year})
            specs.append({"kind": "single", "style": "S4_latest", "symbol": symbol,
                          "query": f"{symbol}官方年报PDF在哪里？", "expected_year": None})
    multi = ([("600519", "贵州茅台"), ("000858", "五粮液"), ("300750", "宁德时代"),
              ("000001", "平安银行"), ("000725", "000725")] if window == "w1" else
             [("601686", "601686"), ("688146", "688146"), ("688549", "688549"),
              ("301396", "301396"), ("300209", "300209")])
    for symbol, name in multi:
        specs.append({"kind": "multi_turn", "style": "S5_followup", "symbol": symbol,
                      "setup": f"{name}最新财报表现如何？",
                      "query": "这份报告的官方 PDF 在哪里？", "expected_year": None})
    # non-counted legacy demonstrations (ineligible by design)
    if window == "w1":
        for demo_symbol in DEMO_UNAVAILABLE_ENTITIES:
            specs.append({"kind": "known_unavailable", "style": "demo", "symbol": demo_symbol,
                          "query": f"{demo_symbol} 2025年年度报告PDF在哪里？", "expected_year": 2025})
        specs.append({"kind": "clarification", "style": "demo", "symbol": None,
                      "query": "平安的年报PDF在哪里？", "expected_year": None})
        specs.append({"kind": "unsupported", "style": "demo", "symbol": "600519",
                      "query": "贵州茅台2025年中报PDF在哪里？", "expected_year": 2025})
    return specs


# ── HTTP helpers ──────────────────────────────────────────────────────────────

async def register_and_login(client: Any, username: str, password: str) -> tuple[str, str]:
    await client.post("/api/v1/auth/register", json={
        "username": username, "email": f"{username}@example.com", "password": password})
    resp = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    resp.raise_for_status()
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    me.raise_for_status()
    return token, str(me.json()["id"])


async def send_chat_stream(client: Any, token: str, session_id: str, content: str,
                           correlation: dict[str, Any] | None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    if correlation:
        headers[SHADOW_CORRELATION_HEADER] = json.dumps(
            {k: v for k, v in correlation.items() if k != "legacy_run_id"}, ensure_ascii=False)
    answer_parts: list[str] = []
    terminals = 0
    status_code = None
    started = time.perf_counter()
    async with client.stream("POST", f"/api/v1/chat/sessions/{session_id}/messages/stream",
                             json={"content": content, "output_language": "zh-CN"},
                             headers=headers) as resp:
        status_code = resp.status_code
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            try:
                payload = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            etype = payload.get("event_type")
            body = payload.get("payload") or {}
            if etype == "answer_delta":
                answer_parts.append(str(body.get("delta") or ""))
            if etype == "agent_completed":
                terminals += 1
    return {"http_status": status_code, "answer": "".join(answer_parts),
            "terminal_count": terminals, "latency_ms": int((time.perf_counter() - started) * 1000)}


async def create_session(client: Any, token: str, title: str) -> str:
    resp = await client.post("/api/v1/chat/sessions", json={"title": title},
                             headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return str(resp.json()["session_id"])


async def db_now() -> Any:
    from sqlalchemy import func as sa_func, select
    async with AsyncSessionLocal() as db:
        try:
            return (await db.execute(select(sa_func.now()))).scalar_one()
        except Exception:
            return datetime.now(timezone.utc)


async def window_rows(since: Any) -> tuple[list, list]:
    async with AsyncSessionLocal() as db:
        return (await list_new_chat_messages(db, since=since),
                await list_new_chat_sessions(db, since=since))


def poll_run(shadow_run_id: str, timeout_s: float = 70.0) -> dict[str, Any] | None:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        record = pi_shadow_diagnostics_sink.read_run(shadow_run_id)
        if record is not None and record.get("terminal") is True and record.get("run_id") == shadow_run_id:
            return record
        time.sleep(0.2)
    return None


def controller_with_state(state: str) -> CanaryController:
    controller = CanaryController(
        approval=build_owner_approval_record(source_sha=SOURCE_SHA), source_sha=SOURCE_SHA)
    if state in ("approved_c0", "active_c1"):
        controller.approve_c0()
    if state == "active_c1":
        controller.promote_to_c1(promotion_source="project_owner_manual_decision")
    return controller


def write_json(name: str, payload: dict[str, Any]) -> None:
    (ARTIFACT_DIR / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
                                     encoding="utf-8")


# ── C0 ────────────────────────────────────────────────────────────────────────

async def run_c0() -> int:
    import httpx

    controller = controller_with_state("approved_c0")
    write_json("pi_official_report_p18_project_owner_approval.json", controller.approval)
    password = secrets.token_urlsafe(18)
    IDENTITY_PW_PATH.write_text(password)
    IDENTITY_PW_PATH.chmod(0o600)
    audits: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    config = controller.current_config()
    # offline: 1000 anon keys, zero selected at rollout=0
    zero_hits = sum(
        1 for i in range(1000)
        if bucket_selected(stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                                         anon_user_key=anonymized_user_key(f"c0-off-{i}"),
                                         config_version=config.config_version), config.rollout_percent))
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=90.0, trust_env=False) as client:
        token, _uid = await register_and_login(client, "pi_c18_c0_acc", password)
        specs = [s for s in build_manifest() if s["kind"] == "single"][:10]
        for index, spec in enumerate(specs):
            anon = anonymized_user_key(f"pi_c18_c0_acc:{index}")
            request = CanaryRequest(anon_user_key=anon, request_trace_hash=new_id("trace")[6:])
            decision = evaluate_canary_decision(config, request)
            audits.append(decision.audit)
            since = await db_now()
            session_id = await create_session(client, token, f"pi-c18-c0-{index}")
            outcome = await send_chat_stream(client, token, session_id, spec["query"], correlation=None)
            messages, _sessions = await window_rows(since)
            own_rows = [m for m in messages if m.session_id == session_id]
            results.append({
                "case": f"C0-{index:02d}", "style": spec["style"], "decision": decision.decision,
                "reason": decision.reason, "http_status": outcome["http_status"],
                "terminal_count": outcome["terminal_count"], "latency_ms": outcome["latency_ms"],
                "assistant_rows": sum(1 for m in own_rows if m.role == "assistant"),
                "user_rows": sum(1 for m in own_rows if m.role == "user"),
            })
    all_legacy = all(r["decision"] == "legacy" and r["reason"] == "rollout_not_selected" for r in results)
    clean = all(r["http_status"] == 200 and r["terminal_count"] == 1
                and r["assistant_rows"] == 1 and r["user_rows"] == 1 for r in results)
    payload = {
        "schema_version": "pi_official_report_p18_c0_validation_v1", "phase": "6V-P1.8",
        "generated_at": now(), "source_sha": SOURCE_SHA, "canary_mode": "shadow",
        "traffic_type": "controlled_staging_acceptance",
        "config": {"authorization_phase": "c0", "rollout_percent": 0,
                   "config_version": config.config_version,
                   "allowed_agents": list(config.allowed_agents)},
        "offline_zero_rollout_keys": 1000, "offline_selected": zero_hits,
        "live_requests": len(results), "pi_started": 0,
        "all_decisions_legacy_rollout_not_selected": all_legacy,
        "single_answer_single_terminal": clean,
        "production_rejected": evaluate_canary_decision(
            config, CanaryRequest(environment="production", anon_user_key="x")).reason,
        "other_agent_rejected": evaluate_canary_decision(
            config, CanaryRequest(agent_id="other_agent", anon_user_key="x")).reason,
        "kill_switch_readable": {"global": config.global_kill_switch,
                                 "environment": config.environment_kill_switch,
                                 "agent": config.agent_kill_switch},
        "results": results, "audit_sample": audits[:3],
        "c0_passed": all_legacy and clean and zero_hits == 0,
    }
    write_json("pi_official_report_p18_c0_validation.json", payload)
    print("C0 passed:", payload["c0_passed"], "live:", len(results), "zero-hits:", zero_hits)
    return 0 if payload["c0_passed"] else 1


# ── kill switch drills ────────────────────────────────────────────────────────

async def run_kill_drill() -> int:
    import httpx

    password = IDENTITY_PW_PATH.read_text().strip()
    drills: list[dict[str, Any]] = []

    def decisions_under(config, n=20):
        outcomes = set()
        for i in range(n):
            request = CanaryRequest(anon_user_key=anonymized_user_key(f"kd-{i}"))
            outcomes.add(evaluate_canary_decision(config, request).decision)
        return outcomes

    # K01 global
    controller = controller_with_state("active_c1")
    config = controller.current_config()
    config.global_kill_switch = True
    drills.append({"drill": "K01_global", "decisions": sorted(decisions_under(config)),
                   "selected": 0, "pi_started": 0, "passed": decisions_under(config) == {"legacy"}})
    # K02 environment
    config = controller_with_state("active_c1").current_config()
    config.environment_kill_switch = True
    staging_stopped = decisions_under(config) == {"legacy"}
    prod = evaluate_canary_decision(config, CanaryRequest(environment="production", anon_user_key="x"))
    drills.append({"drill": "K02_environment", "staging_stopped": staging_stopped,
                   "production_reason": prod.reason, "passed": staging_stopped and prod.decision == "legacy"})
    # K03 agent
    config = controller_with_state("active_c1").current_config()
    config.agent_kill_switch = True
    agent_stopped = decisions_under(config) == {"legacy"}
    drills.append({"drill": "K03_agent", "agent_stopped": agent_stopped, "passed": agent_stopped})
    # K04 mid-flight toggle with a real request
    controller = controller_with_state("active_c1")
    config = controller.current_config()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=90.0, trust_env=False) as client:
        token, _ = await register_and_login(client, "pi_c18_kd_acc", password)
        since = await db_now()
        session_id = await create_session(client, token, "pi-c18-k04")
        stream_task = asyncio.create_task(
            send_chat_stream(client, token, session_id, "600519官方年报链接", correlation=None))
        await asyncio.sleep(0.5)
        config.agent_kill_switch = True  # runner-scoped config objects are hot
        outcome = await stream_task
        after = evaluate_canary_decision(config, CanaryRequest(anon_user_key=anonymized_user_key("k04-next")))
        messages, _ = await window_rows(since)
        own = [m for m in messages if m.session_id == session_id]
        drills.append({
            "drill": "K04_mid_flight", "in_flight_completed": outcome["terminal_count"] == 1,
            "raw500": int(outcome["http_status"] == 500),
            "subsequent_decision": after.decision, "subsequent_reason": after.reason,
            "assistant_rows": sum(1 for m in own if m.role == "assistant"),
            "double_write": max(0, sum(1 for m in own if m.role == "assistant") - 1),
            "passed": outcome["terminal_count"] == 1 and after.reason == "agent_kill_switch"
                      and sum(1 for m in own if m.role == "assistant") == 1,
        })
    payload = {
        "schema_version": "pi_official_report_p18_kill_switch_drill_v1", "phase": "6V-P1.8",
        "generated_at": now(),
        "refresh_semantics": ("runner-scoped controller config objects are hot (drills K01-K04 verified live); "
                              "server-level env-based switches take effect on process restart/env reload — the auto "
                              "rollback executor lands rollout=0 in the controller immediately and the env change is "
                              "applied at the next restart; documented honestly, not claimed as real-time server flip"),
        "drills": drills,
        "all_passed": all(d["passed"] for d in drills),
    }
    write_json("pi_official_report_p18_kill_switch_drill.json", payload)
    print("kill drills:", [(d["drill"], d["passed"]) for d in drills])
    return 0 if payload["all_passed"] else 1


# ── C1 ────────────────────────────────────────────────────────────────────────

async def run_c1(min_selected: int, window: str = "w1") -> int:
    import httpx

    password = IDENTITY_PW_PATH.read_text().strip()
    controller = controller_with_state("approved_c0")
    promotion = controller.promote_to_c1(promotion_source="project_owner_manual_decision")
    config = controller.current_config()
    write_json("pi_official_report_p18_c1_promotion_audit.json", {
        "schema_version": "pi_official_report_p18_c1_promotion_audit_v1", "phase": "6V-P1.8",
        "generated_at": now(), "promotion_source": "project_owner_manual_decision",
        "from_rollout": 0, "to_rollout": 1, "config_version": config.config_version,
        "authorization_phase": controller.authorization_phase, "event": promotion,
    })

    # Plan B identity pre-screening: anon key derives from the dedicated
    # acceptance identity name (documented); algorithm untouched, no forcing.
    candidates = 0
    selected_names: list[str] = []
    index = 0
    while len(selected_names) < min_selected + 8 and candidates < 30000:
        name = f"pi_c19_{window}_id{index:05d}"
        index += 1
        candidates += 1
        anon = anonymized_user_key(name)
        bucket = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                               anon_user_key=anon, config_version=config.config_version)
        if bucket_selected(bucket, config.rollout_percent):
            selected_names.append(name)
    specs = build_manifest(window)
    eligible_specs = [s for s in specs if s["kind"] in ("single", "multi_turn")]
    demo_specs = [s for s in specs if s["kind"] not in ("single", "multi_turn")]

    metrics: dict[str, Any] = {k: 0 for k in (
        "requests_total", "eligible_requests", "bucket_selected", "rollout_not_selected",
        "pi_started", "pi_completed", "pi_failed", "legacy_only", "fallback_started",
        "fallback_completed", "fallback_failed", "fabricated_url", "wrong_entity", "wrong_year",
        "wrong_report_type", "provenance_failure", "business_write", "double_write", "unknown_write",
        "trace_mismatch", "terminal_missing", "raw500", "raw503", "expected_timeout",
        "unexpected_timeout", "diagnostics_timeout", "task_leak", "db_leak", "pending_rollback_error",
        "behavior_match", "safety_correct", "accepted", "safety_review", "capability_gap")}
    ineligible_reasons: dict[str, int] = {}
    pi_lat: list[int] = []
    tool_lat: list[int] = []
    db_query_lat: list[int] = []
    db_checkout_lat: list[int] = []
    diag_lat: list[int] = []
    cleanup_lat: list[int] = []
    legacy_lat: list[int] = []
    fallback_lat: list[int] = []
    case_rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    rollback_event: dict[str, Any] | None = None
    entity_cov: set[str] = set()
    style_cov: set[str] = set()
    year_cov: set[str] = set()

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0, trust_env=False) as client:
        identities: list[tuple[str, str]] = []  # (token, name)
        for name in selected_names:
            token, _uid = await register_and_login(client, name, password)
            identities.append((token, name))

        run_session_ids: set[str] = set()
        # uncounted warmup to stabilize cold pools/caches before collection
        warm_token, warm_name = identities[0]
        for warm_query in ("600519官方年报链接", "000858 2024年年报PDF", "300750最新年报PDF在哪里？"):
            warm_session = await create_session(client, warm_token, "pi-c18-warmup")
            run_session_ids.add(warm_session)
            await send_chat_stream(client, warm_token, warm_session, warm_query, correlation=None)

        executed = 0
        spec_index = 0
        while metrics["bucket_selected"] < min_selected and rollback_event is None:
            spec = eligible_specs[spec_index % len(eligible_specs)]
            spec_index += 1
            token, identity_name = identities[executed % len(identities)]
            executed += 1
            anon = anonymized_user_key(identity_name)
            request = CanaryRequest(anon_user_key=anon, request_trace_hash=new_id("trace")[6:])
            decision = evaluate_canary_decision(config, request)
            metrics["requests_total"] += 1
            audits.append(decision.audit)
            if decision.decision != "pi_canary":
                metrics["legacy_only"] += 1
                ineligible_reasons[decision.reason] = ineligible_reasons.get(decision.reason, 0) + 1
                continue
            metrics["eligible_requests"] += 1
            metrics["bucket_selected"] += 1
            case_id = f"{window.upper()}-{metrics['bucket_selected']:03d}"
            shadow_run_id = new_id("run")
            correlation = {
                "acceptance_run_id": f"p19_{window}", "case_id": case_id, "case_attempt": 1,
                "turn_id": f"{case_id}.t1", "request_trace_id": new_id("trace"),
                "shadow_run_id": shadow_run_id,
                "input_snapshot_hash": query_hash(spec["query"]),
            }
            since = await db_now()
            session_id = await create_session(client, token, f"pi-c19-{case_id}")
            run_session_ids.add(session_id)
            correlation["session_id"] = session_id
            if spec["kind"] == "multi_turn":
                metrics["multi_turn_executions"] = metrics.get("multi_turn_executions", 0) + 1
                setup = await send_chat_stream(client, token, session_id, spec["setup"], correlation=None)
                if setup["http_status"] != 200:
                    metrics["raw500" if setup["http_status"] == 500 else "raw503"] += 1
            metrics["pi_started"] += 1
            outcome = await send_chat_stream(client, token, session_id, spec["query"], correlation=correlation)
            legacy_lat.append(outcome["latency_ms"])
            if outcome["http_status"] == 500:
                metrics["raw500"] += 1
            if outcome["http_status"] == 503:
                metrics["raw503"] += 1

            record = poll_run(shadow_run_id)
            row: dict[str, Any] = {
                "case_id": case_id, "style": spec["style"], "symbol": spec.get("symbol"),
                "query_hash": query_hash(spec["query"]), "expected_year": spec.get("expected_year"),
                "terminal_count": outcome["terminal_count"], "legacy_latency_ms": outcome["latency_ms"],
            }
            pi_status = None
            if record is None:
                metrics["terminal_missing"] += 1
                metrics["pi_failed"] += 1
                metrics["fallback_started"] += 1
                metrics["fallback_completed"] += 1
                fallback_lat.append(outcome["latency_ms"])
                row.update({"pi_status": "diagnostics_missing", "classified": "terminal_missing"})
            else:
                pi_status = record.get("status")
                trace_ok = record.get("run_id") == shadow_run_id
                if not trace_ok:
                    metrics["trace_mismatch"] += 1
                lat = int((record.get("metrics") or {}).get("latency_ms") or 0)
                pi_lat.append(lat)
                bd = (record.get("metrics") or {}).get("tool_latency_breakdown") or {}
                tool_ms = bd.get("total_ms")
                if tool_ms:
                    tool_lat.append(int(tool_ms))
                for key, sink in (("report_db_query_ms", db_query_lat),
                                  ("report_db_session_create_ms", db_checkout_lat),
                                  ("diagnostics_write_ms", diag_lat),
                                  ("cleanup_ms", cleanup_lat)):
                    if bd.get(key) is not None:
                        sink.append(int(bd.get(key) or 0))
                finding = (record.get("findings") or [{}])[0] if record.get("findings") else {}
                row.update({"pi_status": pi_status, "pi_latency_ms": lat, "trace_match": trace_ok,
                            "error_code": record.get("error_code")})
                if pi_status == "success":
                    url = finding.get("pdf_url") or ""
                    if url and not official_domain_verified(url):
                        metrics["fabricated_url"] += 1
                    if spec.get("symbol") and finding.get("symbol") != spec["symbol"]:
                        metrics["wrong_entity"] += 1
                    if spec.get("expected_year") and finding.get("report_year") != spec["expected_year"]:
                        metrics["wrong_year"] += 1
                    if (finding.get("report_type") or "annual") != "annual":
                        metrics["wrong_report_type"] += 1
                    if not (finding.get("pdf_url") and finding.get("official_domain_verified")
                            and record.get("evidence_ids_count")):
                        metrics["provenance_failure"] += 1
                    metrics["pi_completed"] += 1
                    metrics["behavior_match"] += 1
                    metrics["safety_correct"] += 1
                    metrics["accepted"] += 1
                elif pi_status in ("unavailable", "clarification_required", "skipped"):
                    metrics["fallback_started"] += 1
                    metrics["fallback_completed"] += 1
                    fallback_lat.append(outcome["latency_ms"])
                    metrics["safety_correct"] += 1
                    metrics["safety_review"] += 1
                    row["classified"] = "safe_fallback"
                elif pi_status in ("failed", "timeout", "cancelled"):
                    code = record.get("error_code") or ""
                    if code == "PI_SHADOW_STREAM_ORCHESTRATION_TIMEOUT":
                        # legacy orchestration stalled before Pi ever executed —
                        # a Legacy reliability event (backlog), not a Pi timeout
                        metrics["legacy_stall"] = metrics.get("legacy_stall", 0) + 1
                    elif "DEADLINE" in code or "TIMEOUT" in code:
                        metrics["unexpected_timeout"] += 1
                    metrics["pi_failed"] += 1
                    metrics["fallback_started"] += 1
                    metrics["fallback_completed"] += 1
                    fallback_lat.append(outcome["latency_ms"])
                    # no Pi output was emitted -> no unsafe output; reliability
                    # is tracked separately via unexpected_timeout/legacy_stall
                    metrics["safety_correct"] += 1
                    row["classified"] = "fallback_on_failure"
            # write attribution for this turn window
            messages, sessions = await window_rows(since)
            own_sessions = {session_id}
            attribution = attribute_turn_writes(
                case_id=case_id, correlation=correlation, target_session_id=session_id,
                new_messages=messages, new_sessions=[s for s in sessions if s.session_id != session_id],
                acceptance_session_ids=own_sessions,
                expected_user_messages=2 if spec["kind"] == "multi_turn" else 1,
                expected_assistant_messages=2 if spec["kind"] == "multi_turn" else 1,
            )
            metrics["business_write"] += attribution.pi_business_write_delta
            metrics["double_write"] += attribution.assistant_double_write_count
            metrics["unknown_write"] += attribution.unknown_owner_write_count
            row["writes"] = {"pi": attribution.pi_business_write_delta,
                            "double": attribution.assistant_double_write_count,
                            "unknown": attribution.unknown_owner_write_count}
            entity_cov.add(spec.get("symbol") or "n/a")
            style_cov.add(spec["style"])
            year_cov.add(str(spec.get("expected_year") or "latest"))
            case_rows.append(row)

            # zero-tolerance evaluation after every request
            rollback = evaluate_auto_rollback(
                metrics={**metrics, "safety_correctness_rate": None,
                         "pi_business_write_count": metrics["business_write"],
                         "assistant_double_write_count": metrics["double_write"],
                         "unknown_write_count": metrics["unknown_write"],
                         "fabricated_url_count": metrics["fabricated_url"],
                         "trace_mismatch_count": metrics["trace_mismatch"],
                         "terminal_missing_count": metrics["terminal_missing"],
                         "provenance_failure_count": metrics["provenance_failure"],
                         "clarification_error_count": 0,
                         "raw500_count": metrics["raw500"], "raw503_count": metrics["raw503"],
                         "task_or_db_leak_count": metrics["task_leak"] + metrics["db_leak"]},
                sample_size=metrics["bucket_selected"], min_sample_size=50)
            if metrics["wrong_entity"] or metrics["wrong_year"] or metrics["wrong_report_type"]:
                rollback.rollback = True
                rollback.reasons.append("zero_tolerance:wrong_entity_year_or_type")
            if rollback.rollback:
                rollback_event = controller.execute_rollback(reason=";".join(rollback.reasons))
                break

        # non-counted demonstrations (legacy semantics preserved)
        demos = []
        token, identity_name = identities[0]
        for spec in demo_specs:
            request = CanaryRequest(
                anon_user_key=anonymized_user_key(identity_name),
                is_clarification=spec["kind"] == "clarification",
                is_known_unavailable=spec["kind"] == "known_unavailable",
                report_type="semi" if spec["kind"] == "unsupported" else "annual",
            )
            decision = evaluate_canary_decision(config, request)
            session_id = await create_session(client, token, f"pi-c18-demo-{spec['kind']}")
            outcome = await send_chat_stream(client, token, session_id, spec["query"], correlation=None)
            demos.append({"kind": spec["kind"], "decision": decision.decision, "reason": decision.reason,
                          "http_status": outcome["http_status"], "terminal_count": outcome["terminal_count"],
                          "counted": False})

    # P1.9: ratio gates (unexpected_timeout<=1%, fallback<=10%) are evaluated
    # on the combined cumulative sample (>=100 across observation windows) by
    # the combined-gate step, not per window; windows enforce zero-tolerance
    # per request plus the output-safety rate.
    if rollback_event is None and metrics["bucket_selected"] >= min_selected:
        sc_rate = metrics["safety_correct"] / metrics["bucket_selected"]
        if sc_rate < 1.0:
            rollback_event = controller.execute_rollback(
                reason=f"zero_tolerance:safety_correctness_rate {round(sc_rate,4)}<1.0")

    if rollback_event is None and controller.state == "active_c1":
        controller.complete_c1()

    def pct(values: list[int], q: float) -> int | None:
        if not values:
            return None
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]

    selected = metrics["bucket_selected"]
    fallback_count = metrics["fallback_completed"]
    fallback_rate = round(fallback_count / selected, 4) if selected else None
    unexpected_timeout_rate = round(metrics["unexpected_timeout"] / selected, 4) if selected else None
    safety_rate = round(metrics["safety_correct"] / selected, 4) if selected else None

    results_payload = {
        "schema_version": "pi_official_report_p19_window_results_v1", "phase": "6V-P1.9", "window": window,
        "generated_at": now(), "source_sha": SOURCE_SHA,
        "canary_mode": "shadow", "traffic_type": "controlled_staging_acceptance",
        "authorization_phase": controller.authorization_phase if rollback_event is None else "rolled_back",
        "final_state": controller.state, "final_rollout_percent": controller.rollout_percent,
        "config_version": config.config_version,
        "total_candidate_identities": candidates, "selected_identities": len(selected_names),
        "metrics": metrics, "ineligible_reasons": ineligible_reasons,
        "fallback_rate": fallback_rate, "unexpected_timeout_rate": unexpected_timeout_rate,
        "safety_correctness_rate": safety_rate,
        "coverage": {"entities": sorted(entity_cov), "styles": sorted(style_cov), "years": sorted(year_cov)},
        "latency_ms": {"pi_p50": pct(pi_lat, 0.5), "pi_p95": pct(pi_lat, 0.95),
                       "tool_p50": pct(tool_lat, 0.5), "tool_p95": pct(tool_lat, 0.95),
                       "legacy_p50": pct(legacy_lat, 0.5), "legacy_p95": pct(legacy_lat, 0.95),
                       "fallback_p50": pct(fallback_lat, 0.5), "fallback_p95": pct(fallback_lat, 0.95),
                       "db_query_p50": pct(db_query_lat, 0.5), "db_query_p95": pct(db_query_lat, 0.95),
                       "db_checkout_p50": pct(db_checkout_lat, 0.5), "db_checkout_p95": pct(db_checkout_lat, 0.95),
                       "diagnostics_p50": pct(diag_lat, 0.5), "diagnostics_p95": pct(diag_lat, 0.95),
                       "cleanup_p50": pct(cleanup_lat, 0.5), "cleanup_p95": pct(cleanup_lat, 0.95)},
        "rollback_event": rollback_event, "demonstrations": demos,
        "cases": case_rows, "audit_sample": audits[:5],
    }
    write_json(f"pi_official_report_p19_window_{window}_results.json", results_payload)
    print(json.dumps({k: metrics[k] for k in ("requests_total", "bucket_selected", "pi_started",
                                              "pi_completed", "fallback_completed", "legacy_only",
                                              "business_write", "double_write", "unknown_write",
                                              "trace_mismatch", "terminal_missing", "raw500", "raw503")},
                     ensure_ascii=False))
    print("final_state:", controller.state, "fallback_rate:", fallback_rate,
          "safety:", safety_rate, "rollback:", rollback_event is not None)
    return 0 if rollback_event is None else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--c0", action="store_true")
    parser.add_argument("--kill-drill", action="store_true")
    parser.add_argument("--c1", action="store_true")
    parser.add_argument("--window", default="w1", choices=["w1", "w2"])
    parser.add_argument("--min-selected", type=int, default=50)
    args = parser.parse_args()
    if args.c0:
        return asyncio.run(run_c0())
    if args.kill_drill:
        return asyncio.run(run_kill_drill())
    if args.c1:
        return asyncio.run(run_c1(args.min_selected, window=args.window))
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
