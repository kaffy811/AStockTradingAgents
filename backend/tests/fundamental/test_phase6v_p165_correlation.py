"""Phase 6V-P1.6.5 — shadow correlation, diagnostics storage, write attribution,
status taxonomy, clarification denominator and provenance regression tests."""
from __future__ import annotations

import json

import pytest

from app.agent_runtime.shadow_correlation import parse_correlation_header
from app.agent_runtime.shadow_diagnostics import PiShadowDiagnosticsSink, record_checksum
from app.agent_runtime.shadow_runner import PiCompatibleShadowRunner
from app.agent_runtime.shadow_taxonomy import (
    assess_safety_correctness,
    clarification_applicable,
    clarification_correct,
    classify_deadline,
    normalize_status,
    pdf_urls_semantically_equal,
    status_specific_provenance_complete,
)
from app.agent_runtime.shadow_write_attribution import (
    ObservedMessageRow,
    ObservedSessionRow,
    assistant_logical_response_id,
    attribute_turn_writes,
    parse_case_marker,
)


# ── Diagnostics storage (items 1-3, 8-11) ─────────────────────────────────────


@pytest.fixture()
def sink(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "pi_agent_shadow_diagnostics_path", str(tmp_path / "diag.jsonl"))
    return PiShadowDiagnosticsSink()


def _result(run_id: str, status: str = "success", trace_id: str = "trace_x") -> dict:
    return {
        "trace_id": trace_id,
        "run_id": run_id,
        "status": status,
        "agent_id": "official_report_pdf_pi_v1",
        "metrics": {"latency_ms": 1, "model_calls": 0, "tool_calls": 0},
        "findings": [],
        "events": [],
        "evidence_ids": [],
        "shadow_input": {"conversation_id": "conv"},
    }


def test_setup_and_followup_records_are_isolated_by_run_id(sink):
    """Items 1+2: setup diagnostics cannot be consumed by the follow-up turn and
    the follow-up cannot overwrite the setup record."""
    sink.record(raw_query="setup q", conversation_id="conv1", user_id="u", result=_result("run_setup", "skipped"))
    sink.record(raw_query="follow q", conversation_id="conv1", user_id="u", result=_result("run_follow", "success"))
    setup = sink.read_run("run_setup")
    follow = sink.read_run("run_follow")
    assert setup["status"] == "skipped" and setup["run_id"] == "run_setup"
    assert follow["status"] == "success" and follow["run_id"] == "run_follow"


def test_late_terminal_from_previous_case_not_consumed_by_next_case(sink):
    """Item 3: a late terminal for run A never satisfies a reader waiting on run B."""
    sink.record(raw_query="q1", conversation_id="conv_a", user_id="u", result=_result("run_a"))
    assert sink.read_run("run_b") is None


def test_retry_uses_new_shadow_run_id_and_both_records_kept(sink):
    """Item 4: each retry attempt gets its own run file."""
    sink.record(raw_query="q", conversation_id="conv", user_id="u", result=_result("run_attempt1", "failed"))
    sink.record(raw_query="q", conversation_id="conv", user_id="u", result=_result("run_attempt2", "success"))
    assert sink.read_run("run_attempt1")["status"] == "failed"
    assert sink.read_run("run_attempt2")["status"] == "success"


def test_same_query_different_case_not_confused(sink):
    """Item 5: identical query text in two cases resolves by run id, not query hash."""
    sink.record(raw_query="same query", conversation_id="c1", user_id="u", result=_result("run_case1", "success"))
    sink.record(raw_query="same query", conversation_id="c2", user_id="u", result=_result("run_case2", "unavailable"))
    assert sink.read_run("run_case1")["status"] == "success"
    assert sink.read_run("run_case2")["status"] == "unavailable"


