"""Read-only CNINFO official-event projection for AI chat.

The service intentionally reads persisted ``ReportDocument`` rows only.  It
never discovers, downloads, refreshes, or calls an external provider.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_document import ReportDocument
from app.services.security_entity_resolver import ts_code_for


_CNINFO_HOSTS = frozenset({"cninfo.com.cn", "www.cninfo.com.cn", "static.cninfo.com.cn"})

_EVENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("财报/业绩", re.compile(r"年报|年度报告|半年报|半年度报告|季报|季度报告|业绩|财务报告|业绩预告|业绩快报")),
    ("分红", re.compile(r"分红|分配方案|利润分配|派息|派发现金|权益分派")),
    ("回购", re.compile(r"回购|注销股份")),
    ("股东增减持", re.compile(r"增持|减持|持股变动|股东变动|权益变动|股权变动")),
    ("并购重组", re.compile(r"并购|重组|收购|重大资产|资产置换|发行股份购买")),
    ("治理与管理层", re.compile(r"董事|监事|高管|管理层|治理|换届|选举|辞职|聘任")),
    ("业务进展", re.compile(r"项目|合同|中标|业务进展|投产|产品|合作协议|投资建设")),
    ("监管/诉讼/风险", re.compile(r"监管|问询|处罚|诉讼|仲裁|风险|立案|调查|警示|异常波动|停牌")),
)


def classify_official_event(title: str | None) -> str:
    """Classify one persisted official disclosure without model inference."""
    value = str(title or "")
    for event_type, pattern in _EVENT_RULES:
        if pattern.search(value):
            return event_type
    return "其它官方披露"


def _approved_cninfo_url(*values: str | None) -> str | None:
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in _CNINFO_HOSTS:
            return value
    return None


class OfficialCompanyEventService:
    async def list_persisted_events(
        self,
        db: AsyncSession,
        *,
        market: str,
        symbol: str,
        company_name: str,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Return display-safe CNINFO events, newest disclosure first.

        Rows without a disclosure date or approved official URL are excluded so
        every visible event carries the minimum public evidence contract.
        Database IDs and internal table/parse state are never returned.
        """
        market = str(market or "").upper()
        symbol = str(symbol or "").strip()
        ts_code = ts_code_for(market, symbol)
        if market != "CN" or not symbol or not ts_code:
            return {
                "fulfillment": "unavailable",
                "reason_code": "NO_PERSISTED_CNINFO_EVENTS",
                "events": [],
                "coverage": "cninfo_persisted_metadata_only",
                "quality": "unavailable",
                "as_of": None,
            }

        stmt = (
            select(ReportDocument)
            .where(
                ReportDocument.ts_code == ts_code,
                ReportDocument.source == "cninfo",
            )
            .order_by(
                ReportDocument.disclosure_date.desc().nulls_last(),
                ReportDocument.created_at.desc().nulls_last(),
            )
            .limit(max(int(limit) * 4, 24))
        )
        rows = (await db.execute(stmt)).scalars().all()

        events: list[dict[str, Any]] = []
        skipped_incomplete = 0
        snapshot_times: list[datetime] = []
        for row in rows:
            source_url = _approved_cninfo_url(row.source_url, row.pdf_url)
            published_at = str(row.disclosure_date or "").strip() or None
            if not source_url or not published_at or not row.title:
                skipped_incomplete += 1
                continue
            if row.created_at:
                created_at = row.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                snapshot_times.append(created_at)
            events.append({
                "title": str(row.title).strip(),
                "published_at": published_at,
                "source": "CNINFO",
                "source_url": source_url,
                "event_type": classify_official_event(row.title),
                "symbol": symbol,
                "company_name": company_name or symbol,
                "as_of": None,
                "coverage": "persisted_cninfo_report_metadata",
                "quality": "official_metadata",
            })
            if len(events) >= max(1, min(int(limit), 20)):
                break

        as_of = max(snapshot_times).astimezone(timezone.utc).isoformat() if snapshot_times else None
        for event in events:
            event["as_of"] = as_of

        if not events:
            fulfillment = "unavailable"
            quality = "unavailable"
            reason_code = "NO_PERSISTED_CNINFO_EVENTS"
        elif skipped_incomplete:
            fulfillment = "partial"
            quality = "partial"
            reason_code = "INCOMPLETE_PERSISTED_CNINFO_COVERAGE"
        else:
            fulfillment = "fulfilled"
            quality = "official_metadata"
            reason_code = None

        return {
            "fulfillment": fulfillment,
            "reason_code": reason_code,
            "events": events,
            "coverage": "cninfo_persisted_metadata_only",
            "quality": quality,
            "as_of": as_of,
        }


official_company_event_service = OfficialCompanyEventService()
