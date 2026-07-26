"""
backend/tests/fundamental/test_phase6ta_accuracy_audit.py
Phase 6T-A: 数据准确性审计服务验收测试
"""
from __future__ import annotations

import pytest


# ── 基础分类测试 ──────────────────────────────────────────────────────────────

def test_baostock_field_is_public_provider_verified():
    """BaoStock 字段应标记为 public_provider_verified，不能是 official_disclosure_verified。"""
    from app.services.company_v2_accuracy_audit_service import audit_envelope

    envelope = {
        "module_key": "profitability",
        "normalized": {
            "fields": {
                "roe": {
                    "value": 0.18,
                    "provider": "baostock",
                    "computed": False,
                    "source": "baostock_aggregate",
                }
            }
        }
    }
    result = audit_envelope(envelope, has_official_pdf=False)
    assert "roe" in result["verified_fields"]
    assert "roe" not in result.get("official_disclosure_fields", [])
    assert result["status"] in ("partially_verified", "unverified")


def test_computed_field_is_computed_from_public_provider():
    """market_cap 应标记为 computed_from_public_provider。"""
    from app.services.company_v2_accuracy_audit_service import audit_envelope

    envelope = {
        "module_key": "quote_overview",
        "normalized": {
            "fields": {
                "market_cap": {
                    "value": 2e12,
                    "provider": "computed",
                    "computed": True,
                    "computed_formula": "recent_close * total_share",
                    "source": "computed",
                },
                "float_market_cap": {
                    "value": 1.5e12,
                    "provider": "computed",
                    "computed": True,
                    "source": "computed",
                }
            }
        }
    }
    result = audit_envelope(envelope, has_official_pdf=False)
    assert "market_cap" in result["computed_fields"]
    assert "float_market_cap" in result["computed_fields"]
    assert "market_cap" not in result.get("official_disclosure_fields", [])


def test_no_buy_sell_wording_in_audit_output():
    """审计输出不包含买入/卖出/目标价等投资建议词汇。"""
    from app.services.company_v2_accuracy_audit_service import audit_envelope, audit_full_debug

    envelope = {
        "module_key": "profitability",
        "normalized": {"fields": {"roe": {"value": 0.2, "provider": "baostock", "computed": False}}}
    }
    result = audit_envelope(envelope)
    text = str(result)
    forbidden = ["买入", "卖出", "目标价", "建议", "推荐", "上涨保证", "保证"]
    for word in forbidden:
        assert word not in text, f"Found forbidden word: {word}"


def test_cninfo_pdf_field_upgrade_to_official():
    """接入 CNINFO 年报 PDF 后，财务字段升级为 official_disclosure_verified。"""
    from app.services.company_v2_accuracy_audit_service import audit_envelope

    envelope = {
        "module_key": "profitability",
        "normalized": {
            "fields": {
                "roe": {
                    "value": 0.18,
                    "provider": "cninfo",
                    "computed": False,
                    "source": "pdf_metrics",
                }
            }
        }
    }
    result = audit_envelope(envelope, has_official_pdf=True)
    assert "roe" in result.get("official_disclosure_fields", [])


def test_audit_has_disclaimer():
    """审计结果包含数据来源免责声明。"""
    from app.services.company_v2_accuracy_audit_service import audit_envelope

    envelope = {"module_key": "growth", "normalized": {"fields": {}}}
    result = audit_envelope(envelope)
    assert "disclaimer" in result
    assert len(result["disclaimer"]) > 10


def test_audit_status_unverified_when_no_fields():
    """无字段时状态为 unverified。"""
    from app.services.company_v2_accuracy_audit_service import audit_envelope

    envelope = {"module_key": "unknown", "normalized": {"fields": {}}}
    result = audit_envelope(envelope)
    assert result["status"] == "unverified"


def test_audit_source_reliability_structure():
    """审计结果包含 source_reliability 映射。"""
    from app.services.company_v2_accuracy_audit_service import audit_envelope

    envelope = {"module_key": "valuation", "normalized": {"fields": {}}}
    result = audit_envelope(envelope)
    assert "source_reliability" in result
    sr = result["source_reliability"]
    assert sr["baostock"] == "public_provider"
    assert sr["akshare"] == "optional_public_adapter"
    assert sr["cninfo"] == "official_disclosure"
    assert sr["computed"] == "derived"


def test_full_debug_audit_structure():
    """audit_full_debug 返回正确的全局结构。"""
    from app.services.company_v2_accuracy_audit_service import audit_full_debug

    debug_data = {
        "modules": {
            "profitability": {
                "module_key": "profitability",
                "normalized": {
                    "fields": {
                        "roe": {"value": 0.15, "provider": "baostock", "computed": False}
                    }
                }
            },
            "quote_overview": {
                "module_key": "quote_overview",
                "normalized": {
                    "fields": {
                        "market_cap": {"value": 1e12, "provider": "computed", "computed": True}
                    }
                }
            }
        }
    }
    result = audit_full_debug(debug_data, has_official_pdf=False)
    assert "status" in result
    assert "verified_fields" in result
    assert "computed_fields" in result
    assert "module_audits" in result
    assert "profitability" in result["module_audits"]
    assert "quote_overview" in result["module_audits"]
    assert "roe" in result["verified_fields"]
    assert "market_cap" in result["computed_fields"]
    assert "disclaimer" in result


def test_price_non_realtime_note():
    """当 price_label=最近收盘价 时，审计 notes 中有非实时提示。"""
    from app.services.company_v2_accuracy_audit_service import audit_full_debug

    debug_data = {
        "modules": {
            "quote_overview": {
                "module_key": "quote_overview",
                "normalized": {
                    "fields": {
                        "recent_close": {"value": 100.0, "provider": "baostock", "computed": False},
                    },
                    "rows": [{"price_label": "最近收盘价", "price_is_realtime": False}],
                }
            }
        }
    }
    result = audit_full_debug(debug_data)
    notes_text = " ".join(result.get("notes", []))
    assert "最近收盘价" in notes_text or "非实时" in notes_text


def test_report_rag_not_independent_module():
    """report_rag 不在 MODULE_KEYS（已合并入 report_documents）。"""
    from app.services.company_v2_debug_service import MODULE_KEYS
    assert "report_rag" not in MODULE_KEYS
    assert "report_documents" in MODULE_KEYS