def test_multi_turn_same_session_distinguished_by_correlation_turn_id(sink):
    """Item 6: two turns in one session carry distinct turn ids in correlation."""
    sink.record(
        raw_query="t1", conversation_id="conv", user_id="u", result=_result("run_t1"),
        correlation={"turn_id": "A01.a1.t1", "case_id": "A01"},
    )
    sink.record(
        raw_query="t2", conversation_id="conv", user_id="u", result=_result("run_t2"),
        correlation={"turn_id": "A01.a1.t2", "case_id": "A01"},
    )
    assert sink.read_run("run_t1")["correlation"]["turn_id"] == "A01.a1.t1"
    assert sink.read_run("run_t2")["correlation"]["turn_id"] == "A01.a1.t2"


def test_concurrent_cases_isolated_by_acceptance_run_id(sink):
    """Item 7: records from two acceptance runs remain separately addressable."""
    sink.record(
        raw_query="q", conversation_id="c1", user_id="u", result=_result("run_x"),
        correlation={"acceptance_run_id": "acc_1", "case_id": "B01"},
    )
    sink.record(
        raw_query="q", conversation_id="c2", user_id="u", result=_result("run_y"),
        correlation={"acceptance_run_id": "acc_2", "case_id": "B01"},
    )
    assert sink.read_run("run_x")["correlation"]["acceptance_run_id"] == "acc_1"
    assert sink.read_run("run_y")["correlation"]["acceptance_run_id"] == "acc_2"


def test_diagnostics_run_file_written_atomically_no_tmp_left(sink, tmp_path):
    """Item 8: per-run record is written via tmp+rename, no partial files remain."""
    sink.record(raw_query="q", conversation_id="c", user_id="u", result=_result("run_atomic"))
    runs_dir = sink.runs_dir()
    leftover = [p for p in runs_dir.iterdir() if p.name.endswith(".tmp")]
    assert leftover == []
    assert json.loads((runs_dir / "run_atomic.json").read_text())["terminal"] is True


def test_terminal_exactly_once_and_core_immutable_after_terminal(sink):
    """Items 9+10: a second terminal for the same run cannot change the record."""
    sink.record(raw_query="q", conversation_id="c", user_id="u", result=_result("run_once", "success"))
    sink.record(raw_query="q", conversation_id="c", user_id="u", result=_result("run_once", "failed"))
    record = sink.read_run("run_once")
    assert record["status"] == "success"
    assert record["terminal_sequence"] == 1
    assert record["checksum"] == record_checksum(record)


def test_stale_terminal_marked_ignored_in_jsonl(sink):
    """Item 11: the stale write is preserved in JSONL flagged stale_terminal_ignored."""
    sink.record(raw_query="q", conversation_id="c", user_id="u", result=_result("run_stale", "success"))
    sink.record(raw_query="q", conversation_id="c", user_id="u", result=_result("run_stale", "failed"))
    lines = [json.loads(line) for line in sink.path().read_text().splitlines()]
    assert lines[0].get("stale_terminal_ignored") is None
    assert lines[1].get("stale_terminal_ignored") is True


# ── Write attribution (items 12-17) ───────────────────────────────────────────


def _correlation(turn: str = "B01.a1.t1") -> dict:
    return {
        "acceptance_run_id": "acc",
        "case_id": "B01",
        "case_attempt": 1,
        "turn_id": turn,
        "request_trace_id": "trace_1",
        "legacy_run_id": "msg_1",
        "shadow_run_id": "run_1",
    }


def test_writes_attributed_by_owner_and_pi_delta_zero_for_legacy_pair():
    """Item 12: expected user+assistant rows are legacy; Pi delta stays 0."""
    attribution = attribute_turn_writes(
        case_id="B01",
        correlation=_correlation(),
        target_session_id="sess_t",
        new_messages=[
            ObservedMessageRow("m1", "sess_t", "user", "2026-07-19T00:00:01"),
            ObservedMessageRow("m2", "sess_t", "assistant", "2026-07-19T00:00:02"),
        ],
        new_sessions=[],
        acceptance_session_ids={"sess_t"},
    )
    assert attribution.pi_business_write_delta == 0
    assert attribution.legacy_write_count == 2
    assert attribution.unknown_owner_write_count == 0


