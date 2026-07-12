"""Phase 6T-J2: multistock regression invariants after the unit-context fix.

Validates classification invariants against synthetic evidence shapes drawn
from the four real acceptance symbols — read-only, no artifacts written, no
real report data touched.
"""
from __future__ import annotations

from app.services.company_v2_financial_evidence_fusion_service import _fuse_field


def test_600519_revenue_stays_definition_mismatch():
    # structured = 营业总收入 (main_business/total), official = 营业收入 → the unit
    # fix must NOT flip this back to value_conflict.
    record = _fuse_field(
        symbol="600519", report_id=2, report_year=2025, report_type="annual",
        field_name="revenue",
        structured={
            "value": 172054171890.91, "unit": "CNY",
            "provider_definition": "main_business_revenue",
            "provider_period": "2025-12-31", "value_basis": "annual_cumulative",
            "provider_name": "MBRevenue", "confidence": 0.9,
            "source_trace": {"source": "artifact_seed", "field_name": "revenue"},
        },
        official_result={
            "status": "resolved", "retrieval_mode": "extractor",
            "candidate": {
                "value": 168838102514.79, "unit": "CNY", "unit_source": "table_level",
                "definition": "营业收入", "period": "2025-12-31",
                "value_basis": "annual_cumulative", "page": 6, "chunk_id": None,
                "excerpt": "营业收入 168,838,102,514.79", "source_url": "", "score": 0.9,
            },
            "warnings": [],
        },
    )
    assert record.fusion_status == "definition_mismatch"
    assert record.fusion_status != "value_conflict"


def test_period_column_misalignment_not_conflict():
    # 上期/本期错位 → period mismatch, not conflict
    record = _fuse_field(
        symbol="000725", report_id=4, report_year=2025, report_type="annual",
        field_name="net_profit",
        structured={
            "value": 100.0, "unit": "CNY", "provider_definition": "net_profit",
            "provider_period": "2025-12-31", "value_basis": "annual_cumulative",
            "provider_name": "netProfit", "confidence": 0.9,
            "source_trace": {"source": "artifact_seed", "field_name": "net_profit"},
        },
        official_result={
            "status": "resolved", "retrieval_mode": "extractor",
            "candidate": {
                "value": 90.0, "unit": "CNY", "unit_source": "table_level",
                "definition": "净利润", "period": "2024-12-31",  # prior-year column
                "value_basis": "annual_cumulative", "page": 10, "chunk_id": None,
                "excerpt": "净利润 90", "source_url": "", "score": 0.9,
            },
            "warnings": [],
        },
    )
    assert record.fusion_status == "period_basis_mismatch"


def test_consolidated_vs_parent_scope_not_merged():
    # parent-company statement label must not merge with consolidated field
    record = _fuse_field(
        symbol="000001", report_id=5, report_year=2025, report_type="annual",
        field_name="net_profit_parent",
        structured={
            "value": 100.0, "unit": "CNY", "provider_definition": "net_profit_parent",
            "provider_period": "2025-12-31", "value_basis": "annual_cumulative",
            "provider_name": "netProfit", "confidence": 0.9,
            "source_trace": {"source": "artifact_seed", "field_name": "net_profit_parent"},
        },
        official_result={
            "status": "resolved", "retrieval_mode": "extractor",
            "candidate": {
                "value": 90.0, "unit": "CNY", "unit_source": "table_level",
                "definition": "净利润",  # different concept than 归母净利润
                "period": "2025-12-31", "value_basis": "annual_cumulative",
                "page": 10, "chunk_id": None, "excerpt": "母公司利润表 净利润 90",
                "source_url": "", "score": 0.9,
            },
            "warnings": [],
        },
    )
    assert record.fusion_status == "definition_mismatch"
