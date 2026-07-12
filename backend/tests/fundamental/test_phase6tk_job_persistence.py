from __future__ import annotations

import json
from datetime import datetime


def test_job_status_is_lightweight_and_persistent_shape():
    from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob
    from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service

    row = CompanyV2FinancialFusionJob(
        job_id="job-persist",
        market="CN",
        symbol="600519",
        report_id=2,
        report_year=2025,
        requested_fields_json=json.dumps(["revenue"]),
        request_fingerprint="fp",
        status="completed",
        progress=1.0,
        current_stage="completed",
        result_json=json.dumps({"fields": [{"field_name": "revenue"}]}),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    payload = company_v2_financial_fusion_job_service._row_to_status(row)  # noqa: SLF001
    assert payload["terminal"] is True
    assert payload["result_id"] is None
    assert "result_json" not in payload
    assert "local_path" not in payload