def test_other_case_writes_not_counted_into_pi_delta():
    """Item 13: rows from another case's session are other_case, not Pi."""
    attribution = attribute_turn_writes(
        case_id="B01",
        correlation=_correlation(),
        target_session_id="sess_t",
        new_messages=[
            ObservedMessageRow("m1", "sess_t", "user", "2026-07-19T00:00:01"),
            ObservedMessageRow("m2", "sess_t", "assistant", "2026-07-19T00:00:02"),
            ObservedMessageRow("m3", "sess_other", "user", "2026-07-19T00:00:03"),
            ObservedMessageRow("m4", "sess_other", "assistant", "2026-07-19T00:00:04"),
        ],
        new_sessions=[ObservedSessionRow("sess_other", "B02", "2026-07-19T00:00:00")],
        acceptance_session_ids={"sess_t", "sess_other"},
    )
    assert attribution.pi_business_write_delta == 0
    assert attribution.other_case_write_count == 3
    assert attribution.assistant_double_write_count == 0
    assert attribution.unknown_owner_write_count == 0


def test_setup_followup_assistant_pair_not_double_write():
    """Item 14: one assistant message per turn across two turns is not a duplicate."""
    for turn in ("A01.a1.t1", "A01.a1.t2"):
        attribution = attribute_turn_writes(
            case_id="A01",
            correlation=_correlation(turn),
            target_session_id="sess_t",
            new_messages=[
                ObservedMessageRow(f"{turn}-u", "sess_t", "user", "2026-07-19T00:00:01"),
                ObservedMessageRow(f"{turn}-a", "sess_t", "assistant", "2026-07-19T00:00:02"),
            ],
            new_sessions=[],
            acceptance_session_ids={"sess_t"},
        )
        assert attribution.assistant_double_write_count == 0


def test_retry_message_has_distinct_logical_response_id():
    """Item 15: a retry attempt is a different logical response."""
    first = assistant_logical_response_id("sess", "B01.a1.t1")
    retry = assistant_logical_response_id("sess", "B01.a2.t1")
    assert first != retry


def test_true_duplicate_assistant_write_detected_and_fails_ownership():
    """Items 16+17: a second assistant row in the same turn is a true duplicate
    and counts as unknown-owner (Gate-failing), never silently excluded."""
    attribution = attribute_turn_writes(
        case_id="B01",
        correlation=_correlation(),
        target_session_id="sess_t",
        new_messages=[
            ObservedMessageRow("m1", "sess_t", "user", "2026-07-19T00:00:01"),
            ObservedMessageRow("m2", "sess_t", "assistant", "2026-07-19T00:00:02"),
            ObservedMessageRow("m3", "sess_t", "assistant", "2026-07-19T00:00:03"),
        ],
        new_sessions=[],
        acceptance_session_ids={"sess_t"},
    )
    assert attribution.assistant_double_write_count == 1
    assert attribution.unknown_owner_write_count == 1
    duplicate = [w for w in attribution.writes if w.get("classification") == "true_duplicate_assistant_write"]
    assert duplicate and duplicate[0]["owner"] == "unknown"


def test_foreign_session_write_is_unknown_owner():
    """Item 17 (continued): unattributable rows are unknown, not excluded."""
    attribution = attribute_turn_writes(
        case_id="B01",
        correlation=_correlation(),
        target_session_id="sess_t",
        new_messages=[ObservedMessageRow("mx", "sess_foreign", "assistant", "2026-07-19T00:00:09")],
        new_sessions=[],
        acceptance_session_ids={"sess_t"},
    )
    assert attribution.unknown_owner_write_count == 1


