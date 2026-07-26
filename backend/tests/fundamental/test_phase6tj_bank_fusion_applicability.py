from __future__ import annotations


def test_bank_specific_fields_are_not_forced_into_default_stage2_fusion_set():
    from app.services.company_v2_financial_evidence_fusion_service import DEFAULT_FUSION_FIELDS
    from app.services.company_v2_financial_field_definition_registry import get_field_definition

    assert "inventory_turnover" not in DEFAULT_FUSION_FIELDS
    assert "current_ratio" not in DEFAULT_FUSION_FIELDS
    assert get_field_definition("total_share").value_basis == "point_in_time"
    assert get_field_definition("float_share").value_basis == "point_in_time"
