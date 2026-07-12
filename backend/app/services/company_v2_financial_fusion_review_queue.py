"""Manual review queue for Company V2 financial evidence fusion."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
import uuid


REVIEW_STATUSES = {
    "value_conflict",
    "likely_match",
    "unit_mismatch",
}


@dataclass(slots=True)
class ReviewItem:
    review_id: str
    symbol: str
    report_id: int
    field_name: str
    fusion_status: str
    priority: str
    reason: str
    provider_value: Any
    official_value: Any
    citation: dict[str, Any] | None
    source_trace: dict[str, Any] | None
    created_at: str
    reviewed_at: str | None = None
    reviewer_decision: str | None = None
    reviewer_notes: str | None = None


class CompanyV2FinancialFusionReviewQueue:
    def __init__(self) -> None:
        self._items: dict[str, ReviewItem] = {}
        self._by_key: dict[str, str] = {}

    def clear(self) -> None:
        self._items.clear()
        self._by_key.clear()

    def enqueue(self, *, symbol: str, report_id: int, field_name: str, fusion_status: str, reason: str, provider_value: Any, official_value: Any, citation: dict[str, Any] | None, source_trace: dict[str, Any] | None, priority: str = "medium") -> dict[str, Any]:
        key = f"{symbol}:{report_id}:{field_name}:{fusion_status}:{reason}"
        if key in self._by_key:
            return asdict(self._items[self._by_key[key]])
        now = datetime.now(timezone.utc).isoformat()
        item = ReviewItem(
            review_id=str(uuid.uuid4()),
            symbol=symbol,
            report_id=report_id,
            field_name=field_name,
            fusion_status=fusion_status,
            priority=priority,
            reason=reason,
            provider_value=provider_value,
            official_value=official_value,
            citation=citation,
            source_trace=source_trace,
            created_at=now,
        )
        self._items[item.review_id] = item
        self._by_key[key] = item.review_id
        return asdict(item)

    def maybe_enqueue_from_record(self, record: dict[str, Any]) -> dict[str, Any] | None:
        status = record.get("fusion_status")
        confidence = float(record.get("confidence") or 1.0)
        citation_missing = not record.get("official_page") and record.get("official_value") is not None
        source_trace_incomplete = not record.get("source_trace_json")
        if status not in REVIEW_STATUSES and not citation_missing and not source_trace_incomplete:
            return None
        if status in REVIEW_STATUSES:
            reason = f"{status}_needs_manual_review"
            priority = "high" if status == "value_conflict" else "medium"
        elif citation_missing:
            reason = "missing_citation_needs_manual_review"
            priority = "medium"
        elif source_trace_incomplete:
            reason = "source_trace_incomplete_needs_manual_review"
            priority = "medium"
        else:
            return None
        citation = {
            "page": record.get("official_page"),
            "chunk_id": record.get("official_chunk_id"),
            "excerpt": record.get("official_excerpt"),
            "source_url": (record.get("source_trace_json") or {}).get("official", {}).get("source_url"),
        }
        return self.enqueue(
            symbol=record.get("symbol") or "",
            report_id=int(record.get("report_id") or 0),
            field_name=record.get("field_name") or "",
            fusion_status=status,
            reason=reason,
            provider_value=record.get("provider_value"),
            official_value=record.get("official_value"),
            citation=citation,
            source_trace=record.get("source_trace_json"),
            priority=priority,
        )

    def list(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in sorted(self._items.values(), key=lambda item: item.created_at, reverse=True)]


company_v2_financial_fusion_review_queue = CompanyV2FinancialFusionReviewQueue()
