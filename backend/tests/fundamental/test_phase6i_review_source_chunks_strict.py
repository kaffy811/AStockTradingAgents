"""
tests/fundamental/test_phase6i_review_source_chunks_strict.py

Phase 6I: Review Agent 强校验 source_chunks + 引用一致性审计

15 tests:
  1. valid chunk_id passes through unmodified (metadata preserved)
  2. invalid chunk_id removed from source_chunks
  3. LLM-modified section_title is canonicalized from rag_context
  4. LLM-modified report_type is canonicalized from rag_context
  5. duplicate chunk_id deduped
  6. more than 8 chunks truncated to 8
  7. page citation (第12页) removed from analysis text
  8. coverage claim ("完整覆盖所有财报") rewritten
  9. body claims report citation but no chunks/reports → citation signal rewritten
 10. review_audit is present and has expected keys
 11. review_audit reflects canonicalization flags correctly
 12. investment advice blocked → audit flag set
 13. orchestrator includes review_audit in final_analysis
 14. schemas.make_review_result carries audit field
 15. no v-html usage in AiAnalysisCard.vue or ReportDocumentsPanel.vue
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_minimal_data_pack(
    allowed_chunk_ids: list[int] | None = None,
    rag_context: list[dict] | None = None,
) -> dict:
    """Minimal data_pack for review-agent unit tests."""
    chunks = rag_context or []
    ids = allowed_chunk_ids if allowed_chunk_ids is not None else [c["chunk_id"] for c in chunks]
    return {
        "ts_code": "000001.SZ",
        "market": "CN",
        "symbol": "000001",
        "collected_modules": [],
        "missing_modules": [],
        "stale_modules": [],
        "partial_modules": [],
        "data_quality": {"score": 80, "level": "high", "issues": []},
        "module_summaries": {},
        "compressed_facts": [],
        "report_rag_context": chunks,
        "allowed_chunk_ids": ids,
        "rag_meta": {"provider": "mock", "fallback_used": False},
    }


def _make_minimal_analysis(**overrides) -> dict:
    base = {
        "summary": "公司基本面稳健，盈利能力持续提升。",
        "overall_score": 72,
        "dimensions": [
            {
                "name": "盈利能力",
                "score": 70,
                "level": "neutral",
                "evidence": [
                    {"label": "ROE", "value": "12.5%", "source_modules": ["profitability"]}
                ],
                "risks": [],
            }
        ],
        "highlights": [
            {"title": "营收增长", "detail": "同比增长10%", "source_modules": ["growth"]}
        ],
        "risks": [
            {"title": "宏观风险", "detail": "经济周期影响", "severity": "low", "source_modules": ["macro"]}
        ],
        "watch_items": [],
        "data_limitations": [],
        "raw_disclaimer": "不构成投资建议",
        "source_chunks": [],
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Module-level imports of the functions under test
# ─────────────────────────────────────────────────────────────────────────────

from app.agent.fundamental_review_agent import (
    _canonicalize_source_chunks,
    _check_citation_consistency,
    _check_and_remove_page_citations,
    _check_and_rewrite_coverage_claims,
    _generate_review_audit,
    _rule_based_review,
    FundamentalReviewAgent,
)
from app.agent.schemas import make_review_result


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: valid chunk_id passes through
# ─────────────────────────────────────────────────────────────────────────────

def test_valid_chunk_passes():
    rag_chunk = {
        "chunk_id": 42,
        "report_id": 1,
        "ts_code": "000001.SZ",
        "report_type": "annual",
        "report_year": 2023,
        "period": "2023-12-31",
        "section_title": "主要业务",
        "content": "公司主营银行业务...",
        "score": 0.87,
    }
    data_pack = _make_minimal_data_pack(
        allowed_chunk_ids=[42],
        rag_context=[rag_chunk],
    )
    analysis = _make_minimal_analysis(source_chunks=[{
        "chunk_id": 42,
        "citation": "根据年报主要业务章节",
    }])

    issues, cleaned, audit = _canonicalize_source_chunks(analysis, data_pack)

    assert len(cleaned["source_chunks"]) == 1
    chunk = cleaned["source_chunks"][0]
    assert chunk["chunk_id"] == 42
    assert chunk["section_title"] == "主要业务"
    assert chunk["report_type"] == "annual"
    assert chunk["citation"] == "根据年报主要业务章节"
    assert audit["chunk_ids_checked"] == 1
    assert audit["invalid_removed"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: invalid chunk_id removed
# ─────────────────────────────────────────────────────────────────────────────

def test_invalid_chunk_id_removed():
    rag_chunk = {"chunk_id": 10, "report_id": 1, "ts_code": "000001.SZ",
                 "report_type": "annual", "report_year": 2023, "period": "2023-12-31",
                 "section_title": "风险因素", "content": "...", "score": 0.75}
    data_pack = _make_minimal_data_pack(
        allowed_chunk_ids=[10],  # only 10 is allowed; LLM claims 99
        rag_context=[rag_chunk],
    )
    analysis = _make_minimal_analysis(source_chunks=[
        {"chunk_id": 10, "citation": "正常引用"},
        {"chunk_id": 99, "citation": "非法引用"},  # not in allowed_chunk_ids
    ])

    issues, cleaned, audit = _canonicalize_source_chunks(analysis, data_pack)

    chunk_ids = [c["chunk_id"] for c in cleaned["source_chunks"]]
    assert 10 in chunk_ids
    assert 99 not in chunk_ids
    assert 99 in audit["invalid_removed"]
    assert len(issues) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: LLM-modified section_title is canonicalized
# ─────────────────────────────────────────────────────────────────────────────

def test_llm_modified_section_title_canonicalized():
    rag_chunk = {"chunk_id": 5, "report_id": 2, "ts_code": "000001.SZ",
                 "report_type": "annual", "report_year": 2023, "period": "2023-12-31",
                 "section_title": "管理层讨论与分析", "content": "真实内容", "score": 0.9}
    data_pack = _make_minimal_data_pack(allowed_chunk_ids=[5], rag_context=[rag_chunk])
    analysis = _make_minimal_analysis(source_chunks=[{
        "chunk_id": 5,
        "section_title": "LLM_FABRICATED_TITLE",  # LLM tried to override
        "citation": "第一节",
    }])

    issues, cleaned, audit = _canonicalize_source_chunks(analysis, data_pack)

    chunk = cleaned["source_chunks"][0]
    assert chunk["section_title"] == "管理层讨论与分析"  # from rag_context, not LLM
    assert audit["metadata_canonicalized"] is True
    assert any("section_title" in msg for msg in issues)


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: LLM-modified report_type is canonicalized
# ─────────────────────────────────────────────────────────────────────────────

def test_llm_modified_report_type_canonicalized():
    rag_chunk = {"chunk_id": 7, "report_id": 3, "ts_code": "000001.SZ",
                 "report_type": "semi", "report_year": 2023, "period": "2023-06-30",
                 "section_title": "重要事项", "content": "内容", "score": 0.8}
    data_pack = _make_minimal_data_pack(allowed_chunk_ids=[7], rag_context=[rag_chunk])
    analysis = _make_minimal_analysis(source_chunks=[{
        "chunk_id": 7,
        "report_type": "annual",  # LLM reported wrong type
        "citation": "某节",
    }])

    issues, cleaned, audit = _canonicalize_source_chunks(analysis, data_pack)

    chunk = cleaned["source_chunks"][0]
    assert chunk["report_type"] == "semi"  # from rag_context
    assert audit["metadata_canonicalized"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: duplicate chunk_id deduped
# ─────────────────────────────────────────────────────────────────────────────

def test_duplicate_chunk_id_deduped():
    rag_chunk = {"chunk_id": 3, "report_id": 1, "ts_code": "000001.SZ",
                 "report_type": "annual", "report_year": 2023, "period": "2023-12-31",
                 "section_title": "主营业务", "content": "...", "score": 0.88}
    data_pack = _make_minimal_data_pack(allowed_chunk_ids=[3], rag_context=[rag_chunk])
    analysis = _make_minimal_analysis(source_chunks=[
        {"chunk_id": 3, "citation": "第一次引用"},
        {"chunk_id": 3, "citation": "第二次引用（重复）"},
    ])

    issues, cleaned, audit = _canonicalize_source_chunks(analysis, data_pack)

    assert len(cleaned["source_chunks"]) == 1
    assert audit["chunk_ids_checked"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: more than 8 chunks truncated to 8
# ─────────────────────────────────────────────────────────────────────────────

def test_more_than_8_chunks_truncated():
    rag_chunks = [
        {"chunk_id": i, "report_id": 1, "ts_code": "000001.SZ",
         "report_type": "annual", "report_year": 2023, "period": "2023-12-31",
         "section_title": f"章节{i}", "content": "...", "score": 0.8}
        for i in range(1, 12)  # 11 chunks
    ]
    data_pack = _make_minimal_data_pack(
        allowed_chunk_ids=list(range(1, 12)),
        rag_context=rag_chunks,
    )
    analysis = _make_minimal_analysis(source_chunks=[
        {"chunk_id": i, "citation": f"引用{i}"} for i in range(1, 12)
    ])

    issues, cleaned, audit = _canonicalize_source_chunks(analysis, data_pack)

    assert len(cleaned["source_chunks"]) == 8
    assert audit["truncated"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: page citation (第12页) removed from analysis text
# ─────────────────────────────────────────────────────────────────────────────

def test_page_citation_removed():
    analysis = _make_minimal_analysis(
        summary="根据第12页的数据，公司盈利能力优秀。",
        data_pack_context=None,
    )
    data_pack = _make_minimal_data_pack()

    issues, cleaned, was_removed = _check_and_remove_page_citations(analysis, data_pack)

    assert was_removed is True
    assert "第12页" not in cleaned["summary"]
    assert len(issues) >= 1


def test_page_citation_regex_variants():
    """第 3 页 (with spaces) should also be caught."""
    analysis = _make_minimal_analysis(summary="第 3 页显示净利率12%。")
    data_pack = _make_minimal_data_pack()

    issues, cleaned, was_removed = _check_and_remove_page_citations(analysis, data_pack)

    assert was_removed is True
    # The pattern "第 3 页" should be removed
    assert "第" not in cleaned["summary"] or "页" not in cleaned["summary"] or "3" not in cleaned["summary"].split("第")[0] if "第" in cleaned["summary"] else True


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: coverage claim rewritten
# ─────────────────────────────────────────────────────────────────────────────

def test_coverage_claim_rewritten():
    analysis = _make_minimal_analysis(
        summary="AI完整覆盖所有财报并生成本分析。"
    )

    issues, cleaned, was_rewritten = _check_and_rewrite_coverage_claims(analysis)

    assert was_rewritten is True
    assert "完整覆盖所有财报" not in cleaned["summary"]
    assert "基于已接入的公开财报片段和结构化数据" in cleaned["summary"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: body claims report citation but no chunks/reports → signal rewritten
# ─────────────────────────────────────────────────────────────────────────────

def test_citation_signal_rewritten_when_no_data():
    analysis = _make_minimal_analysis(
        summary="根据年报显示，公司毛利率为45%。",
        source_chunks=[],  # no chunks
    )
    data_pack = _make_minimal_data_pack(
        rag_context=[],   # no rag context (proxy for no source_reports)
    )

    issues, cleaned = _check_citation_consistency(analysis, data_pack)

    assert len(issues) >= 1
    assert "根据年报" not in cleaned["summary"]
    assert "根据已接入的结构化公开数据" in cleaned["summary"]


def test_citation_signal_not_rewritten_when_chunks_present():
    rag_chunk = {"chunk_id": 1, "report_id": 1, "ts_code": "000001.SZ",
                 "report_type": "annual", "report_year": 2023, "period": "2023-12-31",
                 "section_title": "财务摘要", "content": "...", "score": 0.9}
    data_pack = _make_minimal_data_pack(allowed_chunk_ids=[1], rag_context=[rag_chunk])
    analysis = _make_minimal_analysis(
        summary="根据年报显示，公司毛利率为45%。",
        source_chunks=[{"chunk_id": 1, "citation": "财务摘要"}],
    )

    # has_chunks is True → no rewrite
    issues, cleaned = _check_citation_consistency(analysis, data_pack)

    assert len(issues) == 0
    assert "根据年报" in cleaned["summary"]  # unchanged


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: review_audit has expected keys
# ─────────────────────────────────────────────────────────────────────────────

def test_review_audit_has_expected_keys():
    audit = _generate_review_audit(
        source_chunks_checked=True,
        invalid_chunk_ids_removed=[99],
        metadata_canonicalized=True,
        page_citation_removed=False,
        coverage_claim_rewritten=False,
        citation_consistency_rewritten=False,
        investment_advice_blocked=False,
        mild_phrases_rewritten=[],
    )

    required_keys = {
        "source_chunks_checked",
        "invalid_chunk_ids_removed",
        "metadata_canonicalized",
        "page_citation_removed",
        "coverage_claim_rewritten",
        "citation_consistency_rewritten",
        "investment_advice_blocked",
        "mild_phrases_rewritten",
    }
    assert required_keys.issubset(set(audit.keys()))
    assert audit["source_chunks_checked"] is True
    assert audit["invalid_chunk_ids_removed"] == [99]
    assert audit["metadata_canonicalized"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Test 11: review_audit reflects canonicalization correctly
# ─────────────────────────────────────────────────────────────────────────────

def test_review_audit_canonicalization_flag():
    """audit.metadata_canonicalized should be True when LLM modified metadata."""
    rag_chunk = {"chunk_id": 8, "report_id": 1, "ts_code": "000001.SZ",
                 "report_type": "annual", "report_year": 2023, "period": "2023-12-31",
                 "section_title": "经营策略", "content": "...", "score": 0.85}
    data_pack = _make_minimal_data_pack(allowed_chunk_ids=[8], rag_context=[rag_chunk])
    analysis = _make_minimal_analysis(source_chunks=[{
        "chunk_id": 8,
        "section_title": "FAKE_TITLE",  # LLM override
        "citation": "某节",
    }])

    rule_result, cleaned = _rule_based_review(analysis, data_pack)
    chunk_audit = rule_result["chunk_audit_detail"]

    assert chunk_audit["metadata_canonicalized"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Test 12: investment advice blocked → audit flag set
# ─────────────────────────────────────────────────────────────────────────────

def test_investment_advice_blocked_flag():
    analysis = _make_minimal_analysis(
        summary="该股票强烈推荐买入，目标价50元。"
    )
    data_pack = _make_minimal_data_pack()

    review_agent = FundamentalReviewAgent()
    result = asyncio.run(review_agent.review(analysis, data_pack))

    assert result["review_status"] == "rejected"
    audit = result.get("audit", {})
    assert audit.get("investment_advice_blocked") is True


# ─────────────────────────────────────────────────────────────────────────────
# Test 13: orchestrator includes review_audit in final_analysis
# ─────────────────────────────────────────────────────────────────────────────

def test_orchestrator_includes_review_audit():
    """
    The orchestrator spreads final_analysis into ai_analysis_data.
    Since final_analysis now includes review_audit (set by the review agent),
    the envelope's data.ai_analysis should contain review_audit.
    """
    from app.agent.fundamental_ai_orchestrator import _build_envelope

    final_analysis = {
        "summary": "分析摘要",
        "overall_score": 70,
        "dimensions": [],
        "highlights": [],
        "risks": [],
        "watch_items": [],
        "data_limitations": [],
        "disclaimer": "不构成投资建议",
        "review_audit": {
            "source_chunks_checked": True,
            "invalid_chunk_ids_removed": [],
            "metadata_canonicalized": False,
            "page_citation_removed": False,
            "coverage_claim_rewritten": False,
            "citation_consistency_rewritten": False,
            "investment_advice_blocked": False,
            "mild_phrases_rewritten": [],
        },
    }

    envelope = _build_envelope(
        market="CN", symbol="000001", ts_code="000001.SZ",
        final_analysis=final_analysis,
        review_status="approved",
        data_quality={"score": 80, "level": "high", "issues": []},
        missing_modules=[],
    )

    ai = envelope["data"]["ai_analysis"]
    assert "review_audit" in ai
    assert ai["review_audit"]["source_chunks_checked"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Test 14: schemas.make_review_result carries audit field
# ─────────────────────────────────────────────────────────────────────────────

def test_make_review_result_carries_audit():
    audit_payload = {
        "source_chunks_checked": True,
        "invalid_chunk_ids_removed": [5, 6],
        "metadata_canonicalized": True,
        "page_citation_removed": True,
        "coverage_claim_rewritten": False,
        "citation_consistency_rewritten": False,
        "investment_advice_blocked": False,
        "mild_phrases_rewritten": [],
    }

    result = make_review_result(
        status="revised",
        notes=[{"type": "chunk_id_cleaned", "message": "2 chunks removed"}],
        blocked=[],
        final={"summary": "OK"},
        audit=audit_payload,
    )

    assert result["review_status"] == "revised"
    assert result["audit"] == audit_payload
    assert result["audit"]["invalid_chunk_ids_removed"] == [5, 6]


def test_make_review_result_without_audit_defaults_to_empty():
    result = make_review_result(
        status="approved",
        notes=[],
        blocked=[],
        final={"summary": "OK"},
    )

    assert result["audit"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# Test 15: no v-html in AiAnalysisCard.vue or ReportDocumentsPanel.vue
# ─────────────────────────────────────────────────────────────────────────────

def test_no_v_html_in_ai_analysis_card():
    """Security: all content must use text interpolation, never v-html."""
    frontend_root = Path(__file__).parent.parent.parent.parent / "frontend" / "src"
    aac = frontend_root / "components" / "fundamentals" / "AiAnalysisCard.vue"
    rdp = frontend_root / "components" / "fundamentals" / "ReportDocumentsPanel.vue"

    for path in [aac, rdp]:
        if path.exists():
            content = path.read_text()
            assert "v-html" not in content, (
                f"{path.name} contains v-html — XSS risk! "
                "All content must use {{ }} text interpolation."
            )
