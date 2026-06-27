"""
C27 — Data Quality Card + Source Attribution
Tests for answer_metadata.py and schemas.py C27 extensions.
"""

import pytest

from app.agents.schemas import DataQuality, SourceRef
from app.agents.answer_metadata import (
    compute_data_quality,
    build_source_refs,
    build_answer_metadata,
    add_data_boundary_declaration,
    TOOL_SOURCE_MAP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ev(name: str, status: str = "success", detail: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail}


# ---------------------------------------------------------------------------
# C27.1  DataQuality schema
# ---------------------------------------------------------------------------

class TestDataQualitySchema:
    def test_default_level_is_insufficient(self):
        dq = DataQuality()
        assert dq.level == "insufficient"

    def test_new_fields_present(self):
        dq = DataQuality(
            level="high",
            reason="good",
            verified_data=["实时行情"],
            missing_data=["财务数据"],
            failed_tools=["官方财报检索"],
            stale_data=[],
            source_count=2,
            tool_count=3,
            warning_flags=["部分关键数据工具获取失败"],
        )
        assert dq.level == "high"
        assert dq.source_count == 2

    def test_backward_compat_fields_still_present(self):
        dq = DataQuality(report_verified=True, market_data_available=True)
        assert dq.report_verified is True
        assert dq.market_data_available is True

    def test_model_dump_includes_new_fields(self):
        dq = DataQuality(level="medium", source_count=1)
        d = dq.model_dump()
        assert "level" in d
        assert "source_count" in d
        assert d["level"] == "medium"


# ---------------------------------------------------------------------------
# C27.2  SourceRef schema
# ---------------------------------------------------------------------------

class TestSourceRefSchema:
    def test_new_fields_present(self):
        src = SourceRef(
            title="实时行情",
            source_type="market_quote",
            confidence="high",
            id="abc-123",
            provider="AkShare",
        )
        assert src.confidence == "high"
        assert src.id == "abc-123"
        assert src.provider == "AkShare"

    def test_default_confidence_is_medium(self):
        src = SourceRef(title="test")
        assert src.confidence == "medium"

    def test_backward_compat_title_still_required(self):
        src = SourceRef(title="news", source_type="news")
        assert src.title == "news"

    def test_snippet_and_supports_optional(self):
        src = SourceRef(title="rag doc", snippet="text...", supports=["dividend"])
        assert src.snippet == "text..."
        assert src.supports == ["dividend"]


# ---------------------------------------------------------------------------
# C27.2  compute_data_quality — level rules
# ---------------------------------------------------------------------------

class TestComputeDataQuality:
    def test_no_tools_is_insufficient(self):
        dq = compute_data_quality([])
        assert dq.level == "insufficient"

    def test_all_failed_is_insufficient(self):
        events = [
            _ev("get_stock_quote_tool", "error"),
            _ev("get_latest_news_tool", "error"),
        ]
        dq = compute_data_quality(events)
        assert dq.level == "insufficient"

    def test_only_market_quote_is_low(self):
        events = [_ev("get_stock_quote_tool")]
        dq = compute_data_quality(events)
        assert dq.level == "low"

    def test_only_news_is_low(self):
        events = [_ev("get_latest_news_tool")]
        dq = compute_data_quality(events)
        assert dq.level == "low"

    def test_news_and_quote_no_financial_is_low(self):
        events = [
            _ev("get_stock_quote_tool"),
            _ev("get_latest_news_tool"),
        ]
        dq = compute_data_quality(events)
        assert dq.level == "low"

    def test_report_success_is_at_least_medium(self):
        events = [_ev("get_recent_reports_tool")]
        dq = compute_data_quality(events)
        assert dq.level in ("medium", "high")

    def test_report_plus_quote_high(self):
        events = [
            _ev("get_recent_reports_tool"),
            _ev("get_stock_quote_tool"),
        ]
        dq = compute_data_quality(events)
        assert dq.level == "high"

    def test_financial_report_plus_quote_is_high(self):
        events = [
            _ev("get_fundamental_data_tool"),
            _ev("get_stock_quote_tool"),
        ]
        dq = compute_data_quality(events)
        assert dq.level == "high"

    def test_failed_critical_tool_lowers_level(self):
        events = [
            _ev("get_stock_quote_tool"),          # success
            _ev("official_report_search", "error"),  # critical failure
        ]
        dq = compute_data_quality(events)
        # critical failure → warning_flag, level should not be high
        assert "部分关键数据工具获取失败" in dq.warning_flags
        assert dq.level != "high"

    def test_verified_data_populated(self):
        events = [_ev("get_stock_quote_tool"), _ev("get_latest_news_tool")]
        dq = compute_data_quality(events)
        assert len(dq.verified_data) > 0

    def test_failed_tools_in_missing_data(self):
        events = [
            _ev("get_stock_quote_tool"),
            _ev("official_report_search", "error"),
        ]
        dq = compute_data_quality(events)
        assert len(dq.failed_tools) > 0

    def test_backward_compat_market_data_available(self):
        events = [_ev("get_stock_quote_tool")]
        dq = compute_data_quality(events)
        assert dq.market_data_available is True

    def test_backward_compat_report_verified(self):
        events = [_ev("get_recent_reports_tool")]
        dq = compute_data_quality(events)
        assert dq.report_verified is True

    def test_insufficient_has_reason(self):
        dq = compute_data_quality([])
        assert len(dq.reason) > 0

    def test_high_has_reason(self):
        events = [_ev("get_fundamental_data_tool"), _ev("get_stock_quote_tool")]
        dq = compute_data_quality(events)
        assert len(dq.reason) > 0


# ---------------------------------------------------------------------------
# C27.2  build_source_refs
# ---------------------------------------------------------------------------

class TestBuildSourceRefs:
    def test_failed_tool_no_source(self):
        events = [_ev("get_stock_quote_tool", "error")]
        refs = build_source_refs(events)
        assert len(refs) == 0

    def test_success_tool_creates_source(self):
        events = [_ev("get_stock_quote_tool")]
        refs = build_source_refs(events)
        assert len(refs) == 1
        assert refs[0].source_type == "market_quote"

    def test_market_quote_confidence_high(self):
        events = [_ev("get_stock_quote_tool")]
        refs = build_source_refs(events)
        assert refs[0].confidence == "high"

    def test_news_confidence_low(self):
        events = [_ev("get_latest_news_tool")]
        refs = build_source_refs(events)
        assert refs[0].confidence == "low"

    def test_news_snippet_title_only(self):
        events = [_ev("get_latest_news_tool")]
        refs = build_source_refs(events)
        assert refs[0].snippet == "仅标题，需进一步核验"

    def test_official_report_confidence_high(self):
        events = [_ev("official_report_search")]
        refs = build_source_refs(events)
        assert refs[0].confidence == "high"

    def test_historical_report_confidence_high(self):
        events = [_ev("get_report_detail_tool")]
        refs = build_source_refs(events)
        assert refs[0].confidence == "high"

    def test_dedup_same_tool_called_twice(self):
        events = [_ev("get_stock_quote_tool"), _ev("get_stock_quote_tool")]
        refs = build_source_refs(events)
        assert len(refs) == 1

    def test_rag_results_appended(self):
        events = []
        rag = [{"title": "茅台年报", "source": "SZEX", "content": "..."}]
        refs = build_source_refs(events, rag_results=rag)
        assert len(refs) == 1
        assert refs[0].source_type == "rag"

    def test_report_results_appended(self):
        events = []
        reports = [{"stock_name": "贵州茅台", "created_at": "2026-06-01"}]
        refs = build_source_refs(events, report_results=reports)
        assert len(refs) == 1
        assert refs[0].source_type == "historical_report"
        assert refs[0].confidence == "high"

    def test_source_has_id(self):
        events = [_ev("get_stock_quote_tool")]
        refs = build_source_refs(events)
        assert refs[0].id != ""


# ---------------------------------------------------------------------------
# C27.3  build_answer_metadata
# ---------------------------------------------------------------------------

class TestBuildAnswerMetadata:
    def test_returns_data_quality_and_sources(self):
        events = [_ev("get_stock_quote_tool")]
        meta = build_answer_metadata(events)
        assert "data_quality" in meta
        assert "sources" in meta

    def test_data_quality_is_dict(self):
        meta = build_answer_metadata([_ev("get_stock_quote_tool")])
        assert isinstance(meta["data_quality"], dict)
        assert "level" in meta["data_quality"]

    def test_sources_is_list(self):
        meta = build_answer_metadata([_ev("get_stock_quote_tool")])
        assert isinstance(meta["sources"], list)

    def test_existing_dq_medium_preserved(self):
        events = [_ev("get_stock_quote_tool")]
        existing = DataQuality(level="medium", reason="partial data")
        meta = build_answer_metadata(events, existing_dq=existing)
        assert meta["data_quality"]["level"] == "medium"
        assert meta["data_quality"]["reason"] == "partial data"

    def test_existing_dq_insufficient_overridden(self):
        # If existing is insufficient, let the computed one win
        events = [_ev("get_fundamental_data_tool"), _ev("get_stock_quote_tool")]
        existing = DataQuality(level="insufficient")
        meta = build_answer_metadata(events, existing_dq=existing)
        # computed should be high → override the insufficient
        assert meta["data_quality"]["level"] != "insufficient"


# ---------------------------------------------------------------------------
# C27.6  add_data_boundary_declaration
# ---------------------------------------------------------------------------

class TestAddDataBoundaryDeclaration:
    def test_high_no_change(self):
        answer = "分析内容。"
        dq = DataQuality(level="high")
        out = add_data_boundary_declaration(answer, dq)
        assert out == answer

    def test_low_prefix_added(self):
        answer = "分析内容。"
        dq = DataQuality(level="low")
        out = add_data_boundary_declaration(answer, dq)
        assert "本次数据有限" in out
        assert out.startswith("本次数据有限")

    def test_insufficient_prefix_added(self):
        answer = "分析内容。"
        dq = DataQuality(level="insufficient")
        out = add_data_boundary_declaration(answer, dq)
        assert "当前数据不足" in out

    def test_medium_prefix_added(self):
        answer = "分析内容。"
        dq = DataQuality(level="medium")
        out = add_data_boundary_declaration(answer, dq)
        assert "本次数据部分完整" in out

    def test_idempotent_low(self):
        answer = "本次数据有限，以下仅能作为初步参考。\n\n分析内容。"
        dq = DataQuality(level="low")
        out = add_data_boundary_declaration(answer, dq)
        assert out.count("本次数据有限") == 1

    def test_dict_dq_supported(self):
        dq_dict = {"level": "low"}
        out = add_data_boundary_declaration("分析内容。", dq_dict)
        assert "本次数据有限" in out

    def test_empty_answer_passthrough(self):
        out = add_data_boundary_declaration("", DataQuality(level="low"))
        assert out == ""
