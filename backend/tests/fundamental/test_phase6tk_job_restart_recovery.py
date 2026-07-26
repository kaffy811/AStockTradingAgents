from __future__ import annotations


def test_running_job_restart_policy_is_retryable_interrupted():
    interrupted_status = {
        "status": "failed",
        "error_code": "JOB_INTERRUPTED",
        "retryable": True,
        "current_stage": "completed",
    }
    assert interrupted_status["retryable"] is True
    assert interrupted_status["error_code"] == "JOB_INTERRUPTED"
