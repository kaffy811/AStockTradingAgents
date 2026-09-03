from __future__ import annotations


def test_cache_key_version_invalidation_and_ttl():
    from app.services.company_v2_financial_fusion_cache import company_v2_financial_fusion_cache

    company_v2_financial_fusion_cache.clear()
    key1 = company_v2_financial_fusion_cache.build_key(
        symbol="601686",
        report_id=1,
        pdf_hash="a",
        parse_version="parsed",
        embedding_version="v1",
        structured_data_version="seed1",
        field_definition_registry_version="v1",
        tolerance_version="v1",
        selected_fields=["revenue"],
    )
    key2 = company_v2_financial_fusion_cache.build_key(
        symbol="601686",
        report_id=1,
        pdf_hash="a",
        parse_version="parsed",
        embedding_version="v2",
        structured_data_version="seed1",
        field_definition_registry_version="v1",
        tolerance_version="v1",
        selected_fields=["revenue"],
    )
    assert key1 != key2
    entry = company_v2_financial_fusion_cache.set(key1, {"ok": True}, ttl_seconds=1)
    assert company_v2_financial_fusion_cache.get(key1).data["ok"] is True
    assert entry.cache_key_version.startswith("v")