def test_pi_shadow_write_forbidden_at_tool_boundary():
    """Item 16: a non-read-only tool is rejected with PI_SHADOW_WRITE_FORBIDDEN."""
    import asyncio

    from app.agent_runtime.contracts import PiToolCall, PiToolDefinition
    from app.agent_runtime.tool_adapter import PiFinancialToolAdapter

    adapter = PiFinancialToolAdapter(registry=object())
    adapter._definitions["mutate_things"] = PiToolDefinition(
        name="mutate_things",
        description="forbidden write tool",
        input_schema={"type": "object", "properties": {}},
        mode="write",
    )
    response = asyncio.run(
        adapter.execute(
            PiToolCall(id="tc1", name="mutate_things", arguments={}),
            trace_id="trace",
            context=None,
            allowed_tools={"mutate_things"},
        )
    )
    assert response.error_code == "PI_SHADOW_WRITE_FORBIDDEN"


# ── Status taxonomy / clarification / provenance (items 18-24) ────────────────


def test_status_taxonomy_normalization():
    """Item 18: timeout/unsupported/skipped are never conflated."""
    assert normalize_status("failed", "AGENT_DEADLINE_EXCEEDED") == "timeout"
    assert normalize_status("unavailable", "REPORT_TYPE_UNSUPPORTED") == "unsupported"
    assert normalize_status("skipped", "PI_SHADOW_INTENT_NOT_SUPPORTED") == "skipped"
    assert normalize_status("unavailable", "REPORT_NOT_FOUND") == "unavailable"
    assert normalize_status("clarification_required", None) == "clarification_required"
    assert normalize_status("success", None) == "success"
    assert normalize_status("cancelled", None) == "cancelled"
    assert normalize_status("weird", None) == "failed"
    # failed no longer wildcard-matches anything
    assert normalize_status("failed", None) == "failed"


def test_safety_correctness_for_safe_refusal():
    assert assess_safety_correctness(normalized_pi_status="unavailable", pi_pdf_url=None, expected_status=None)
    assert not assess_safety_correctness(normalized_pi_status="success", pi_pdf_url="https://x/pdf", expected_status="unavailable")


def test_clarification_denominator_only_ambiguity_cases():
    """Item 19: the denominator is the applicable subset, never all 30."""
    assert clarification_applicable("ambiguity", None)
    assert clarification_applicable("explicit_company_name", "clarification_required")
    assert not clarification_applicable("explicit_company_name", None)
    assert not clarification_applicable("missing", "unavailable")


def test_clarification_correct_requires_candidates_and_no_url():
    ok, reasons = clarification_correct(
        normalized_pi_status="clarification_required",
        clarification_options=[{"market": "CN", "symbol": "000001"}, {"market": "CN", "symbol": "601318"}],
        pi_pdf_url=None,
        pi_tool_call_count=0,
    )
    assert ok and not reasons
    bad, bad_reasons = clarification_correct(
        normalized_pi_status="unavailable",
        clarification_options=[{"market": "CN", "symbol": "000001"}],
        pi_pdf_url=None,
        pi_tool_call_count=0,
    )
    assert not bad and any("not_clarification_required" in reason for reason in bad_reasons)


def test_status_specific_provenance_schemas():
    """Item 20: completeness schema depends on terminal status."""
    ok, missing = status_specific_provenance_complete(
        normalized_status="success",
        findings=[{
            "symbol": "600519", "report_type": "annual", "report_year": 2025,
            "pdf_url": "https://static.cninfo.com.cn/x.PDF", "official_domain_verified": True,
        }],
        structured_answer={},
        evidence_ids=["official_report:600519:2025"],
        error_code=None,
        pdf_url="https://static.cninfo.com.cn/x.PDF",
    )
    assert ok, missing
    # unavailable without pdf_url is complete when a reason exists
    ok2, _ = status_specific_provenance_complete(
        normalized_status="unavailable",
        findings=[],
        structured_answer={"reason_code": "REPORT_NOT_FOUND"},
        evidence_ids=[],
        error_code="REPORT_NOT_FOUND",
        pdf_url=None,
    )
    assert ok2
    # skipped requires an explicit reason code
    ok3, missing3 = status_specific_provenance_complete(
        normalized_status="skipped",
        findings=[],
        structured_answer={},
        evidence_ids=[],
        error_code=None,
        pdf_url=None,
    )
    assert not ok3 and "reason_code" in missing3


