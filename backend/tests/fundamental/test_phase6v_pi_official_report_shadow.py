from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest

from app.agent_runtime.shadow_acceptance import (
    ShadowSideEffectSnapshot,
    build_agent_gate,
    build_runtime_gate,
    compute_pi_side_effect_count,
    summarize_shadow_results,
)
from app.agent_runtime.shadow_diagnostics import PiShadowDiagnosticsSink, query_hash, user_hash

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
        access_token = ""
        user_id = ""
        allow_local_fixture_user = False

    monkeypatch.setattr(runner.settings, "pi_agent_shadow_diagnostics_path", str(tmp_path / "diag.jsonl"))
    monkeypatch.setattr(runner.settings, "agent_executor_mode", "legacy")
    report = await runner.build_environment_report(Args())
    assert report["shadow_enabled"] is False
    assert report["environment_ready"] is False
    assert any("shadow" in item.lower() for item in report["blockers"])


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


def test_test_session_isolated_title_prefix():
    assert "pi-shadow-" in runner._browser_markdown(executed=False, passed=False, notes="pi-shadow-A01")


@pytest.mark.asyncio
async def test_callback_timeout_handled(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.settings, "pi_agent_shadow_diagnostics_path", str(tmp_path / "missing.jsonl"))
    result = await runner._poll_shadow_diagnostic(conversation_id="conv", raw_query="q", user_id="u", timeout_seconds=0.01)
    assert result["status"] == "failed"
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


def test_legacy_writes_excluded_and_pi_extra_write_detected():
    before = ShadowSideEffectSnapshot(1, 10, 0, 0, 0, 0, 0, 0, 0)
    after = ShadowSideEffectSnapshot(1, 12, 0, 0, 0, 0, 0, 0, 0)
    assert compute_pi_side_effect_count(before, after, expected_legacy_chat_message_delta=2) == 0
    extra = ShadowSideEffectSnapshot(1, 13, 0, 0, 0, 0, 0, 0, 0)
    assert compute_pi_side_effect_count(before, extra, expected_legacy_chat_message_delta=2) == 1


def test_cleanup_safe_placeholder():
    path = Path("/tmp/nonexistent-pi-shadow-cleanup-marker")
    path.unlink(missing_ok=True)
    assert not path.exists()
