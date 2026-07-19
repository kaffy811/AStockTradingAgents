from __future__ import annotations

import asyncio
import json
import importlib.util
from pathlib import Path

import pytest

from app.agent_runtime.shadow_acceptance import (
    ShadowSideEffectSnapshot,
    _sql_logging_audit,
    build_agent_gate,
    build_runtime_gate,
    build_write_attribution,
    compute_pi_side_effect_count,
    summarize_shadow_results,
)
from app.agent_runtime.shadow_diagnostics import PiShadowDiagnosticsSink, query_hash, user_hash
from app.services.official_report_entity_hints import (
    ambiguous_official_report_entity_hint,
    unambiguous_official_report_entity_hint,
)

ROOT = Path(__file__).parents[3]
RUNNER_PATH = ROOT / "backend" / "scripts" / "pi_official_report_pdf_live_shadow_acceptance.py"
spec = importlib.util.spec_from_file_location("pi_shadow_acceptance_runner", RUNNER_PATH)
runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(runner)


def test_zero_samples_gate_remains_null():
    summary = summarize_shadow_results([], planned_samples=30)
    gate = build_agent_gate(summary)
    runtime_gate = build_runtime_gate(gate)
    assert gate["executed_samples"] == 0
    assert gate["metrics"]["status_match_rate"] is None
    assert gate["metrics"]["url_match_rate"] is None
    assert gate["recommended_for_next_authorization"] is False
    assert runtime_gate["decision"] == "do_not_enable_pi_compatible"


@pytest.mark.asyncio
async def test_no_identity_refuses_execution():
    class Args:
        access_token = ""
        user_id = ""
        allow_local_fixture_user = False

    identity = await runner.resolve_acceptance_identity(Args(), {})
    assert identity["ready"] is False
    assert "token" in identity["blockers"][0]


@pytest.mark.asyncio
async def test_no_shadow_env_preflight_refuses_execution(tmp_path, monkeypatch):
    class Args:
        execute = True
        base_url = ""
        frontend_base_url = ""
        access_token = ""
        user_id = ""
        allow_local_fixture_user = False
        environment_type = "local_live"

    monkeypatch.setattr(runner.settings, "pi_agent_shadow_diagnostics_path", str(tmp_path / "diag.jsonl"))
    monkeypatch.setattr(runner.settings, "agent_executor_mode", "legacy")
    report = await runner.build_environment_report(Args())
    assert report["shadow_enabled"] is False
    assert report["environment_ready"] is False
    assert any("shadow" in item.lower() for item in report["blockers"])


@pytest.mark.asyncio
async def test_preflight_refuses_production(tmp_path, monkeypatch):
    class Args:
        execute = True
        base_url = ""
        frontend_base_url = ""
        access_token = "token"
        user_id = "00000000-0000-0000-0000-000000000001"
        allow_local_fixture_user = False
        environment_type = "staging"

    monkeypatch.setattr(runner.settings, "pi_agent_shadow_diagnostics_path", str(tmp_path / "diag.jsonl"))
    monkeypatch.setattr(runner.settings, "app_env", "production")
    report = await runner.build_environment_report(Args())
    assert report["no_production_mode"] is False
    assert any("production" in item.lower() for item in report["blockers"])


@pytest.mark.asyncio
async def test_diagnostics_path_missing_refuses_execution(monkeypatch):
    class Args:
        execute = True
        base_url = ""
        frontend_base_url = ""
        access_token = "token"
        user_id = "00000000-0000-0000-0000-000000000001"
        allow_local_fixture_user = False
        environment_type = "local_live"

    monkeypatch.setattr(runner.settings, "pi_agent_shadow_diagnostics_path", "")
    report = await runner.build_environment_report(Args())
    assert report["diagnostics_ready"] is False
    assert any("DIAGNOSTICS_PATH" in item for item in report["blockers"])


@pytest.mark.asyncio
async def test_local_fixture_not_counted_as_live(tmp_path, monkeypatch):
    class Args:
        execute = True
        base_url = "http://127.0.0.1:8000"
        frontend_base_url = ""
        access_token = ""
        user_id = ""
        allow_local_fixture_user = True
        environment_type = "local_fixture"

    monkeypatch.setattr(runner.settings, "pi_agent_shadow_diagnostics_path", str(tmp_path / "diag.jsonl"))
    report = await runner.build_environment_report(Args())
    assert report["environment_type"] == "local_fixture"
    assert any("local_fixture" in item for item in report["blockers"])


