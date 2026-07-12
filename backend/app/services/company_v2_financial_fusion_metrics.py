"""Metrics collection for Company V2 financial evidence fusion."""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Any


class CompanyV2FinancialFusionMetrics:
    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()
        self.latencies: dict[str, list[float]] = defaultdict(list)

    def clear(self) -> None:
        self.counters.clear()
        self.latencies.clear()

    def inc(self, key: str, value: int = 1) -> None:
        self.counters[key] += value

    def observe_latency(self, key: str, value_ms: float) -> None:
        self.latencies[key].append(float(value_ms))

    def snapshot(self) -> dict[str, Any]:
        cache_hits = int(self.counters.get("fusion_cache_hits_total", 0))
        cache_misses = int(self.counters.get("fusion_cache_misses_total", 0))
        fields_total = int(self.counters.get("fusion_fields_total", 0))
        requests = int(self.counters.get("fusion_requests_total", 0))
        latency_key = "total_latency_ms" if self.latencies.get("total_latency_ms") else "fusion_latency_ms"
        latency_values = self.latencies.get(latency_key) or []
        return {
            **self.counters,
            "latencies": {key: values[:] for key, values in self.latencies.items()},
            "latency_sample_count": len(latency_values),
            "latency_status": "insufficient_samples" if not latency_values else "ready",
            "p50_latency_ms": self._percentile(latency_key, 50),
            "p95_latency_ms": self._percentile(latency_key, 95),
            "cache_hit_ratio": (cache_hits / (cache_hits + cache_misses)) if (cache_hits + cache_misses) else 0.0,
            "fields_per_request": (fields_total / requests) if requests else 0.0,
        }

    def _percentile(self, key: str, percentile: int) -> float | None:
        values = self.latencies.get(key) or []
        if not values:
            return None
        if percentile == 50:
            return float(median(values))
        values = sorted(values)
        index = max(0, min(len(values) - 1, int(round((percentile / 100) * (len(values) - 1)))))
        return float(values[index])


company_v2_financial_fusion_metrics = CompanyV2FinancialFusionMetrics()
