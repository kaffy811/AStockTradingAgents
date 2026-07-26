from __future__ import annotations


def test_page_load_allowed_calls_are_lightweight_only():
    page_load_calls = {"eligibility", "readiness", "cached_result_availability", "last_successful_run", "job_status"}
    forbidden = {"fusion_run", "rag_retrieval", "llm_extractor", "review_queue", "cache_refresh"}
    assert page_load_calls.isdisjoint(forbidden)