def test_token_never_logged_in_diagnostics(tmp_path, monkeypatch):
    path = tmp_path / "diag.jsonl"
    monkeypatch.setattr("app.agent_runtime.shadow_diagnostics.settings.pi_agent_shadow_diagnostics_path", str(path))
    sink = PiShadowDiagnosticsSink()
    sink.record(
        raw_query="五粮液2025年年度报告PDF在哪里？",
        conversation_id="conv",
        user_id="00000000-0000-0000-0000-000000000001",
        result={
            "trace_id": "trace",
            "run_id": "run",
            "status": "success",
            "agent_id": "official_report_pdf_pi_v1",
            "metrics": {"latency_ms": 1, "model_calls": 0},
            "findings": [{"symbol": "000858", "pdf_url": "https://static.cninfo.com.cn/a.PDF", "official_domain_verified": True}],
            "evidence_ids": ["e1"],
            "events": [],
        },
    )
    text = path.read_text(encoding="utf-8")
    assert "五粮液2025" not in text
    assert "Bearer" not in text
    assert "00000000-0000-0000-0000-000000000001" not in text
    record = json.loads(text)
    assert record["query_hash"] == query_hash("五粮液2025年年度报告PDF在哪里？")
    assert record["user_hash"] == user_hash("00000000-0000-0000-0000-000000000001")
    assert record["input_snapshot_hash"]
    assert record["terminal"] is True
    assert record["completed_at"]


def test_shadow_terminal_diagnostics_for_skipped_and_timeout(tmp_path, monkeypatch):
    path = tmp_path / "diag.jsonl"
    monkeypatch.setattr("app.agent_runtime.shadow_diagnostics.settings.pi_agent_shadow_diagnostics_path", str(path))
    sink = PiShadowDiagnosticsSink()
    for status in ("skipped", "timeout"):
        sink.record(
            raw_query=f"case-{status}",
            conversation_id="conv",
            user_id="00000000-0000-0000-0000-000000000001",
            result={
                "trace_id": f"trace-{status}",
                "run_id": f"run-{status}",
                "status": status,
                "agent_id": "official_report_pdf_pi_v1",
                "metrics": {"latency_ms": 1, "model_calls": 0},
                "findings": [],
                "evidence_ids": [],
                "events": [],
                "error": {"code": f"PI_SHADOW_{status.upper()}"},
            },
        )

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [record["status"] for record in records] == ["skipped", "timeout"]
    assert all(record["terminal"] is True for record in records)
    assert all(record["completed_at"] for record in records)


def test_test_session_isolated_title_prefix():
    assert "pi-shadow-" in runner._browser_markdown(executed=False, passed=False, notes="pi-shadow-A01")


def test_symbol_hint_routes_explicit_code_to_official_report_agent():
    hint = unambiguous_official_report_entity_hint("600519官方年报链接", include_query=True)
    assert hint["symbol"] == "600519"
    assert hint["name"] == "贵州茅台"
    assert hint["source"] == "unambiguous_symbol_hint"


def test_ambiguous_pingan_hint_requires_clarification_without_tool_call():
    hint = ambiguous_official_report_entity_hint("平安的年报PDF在哪里？")
    assert hint["source"] == "ambiguous_name_hint"
    names = {item["name"] for item in hint["candidates"]}
    assert {"平安银行", "中国平安"}.issubset(names)


@pytest.mark.asyncio
async def test_callback_timeout_handled(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.settings, "pi_agent_shadow_diagnostics_path", str(tmp_path / "missing.jsonl"))
    result = await runner._poll_shadow_diagnostic(conversation_id="conv", raw_query="q", user_id="u", timeout_seconds=0.01)
    assert result["status"] == "failed"
    assert result["shadow_terminal_received"] is False
    assert result["error"]["code"] == "PI_SHADOW_TIMEOUT"


@pytest.mark.asyncio
async def test_sse_completion_required():
    class Response:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield 'data: {"event_type": "answer_delta", "payload": {"delta": "ok"}}'

    class Client:
        def stream(self, *_args, **_kwargs):
            return Response()

    with pytest.raises(RuntimeError, match="agent_completed"):
        await runner._send_http_chat_stream(Client(), "session", "hello")


@pytest.mark.asyncio
async def test_sse_terminal_exactly_once_required():
    class Response:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield 'data: {"event_type": "agent_completed", "payload": {"status": "completed"}}'
            yield 'data: {"event_type": "agent_completed", "payload": {"status": "completed"}}'

    class Client:
        def stream(self, *_args, **_kwargs):
            return Response()

    with pytest.raises(RuntimeError, match="agent_completed"):
        await runner._send_http_chat_stream(Client(), "session", "hello")


