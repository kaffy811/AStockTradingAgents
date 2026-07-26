"""Circuit breaker for Company V2 financial evidence fusion."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class CompanyV2FinancialFusionCircuitBreaker:
    def __init__(self) -> None:
        self.state = "closed"
        self.reason: str | None = None
        self.updated_at = self._now()
        self.last_smoke_passed_at: str | None = None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "reason": self.reason,
            "updated_at": self.updated_at,
            "last_smoke_passed_at": self.last_smoke_passed_at,
        }

    def allow(self) -> bool:
        return self.state != "open"

    def trip(self, reason: str) -> dict[str, Any]:
        self.state = "open"
        self.reason = reason
        self.updated_at = self._now()
        return self.snapshot()

    def half_open(self, reason: str | None = None) -> dict[str, Any]:
        self.state = "half_open"
        self.reason = reason or self.reason
        self.updated_at = self._now()
        return self.snapshot()

    def reset(self) -> dict[str, Any]:
        self.state = "closed"
        self.reason = None
        self.updated_at = self._now()
        self.last_smoke_passed_at = self._now()
        return self.snapshot()


company_v2_financial_fusion_circuit_breaker = CompanyV2FinancialFusionCircuitBreaker()
