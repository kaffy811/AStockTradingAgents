"""In-memory cache for Company V2 financial evidence fusion."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings


@dataclass(slots=True)
class FinancialFusionCacheEntry:
    cache_key: str
    cache_key_version: str
    data: dict[str, Any]
    computed_at: str
    expires_at: str
    stale_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cache_key": self.cache_key,
            "cache_key_version": self.cache_key_version,
            "data": self.data,
            "computed_at": self.computed_at,
            "expires_at": self.expires_at,
            "stale_reason": self.stale_reason,
        }


class CompanyV2FinancialFusionCache:
    def __init__(self) -> None:
        self._store: dict[str, FinancialFusionCacheEntry] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def build_key(
        self,
        *,
        symbol: str,
        report_id: int,
        pdf_hash: str | None,
        parse_version: str | None,
        embedding_version: str | None,
        structured_data_version: str | None,
        field_definition_registry_version: str | None,
        tolerance_version: str | None,
        selected_fields: list[str],
    ) -> str:
        normalized_fields = ",".join(sorted(dict.fromkeys(selected_fields)))
        payload = "|".join(
            [
                symbol,
                str(int(report_id)),
                pdf_hash or "none",
                parse_version or "none",
                embedding_version or "none",
                structured_data_version or "none",
                field_definition_registry_version or "none",
                tolerance_version or "none",
                normalized_fields,
            ]
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        version = getattr(settings, "company_v2_financial_fusion_cache_version", "v1")
        return f"{version}:{digest}"

    def get(self, cache_key: str) -> FinancialFusionCacheEntry | None:
        entry = self._store.get(cache_key)
        if not entry:
            return None
        if self._now().isoformat() > entry.expires_at:
            entry.stale_reason = "expired"
            return None
        return entry

    def set(self, cache_key: str, data: dict[str, Any], ttl_seconds: int | None = None) -> FinancialFusionCacheEntry:
        ttl_seconds = ttl_seconds or int(getattr(settings, "company_v2_financial_fusion_cache_ttl_seconds", 86400))
        now = self._now()
        entry = FinancialFusionCacheEntry(
            cache_key=cache_key,
            cache_key_version=getattr(settings, "company_v2_financial_fusion_cache_version", "v1"),
            data=data,
            computed_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=ttl_seconds)).isoformat(),
        )
        self._store[cache_key] = entry
        return entry

    def clear(self) -> None:
        self._store.clear()

    def snapshot(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self._store.values()]


company_v2_financial_fusion_cache = CompanyV2FinancialFusionCache()
