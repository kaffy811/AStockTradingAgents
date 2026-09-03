from __future__ import annotations


def test_warm_cache_contract_requires_equal_hash_and_hit():
    cold = {"cache_hit": False, "result_hash": "abc", "classification": ["verified"]}
    warm = {"cache_hit": True, "result_hash": "abc", "classification": ["verified"], "extractor_executed": False}
    assert warm["cache_hit"] is True
    assert warm["result_hash"] == cold["result_hash"]
    assert warm["classification"] == cold["classification"]
    assert warm["extractor_executed"] is False