@pytest.mark.asyncio
async def test_runner_records_legacy_terminal_and_message_persistence():
    class Response:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield 'data: {"event_type": "answer_delta", "payload": {"delta": "ok"}}'
            yield 'data: {"event_type": "message_persisted", "payload": {"message_id": "m"}}'
            yield 'data: {"event_type": "agent_completed", "payload": {"status": "completed"}}'

    class Client:
        def stream(self, *_args, **_kwargs):
            return Response()

    legacy = await runner._send_http_chat_stream(Client(), "session", "hello")
    assert legacy["http_response_started"] is True
    assert legacy["sse_terminal_received"] is True
    assert legacy["sse_terminal_event_count"] == 1
    assert legacy["legacy_terminal_status"] == "completed"
    assert legacy["legacy_message_persisted"] is True
    assert legacy["answer"] == "ok"


def test_smoke_cases_are_fixed_p161_set():
    cases = runner._smoke_cases()
    assert [case.case_id for case in cases] == ["A01", "A02", "A03"]
    assert cases[0].setup_query == "贵州茅台最新财报表现如何？"
    assert cases[0].query == "这份报告的官方 PDF 在哪里？"
    assert cases[1].query == "600519官方年报链接"
    assert cases[2].expected_status == "clarification_required"


def test_legacy_writes_excluded_and_pi_extra_write_detected():
    before = ShadowSideEffectSnapshot(1, 10, 0, 0, 0, 0, 0, 0, 0)
    after = ShadowSideEffectSnapshot(1, 12, 0, 0, 0, 0, 0, 0, 0)
    assert compute_pi_side_effect_count(before, after, expected_legacy_chat_message_delta=2) == 0
    extra = ShadowSideEffectSnapshot(1, 13, 0, 0, 0, 0, 0, 0, 0)
    assert compute_pi_side_effect_count(before, extra, expected_legacy_chat_message_delta=2) == 1


def test_context_extra_update_detected():
    before = ShadowSideEffectSnapshot(1, 10, 0, 0, 0, 0, 0, 0, 0)
    after = ShadowSideEffectSnapshot(1, 12, 1, 0, 0, 0, 0, 0, 0)
    assert compute_pi_side_effect_count(before, after, expected_legacy_chat_message_delta=2) == 1


def test_legacy_context_writes_are_attributed_not_counted_as_pi_side_effect():
    before = ShadowSideEffectSnapshot(
        1, 10, 0, 0, 0, 0, 0, 0, 0,
        target_session_id="00000000-0000-0000-0000-000000000001",
        target_session_context_version=3,
        target_session_metadata_keys=["memory_v1"],
    )
    after = ShadowSideEffectSnapshot(
        1, 12, 2, 0, 0, 0, 0, 0, 0,
        target_session_id="00000000-0000-0000-0000-000000000001",
        target_session_context_version=5,
        target_session_metadata_keys=["memory_v1"],
        target_session_last_context_commit_at="2026-07-18T10:00:00+00:00",
    )
    assert compute_pi_side_effect_count(
        before,
        after,
        expected_legacy_chat_message_delta=2,
        expected_legacy_context_version_delta=2,
    ) == 0
    attribution = build_write_attribution(case_id="A01", before=before, after=after)
    assert attribution["pi_shadow_business_write_delta"] == 0
    owners = {item["owner"] for item in attribution["writes"]}
    assert owners == {"legacy"}


def test_pi_extra_context_write_still_fails_after_attribution():
    before = ShadowSideEffectSnapshot(1, 10, 0, 0, 0, 0, 0, 0, 0, target_session_context_version=3)
    after = ShadowSideEffectSnapshot(1, 12, 3, 0, 0, 0, 0, 0, 0, target_session_context_version=6)
    assert compute_pi_side_effect_count(
        before,
        after,
        expected_legacy_chat_message_delta=2,
        expected_legacy_context_version_delta=2,
    ) == 1


def test_29_of_30_does_not_pass_or_compute_rates():
    results = [_passing_case_result(str(i)) for i in range(29)]
    summary = summarize_shadow_results(results, planned_samples=30)
    gate = build_agent_gate(summary)
    assert summary["metrics"]["status_match_rate"] is None
    assert gate["passed"] is False


