"""Health summary for Company V2 financial evidence fusion."""
from __future__ import annotations

from typing import Any

from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics


class CompanyV2FinancialFusionHealthService:
    def health(self, window: str = "24h") -> dict[str, Any]:
        metrics = company_v2_financial_fusion_metrics.snapshot()
        requests = int(metrics.get("fusion_requests_total", 0))
        success = int(metrics.get("fusion_success_total", 0))
        timeout = int(metrics.get("fusion_timeout_total", 0))
        cache_hits = int(metrics.get("fusion_cache_hits_total", 0))
        cache_misses = int(metrics.get("fusion_cache_misses_total", 0))
        false_conflict = int(metrics.get("fusion_false_conflict_suspected_total", 0))
        leakage = int(metrics.get("fusion_cross_report_leakage_total", 0))
        missing_citation = int(metrics.get("fusion_missing_citation_total", 0))
        incomplete_trace = int(metrics.get("fusion_incomplete_source_trace_total", 0))
        p50 = metrics.get("p50_latency_ms")
        p95 = metrics.get("p95_latency_ms")
        latency_sample_count = int(metrics.get("latency_sample_count", 0) or 0)
        latency_status = str(metrics.get("latency_status") or "insufficient_samples")

        if requests == 0 or latency_sample_count == 0:
            success_rate = None if requests == 0 else round(success / requests, 4)
        else:
            success_rate = round(success / requests, 4)
        cache_hit_rate = (cache_hits / (cache_hits + cache_misses)) if (cache_hits + cache_misses) else 0.0
        timeout_rate = (timeout / requests) if requests else 0.0
        source_trace_complete_rate = 1.0 if incomplete_trace == 0 else 0.0
        status = "healthy"
        alerts: list[str] = []
        if requests == 0 or latency_sample_count == 0:
            status = "insufficient_data"
        elif leakage > 0 or false_conflict > 0 or missing_citation > 0 or incomplete_trace > 0:
            status = "critical"
        elif timeout_rate > 0.05 or cache_hit_rate < 0.2 or (p95 is not None and p95 > 5000):
            status = "warning"

        if leakage > 0:
            alerts.append("cross_report_leakage_detected")
        if false_conflict > 0:
            alerts.append("false_conflict_suspected")
        if missing_citation > 0:
            alerts.append("missing_citation")
        if incomplete_trace > 0:
            alerts.append("source_trace_incomplete")
        if timeout_rate > 0.05:
            alerts.append("timeout_rate_high")
        if p95 is not None and p95 > 5000:
            alerts.append("latency_p95_high")

        return {
            "window": window,
            "requests": requests,
            "success_rate": success_rate,
            "cache_hit_rate": round(cache_hit_rate, 4),
            "timeout_rate": round(timeout_rate, 4),
            "false_conflict_suspected": false_conflict,
            "cross_report_leakage": leakage,
            "missing_citation_rate": round((missing_citation / requests) if requests else 0.0, 4),
            "source_trace_complete_rate": source_trace_complete_rate,
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "latency_sample_count": latency_sample_count,
            "latency_status": latency_status,
            "status": status,
            "alerts": alerts,
        }


company_v2_financial_fusion_health_service = CompanyV2FinancialFusionHealthService()
