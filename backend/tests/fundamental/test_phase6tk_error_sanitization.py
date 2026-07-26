from __future__ import annotations


def test_job_result_sanitizes_internal_paths_and_stack():
    from app.services.company_v2_financial_fusion_job_service import _sanitize_result

    payload = {
        "ok": False,
        "local_path": "/tmp/private.pdf",
        "database_url": "postgresql://secret",
        "traceback": "stack",
        "fields": [{"field_name": "revenue", "source_trace_json": {"official": {"source_url": "https://static.cninfo.com.cn/a.PDF"}}}],
    }
    clean = _sanitize_result(payload)
    assert "local_path" not in clean
    assert "database_url" not in clean
    assert "traceback" not in clean
    assert clean["fields"][0]["source_trace_json"]["official"]["source_url"].startswith("https://static.cninfo.com.cn/")
