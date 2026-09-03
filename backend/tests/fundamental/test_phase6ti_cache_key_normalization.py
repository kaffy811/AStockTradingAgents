from __future__ import annotations


def test_financial_fusion_cache_key_normalizes_field_order():
    from app.services.company_v2_financial_fusion_cache import company_v2_financial_fusion_cache

    key_a = company_v2_financial_fusion_cache.build_key(
        symbol="601686",
        report_id=1,
        pdf_hash="hash",
        parse_version="parsed",
        embedding_version="v1",
        structured_data_version="sv1",
        field_definition_registry_version="fd1",
        tolerance_version="t1",
        selected_fields=["net_profit", "revenue", "revenue"],
    )
    key_b = company_v2_financial_fusion_cache.build_key(
        symbol="601686",
        report_id=1,
        pdf_hash="hash",
        parse_version="parsed",
        embedding_version="v1",
        structured_data_version="sv1",
        field_definition_registry_version="fd1",
        tolerance_version="t1",
        selected_fields=["revenue", "net_profit"],
    )
    key_c = company_v2_financial_fusion_cache.build_key(
        symbol="601686",
        report_id=1,
        pdf_hash="hash",
        parse_version="parsed",
        embedding_version="v1",
        structured_data_version="sv1",
        field_definition_registry_version="fd1",
        tolerance_version="t1",
        selected_fields=["revenue", "net_profit", "total_assets"],
    )

    assert key_a == key_b
    assert key_a != key_c
