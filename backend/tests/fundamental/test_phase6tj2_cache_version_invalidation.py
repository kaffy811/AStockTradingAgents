"""Phase 6T-J2: cache key includes the extractor/unit version — pre-fix caches invalidate."""
from __future__ import annotations

from app.services.company_v2_financial_evidence_fusion_service import _cache_context
from app.services.company_v2_official_field_extractor import OFFICIAL_EXTRACTOR_VERSION


def _key(parse_version="parsed"):
    return _cache_context(
        symbol="600519", report_id=2, pdf_hash="a" * 64,
        parse_version=parse_version, seed_path=None, fields=["net_profit"],
    )


def test_cache_context_exposes_extractor_version():
    ctx = _key()
    assert ctx["official_extractor_version"] == OFFICIAL_EXTRACTOR_VERSION
    assert OFFICIAL_EXTRACTOR_VERSION == "official-extractor-unit-context-v2"


def test_extractor_version_changes_cache_key(monkeypatch):
    key_now = _key()["cache_key"]
    import app.services.company_v2_official_field_extractor as ext

    monkeypatch.setattr(ext, "OFFICIAL_EXTRACTOR_VERSION", "official-extractor-unit-context-v1-legacy")
    key_old = _key()["cache_key"]
    assert key_now != key_old  # old (pre-fix) cache entries can never be reused


def test_registry_and_generation_still_in_key():
    base = _key()["cache_key"]
    assert _key(parse_version="other")["cache_key"] != base