def test_expected_timeout_not_counted_as_unexpected():
    """Item 21+22: manifest-expected timeout is expected; others are unexpected."""
    assert classify_deadline(normalized_pi_status="timeout", expected_status="timeout") == "expected_timeout"
    assert classify_deadline(normalized_pi_status="timeout", expected_status="unavailable") == "unexpected_timeout"
    assert classify_deadline(normalized_pi_status="unavailable", expected_status=None) == "none"


def test_pdf_url_semantic_normalization():
    """Item 23: scheme/tracking-param differences on the same document normalize equal."""
    assert pdf_urls_semantically_equal(
        "http://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF?utm_source=x",
        "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
    ) is True


def test_different_official_documents_never_normalized_equal():
    """Item 24: distinct official documents must stay different (B02 root cause)."""
    assert pdf_urls_semantically_equal(
        "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
        "https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF",
    ) is False


# ── Correlation propagation / runner behavior ─────────────────────────────────


def test_correlation_header_parse_whitelist_and_limits():
    raw = json.dumps({
        "acceptance_run_id": "acc_1",
        "case_id": "A01",
        "case_attempt": 2,
        "turn_id": "A01.a2.t1",
        "request_trace_id": "trace_1",
        "shadow_run_id": "run_1",
        "input_snapshot_hash": "h" * 200,
        "evil_field": "x",
    })
    envelope = parse_correlation_header(raw)
    assert envelope["case_attempt"] == 2
    assert "evil_field" not in envelope
    assert len(envelope["input_snapshot_hash"]) <= 80
    assert parse_correlation_header("not json") == {}


def test_skip_result_carries_run_id():
    """P1.6.4 root cause RC-B: skipped shadows must keep a run identity."""
    runner = PiCompatibleShadowRunner()
    result = runner._skip_result(
        trace_id="trace_1",
        run_id="run_supplied",
        reason_code="PI_SHADOW_INTENT_NOT_SUPPORTED",
        detected_intent="other",
        normalized_intent="other",
        input_snapshot={},
    )
    assert result["run_id"] == "run_supplied"
    fallback = runner._skip_result(
        trace_id="trace_1",
        reason_code="PI_SHADOW_INTENT_NOT_SUPPORTED",
        detected_intent="other",
        normalized_intent="other",
        input_snapshot={},
    )
    assert fallback["run_id"]


def test_intent_regex_covers_p164_skipped_queries():
    """C04/C05/D01-D05/F05/F07 queries must now be recognized as official-pdf intent."""
    runner = PiCompatibleShadowRunner()
    for query in (
        "601318 2025年年报PDF",
        "000001 2024年度报告PDF",
        "贵州茅台2025年中报PDF",
        "五粮液2025年一季报PDF",
        "招商银行2025年一季报原文",
        "000858 1900年度报告PDF",
        "RAG不可用时贵州茅台2024年官方年报PDF",
    ):
        assert runner._looks_like_official_pdf_intent(query), query


def test_alias_not_ambiguous_when_longer_name_present():
    """B04/B05/B06 root cause: embedded alias must not trigger clarification."""
    runner = PiCompatibleShadowRunner()
    assert runner._ambiguous_alias_options("中国平安2025年年度报告PDF链接") == []
    assert runner._ambiguous_alias_options("平安银行2024年年报PDF在哪里？") == []
    assert runner._ambiguous_alias_options("招商银行2025年年度报告原文") == []
    # bare alias still clarifies
    assert runner._ambiguous_alias_options("平安的年报PDF在哪里？")
    assert runner._ambiguous_alias_options("茅台的年报PDF在哪里？")


def test_session_case_marker_parse():
    assert parse_case_marker("pi-shadow-B02") == "B02"
    assert parse_case_marker("普通标题") is None