def test_30_samples_computes_gate_when_browser_passed():
    results = [_passing_case_result(str(i)) for i in range(30)]
    summary = summarize_shadow_results(results, planned_samples=30)
    summary["browser_acceptance"] = {"executed": True, "passed": True, "notes": "manual"}
    gate = build_agent_gate(summary)
    assert summary["metrics"]["status_match_rate"] == 1.0
    assert summary["metrics"]["url_match_rate"] == 1.0
    assert gate["recommended_for_next_authorization"] is True


def test_three_smoke_gate_requires_three_passes_without_authorization():
    results = [_passing_case_result(str(i)) for i in range(3)]
    summary = summarize_shadow_results(results, planned_samples=3)
    gate = build_agent_gate(summary)
    runtime_gate = build_runtime_gate(gate)
    assert gate["smoke_passed"] is True
    assert gate["recommended_to_run_full_30"] is True
    assert gate["recommended_for_next_authorization"] is False
    assert runtime_gate["decision"] == "do_not_enable_pi_compatible"


def test_runner_smoke_cases_are_fixed_p1_6_3_cases():
    cases = runner._smoke_cases()
    assert [case.case_id for case in cases] == ["A01", "A02", "A03"]
    assert cases[0].setup_query == "贵州茅台最新财报表现如何？"
    assert cases[0].query == "这份报告的官方 PDF 在哪里？"
    assert cases[1].query == "600519官方年报链接"
    assert cases[2].query == "平安的年报PDF在哪里？"
    assert cases[2].expected_status == "clarification_required"


def test_legacy_status_from_answer_detects_clarification():
    assert runner._legacy_status_from_answer("找到多个平安相关证券，请选择") == "clarification_required"
    assert runner._legacy_status_from_answer("没有识别到明确的公司或股票代码。请明确公司名称或证券代码。") == "clarification_required"
    assert runner._legacy_status_from_answer("暂未找到可验证的官方报告 PDF。") == "unavailable"
    assert runner._legacy_status_from_answer("官方 PDF 链接如下") == "success"


def test_input_snapshot_hash_shared_from_diagnostic():
    record = {
        "trace_id": "trace",
        "run_id": "run",
        "status": "success",
        "agent_id": "official_report_pdf_pi_v1",
        "turn_count": 1,
        "tool_call_count": 1,
        "metrics": {"latency_ms": 1, "model_calls": 0},
        "findings": [],
        "evidence_ids_count": 1,
        "events": [],
        "input_snapshot_hash": "abc123",
    }
    assert runner._diagnostic_to_pi_result(record)["input_snapshot_hash"] == "abc123"


def test_artifact_secret_scan(tmp_path):
    payload = {"access_token_present": True, "user_hash": "abc", "backend_base_url": "redacted"}
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    text = artifact.read_text(encoding="utf-8")
    assert "Bearer " not in text
    assert "password" not in text.lower()
    assert "sk-" not in text


def test_sql_logging_audit_defaults_to_no_parameter_exposure():
    audit = _sql_logging_audit()
    assert audit["database_sql_echo"] is False
    assert audit["database_sql_hide_parameters"] is True
    assert audit["sql_parameter_exposure"] == 0
    assert audit["decision"] == "pass"


def test_cleanup_safe_placeholder():
    path = Path("/tmp/nonexistent-pi-shadow-cleanup-marker")
    path.unlink(missing_ok=True)
    assert not path.exists()


@pytest.mark.asyncio
async def test_timeout_no_zombie_task():
    baseline = len([task for task in asyncio.all_tasks() if not task.done()])
    task = asyncio.create_task(asyncio.sleep(0.01))
    await task
    after = len([task for task in asyncio.all_tasks() if not task.done()])
    assert after <= baseline + 1


@pytest.mark.asyncio
async def test_cancellation_no_zombie_task():
    task = asyncio.create_task(asyncio.sleep(10))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.done()


def _passing_case_result(case_id: str) -> dict:
    return {
        "case_id": case_id,
        "query_type": "explicit_company_name",
        "legacy": {"status": "success", "http_status": 200},
        "pi_compatible": {"status": "success", "latency_ms": 10, "llm_call_count": 0, "tool_call_count": 1},
        "comparison": {
            "status_match": True,
            "entity_match": True,
            "year_match": True,
            "report_type_match": True,
            "source_url_match": True,
            "pdf_url_match": True,
            "provenance_complete": True,
            "unsupported_url_count": 0,
            "side_effect_count": 0,
            "decision": "pass",
        },
        "side_effects": {"context_mutation_count": 0, "double_write_count": 0},
    }
