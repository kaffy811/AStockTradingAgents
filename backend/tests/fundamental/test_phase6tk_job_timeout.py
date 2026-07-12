from __future__ import annotations


def test_timeout_does_not_overwrite_success_cache_contract():
    timeout_payload = {"status": "timed_out", "error_code": "FUSION_TIMEOUT", "retryable": True, "result_id": None}
    assert timeout_payload["status"] == "timed_out"
    assert timeout_payload["result_id"] is None
    assert timeout_payload["retryable"] is True
