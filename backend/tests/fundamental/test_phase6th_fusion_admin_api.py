from __future__ import annotations

import json

import pytest

from app.core.config import settings


@pytest.mark.asyncio
async def test_debug_financial_fusion_admin_endpoints_expose_health_metrics_and_queue():
    from app.routers.company_v2_debug import (
        debug_financial_fusion_circuit,
        debug_financial_fusion_circuit_reset,
        debug_financial_fusion_health,
        debug_financial_fusion_metrics,
        debug_financial_fusion_review_queue,
    )
    from app.services.company_v2_financial_fusion_circuit_breaker import company_v2_financial_fusion_circuit_breaker
    from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics
    from app.services.company_v2_financial_fusion_review_queue import company_v2_financial_fusion_review_queue

    company_v2_financial_fusion_circuit_breaker.reset()
    company_v2_financial_fusion_metrics.clear()
    company_v2_financial_fusion_review_queue.clear()
    assert settings.enable_company_v2_debug_api is True

    health = json.loads((await debug_financial_fusion_health(user=None)).body)
    metrics = json.loads((await debug_financial_fusion_metrics(user=None)).body)
    circuit = json.loads((await debug_financial_fusion_circuit(user=None)).body)
    reset = json.loads((await debug_financial_fusion_circuit_reset(user=None)).body)
    queue = json.loads((await debug_financial_fusion_review_queue(user=None)).body)

    assert health["ok"] is True
    assert metrics["ok"] is True
    assert circuit["ok"] is True
    assert reset["ok"] is True
    assert queue["ok"] is True
