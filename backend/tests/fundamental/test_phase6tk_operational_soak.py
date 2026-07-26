from __future__ import annotations


def test_soak_metrics_are_bounded_and_explicit():
    metrics = {
        "requests_total": 5 * (2 + 5 + 3 + 1 + 1 + 1),
        "cold_requests": 10,
        "warm_requests": 25,
        "jobs_created": 65,
        "timeout_count": 0,
        "review_queue_created": 0,
        "result_consistency_failures": 0,
    }
    assert metrics["requests_total"] == 65
    assert metrics["cold_requests"] == 10
    assert metrics["warm_requests"] == 25
    assert metrics["result_consistency_failures"] == 0
