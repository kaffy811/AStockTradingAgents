"""Market-wide security entity resolution.

The resolver is data-driven: it builds a versioned index from the local
security master tables and optional caller-provided rows. Small hand-written
stock maps are intentionally not used here.
"""
from __future__ import annotations

import re
import asyncio
import hashlib
import time
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.industry import StockIndustryMap
from app.models.stock_master import StockMaster
from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service


INDEX_VERSION = "v3_d6_4"
SUPPORTED_MARKETS = ("CN", "HK", "US")
_REQUEST_CACHE_KEY = "_security_entity_index_snapshot_cache"
_CORP_SUFFIX_RE = re.compile(r"(股份有限公司|有限责任公司|有限公司|公司)$")
_ST_PREFIX_RE = re.compile(r"^\*?ST", re.IGNORECASE)
_QUERY_NOISE_RE = re.compile(r"最近|表现|如何|怎么样|怎样|财报|年报|对比|比较|相比|看看|分析|一下|它|该股|这家公司|这只股票|呢|吗")
_CONTEXT_REFERENCE_RE = re.compile(
    r"它(?:的|们)?|这只|这支|该股|这家公司|该公司|这份报告|那份报告|上一份报告|刚才的报告|之前的报告|这个报告|那个报告|这个年报|该报告"
)
_COMPARISON_QUERY_RE = re.compile(r"对比|比较|相比|和|与|、|VS|vs|比呢|比一下|比一比")
_TS_CODE_RE = re.compile(r"(?<!\d)(\d{6})\.(SH|SZ|BJ)(?![A-Z0-9])", re.IGNORECASE)
_CN_CODE_RE = re.compile(r"(?<!\d)\d{6}(?!\d)")
_HK_CODE_RE = re.compile(r"(?<!\d)0?\d{1,5}(?!\d)")
_US_TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:[.-][A-Z])?\b")
_US_TICKER_STOPWORDS = {"PDF", "URL", "HTTP", "HTTPS", "RAG", "QPDF"}


@dataclass(frozen=True)
class SecurityEntity:
    entity_type: str
    market: str
    symbol: str
    exchange: str = ""
    ts_code: str = ""
    short_name: str = ""
    full_name: str = ""
    aliases: list[str] = field(default_factory=list)
    industry: str = ""
    source: str = ""
    confidence: float = 0.0
    match_type: str = ""
    ambiguity: bool = False
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "market": self.market,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "ts_code": self.ts_code,
            "short_name": self.short_name,
            "full_name": self.full_name,
            "aliases": self.aliases,
            "industry": self.industry,
            "source": self.source,
            "confidence": self.confidence,
            "match_type": self.match_type,
            "ambiguity": self.ambiguity,
            "candidates": self.candidates,
        }

    def to_hint(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "symbol": self.symbol,
            "name": self.short_name or self.full_name or self.symbol,
            "query": self.symbol,
            "confidence": self.confidence,
            "match_type": self.match_type,
            "entity": self.to_dict(),
        }


@dataclass(frozen=True)
class _IndexSnapshot:
    market: str
    version: str
    rows: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]
    built_at: float


_APP_INDEX_SNAPSHOTS: dict[str, _IndexSnapshot] = {}
_APP_INDEX_LOCKS: dict[str, asyncio.Lock] = {}
_SECURITY_INDEX_METRICS: dict[str, int | str] = {
    "security_index_cache_hit": 0,
    "security_index_cache_miss": 0,
    "security_index_rebuild": 0,
    "security_index_db_full_scan": 0,
    "security_index_version": INDEX_VERSION,
}


def get_security_index_metrics() -> dict[str, int | str]:
    metrics = dict(_SECURITY_INDEX_METRICS)
    metrics["security_index_snapshot_count"] = len(_APP_INDEX_SNAPSHOTS)
    metrics["security_index_snapshot_id"] = hashlib.sha1(
        "|".join(sorted(_APP_INDEX_SNAPSHOTS)).encode("utf-8")
    ).hexdigest()[:12] if _APP_INDEX_SNAPSHOTS else ""
    return metrics


def reset_security_index_runtime_state() -> None:
    _APP_INDEX_SNAPSHOTS.clear()
    _APP_INDEX_LOCKS.clear()
    for key in list(_SECURITY_INDEX_METRICS):
        _SECURITY_INDEX_METRICS[key] = 0 if key != "security_index_version" else INDEX_VERSION


def normalize_security_text(text: str | None, *, strip_corp_suffix: bool = True, strip_st_prefix: bool = False) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = value.replace("（", "(").replace("）", ")")
    value = re.sub(r"[\s·•,，。:：;；、_\-—/\\'\"`]+", "", value)
    value = value.upper()
    value = value.replace("A股", "A").replace("Ａ股", "A")
    if strip_st_prefix:
        value = _ST_PREFIX_RE.sub("", value)
    if strip_corp_suffix:
        value = _CORP_SUFFIX_RE.sub("", value)
    return value


def _query_terms(text: str) -> list[str]:
    cleaned = _QUERY_NOISE_RE.sub(" ", str(text or ""))
    parts = re.split(r"[\s,，。:：;；、和与/\\()（）]+", cleaned)
    return [
        normalize_security_text(part)
        for part in parts
        if len(normalize_security_text(part)) >= 2
    ]


def infer_exchange(market: str, symbol: str) -> str:
    market = (market or "").upper()
    symbol = str(symbol or "")
    if market == "CN":
        if symbol.startswith(("6", "5", "9")):
            return "SSE"
        if symbol.startswith(("0", "2", "3")):
            return "SZSE"
        if symbol.startswith(("4", "8")):
            return "BSE"
    if market == "HK":
        return "HKEX"
    if market == "US":
        return "US"
    return ""


def ts_code_for(market: str, symbol: str, exchange: str = "") -> str:
    market = (market or "").upper()
    symbol = str(symbol or "")
    exchange = exchange or infer_exchange(market, symbol)
    if market == "CN":
        suffix = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}.get(exchange, "")
        return f"{symbol}.{suffix}" if suffix else symbol
    if market == "HK":
        return f"{symbol.zfill(5)}.HK"
    if market == "US":
        return symbol.upper()
    return symbol


def normalize_symbol_for_market(market: str, symbol: str) -> str:
    market = (market or "").upper()
    raw = str(symbol or "").strip()
    if market == "CN":
        return raw.zfill(6) if raw.isdigit() else raw.upper()
    if market == "HK":
        return raw.lstrip("0").zfill(5) if raw.isdigit() else raw.upper()
    if market == "US":
        return raw.upper()
    return raw


class SecurityEntityResolver:
    def __init__(self, *, sample_rows: list[dict[str, Any]] | None = None) -> None:
        self._sample_rows = sample_rows or []
        self._compiled_indexes: dict[str, dict[str, Any]] = {}

    async def resolve_one(
        self,
        db: AsyncSession | None,
        query: str,
        *,
        market_hint: str | None = None,
        context_entity: dict[str, Any] | None = None,
        min_confidence: float = 0.82,
    ) -> SecurityEntity | None:
        result = await self.resolve(db, query, market_hint=market_hint, context_entity=context_entity, min_confidence=min_confidence)
        if result.get("ambiguity"):
            return None
        entities = result.get("entities") or []
        return entities[0] if entities else None

    async def resolve_many(
        self,
        db: AsyncSession | None,
        text: str,
        *,
        market_hint: str | None = None,
        context_entities: list[dict[str, Any]] | None = None,
        max_entities: int = 5,
    ) -> list[SecurityEntity]:
        result = await self.resolve(db, text, market_hint=market_hint, context_entities=context_entities)
        entities = result.get("entities") or []
        return entities[:max_entities]

    async def resolve(
        self,
        db: AsyncSession | None,
        query: str,
        *,
        market_hint: str | None = None,
        context_entity: dict[str, Any] | None = None,
        context_entities: list[dict[str, Any]] | None = None,
        min_confidence: float = 0.82,
    ) -> dict[str, Any]:
        text = str(query or "")
        context_rows = list(context_entities or [])
        if context_entity:
            context_rows.insert(0, context_entity)
        context_reference = self._context_reference_entity(text, context_rows, min_confidence=min_confidence)
        if context_reference is not None:
            return {
                "query": query,
                "entities": [context_reference],
                "ambiguity": False,
                "candidates": [context_reference.to_dict()],
                "index_version": INDEX_VERSION,
                "cache_key_version": INDEX_VERSION,
                "record_count_by_market": {},
                "security_index_cache_hit": True,
                "security_index_full_scan_count": int(_SECURITY_INDEX_METRICS["security_index_db_full_scan"]),
                "security_index_rebuild_count": int(_SECURITY_INDEX_METRICS["security_index_rebuild"]),
                "security_index_snapshot_id": get_security_index_metrics().get("security_index_snapshot_id"),
            }

        markets = [market_hint.upper()] if market_hint else self._markets_for_query(text)
        index: list[dict[str, Any]] = []
        record_count_by_market: dict[str, int] = {}
        for market in markets:
            market_rows = await self._load_index(db, market)
            record_count_by_market[market] = len(market_rows)
            index.extend(market_rows)

        candidates = self._match_candidates(text, index, min_confidence=min_confidence)
        selected = self._dedupe_entities(candidates)

        if context_entity and any(token in text for token in ("它", "该股", "这家公司", "这只股票", "该公司")):
            selected.insert(0, self._entity_from_row(context_entity, confidence=0.99, match_type="context_pronoun"))
        for ctx in context_entities or []:
            if len(selected) >= 5:
                break
            if any(token in text for token in ("前者", "后者", "第一家", "第二家", "这两家", "这三只")):
                selected.append(self._entity_from_row(ctx, confidence=0.95, match_type="context_reference"))

        selected = self._dedupe_entities(selected)[:5]
        ambiguous = False
        is_comparison_query = any(token in text for token in ("对比", "比较", "相比", "和", "与", "、", "VS", "vs"))
        if not selected and candidates:
            ambiguous = True
        elif len(selected) > 1 and not is_comparison_query and selected[0].confidence < 0.98:
            ambiguous = True
        elif (
            len(selected) > 1
            and not is_comparison_query
            and selected[0].confidence < 0.98
            and abs(selected[0].confidence - selected[1].confidence) < 0.03
        ):
            ambiguous = True
        elif len(selected) == 1:
            close = [
                c for c in candidates
                if c.symbol != selected[0].symbol and abs(c.confidence - selected[0].confidence) < 0.03
            ]
            ambiguous = len(close) > 0 and selected[0].confidence < 0.98

        return {
            "query": query,
            "entities": selected,
            "ambiguity": ambiguous,
            "candidates": [c.to_dict() for c in candidates[:8]],
            "index_version": INDEX_VERSION,
            "cache_key_version": INDEX_VERSION,
            "record_count_by_market": record_count_by_market,
            "security_index_cache_hit": int(_SECURITY_INDEX_METRICS["security_index_cache_hit"]) > 0,
            "security_index_full_scan_count": int(_SECURITY_INDEX_METRICS["security_index_db_full_scan"]),
            "security_index_rebuild_count": int(_SECURITY_INDEX_METRICS["security_index_rebuild"]),
            "security_index_snapshot_id": get_security_index_metrics().get("security_index_snapshot_id"),
        }

    # Generic tokens that must never be treated as an ambiguous company alias.
    _ALIAS_STOPWORDS = frozenset({
        "年报", "季报", "中报", "半年", "报告", "公告", "财报", "业绩", "官方",
        "最新", "今天", "股票", "证券", "市场", "公司", "集团", "控股", "股份",
        "银行", "保险", "科技", "能源", "汽车", "医药", "地产", "电子", "通信",
    })
    _ALIAS_MIN_CANDIDATES = 2
    _ALIAS_MAX_MATCHES = 8

    async def resolve_short_alias_candidates(
        self,
        db: AsyncSession | None,
        query: str,
        *,
        max_candidates: int = 5,
    ) -> dict[str, Any] | None:
        """Return deterministic clarification candidates for a bare short alias.

        Used only after normal resolution found no entity: a short Chinese
        alias (e.g. a two-character brand fragment) that is contained in the
        short names of several distinct listed companies yields an ambiguity
        candidate list.  Purely index-driven — no per-company hardcoding, no
        report tool calls, no URLs, no auto-selection.
        """
        text = str(query or "")
        runs = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        if not runs:
            return None
        markets = self._markets_for_query(text)
        index: list[dict[str, Any]] = []
        for market in markets:
            index.extend(await self._load_index(db, market))
        if not index:
            return None
        for run in runs:
            for length in (4, 3, 2):
                if len(run) < length:
                    continue
                token = run[:length]
                if token in self._ALIAS_STOPWORDS:
                    continue
                matches = self._alias_matches(token, index)
                if self._ALIAS_MIN_CANDIDATES <= len(matches) <= self._ALIAS_MAX_MATCHES:
                    return {
                        "query_term": token,
                        "source": "security_entity_resolver_short_alias",
                        "candidates": matches[:max_candidates],
                    }
        return None

    def _alias_matches(self, token: str, index: list[dict[str, Any]]) -> list[dict[str, Any]]:
        market_priority = {"CN": 0, "HK": 1, "US": 2}
        seen: set[tuple[str, str]] = set()
        scored: list[tuple[int, int, int, str, dict[str, Any]]] = []
        for row in index:
            short_name = str(row.get("short_name") or "")
            if not short_name or token not in short_name:
                continue
            # an exact full-name match belongs to normal resolution, not here
            if short_name == token:
                continue
            market = str(row.get("market") or "CN").upper()
            symbol = str(row.get("symbol") or "")
            key = (market, symbol)
            if key in seen:
                continue
            seen.add(key)
            prefix_rank = 0 if short_name.startswith(token) else 1
            scored.append((prefix_rank, len(short_name), market_priority.get(market, 9), symbol, {
                "display_name": short_name,
                "symbol": symbol,
                "market": market,
                "reason": (f"名称以“{token}”开头" if prefix_rank == 0 else f"名称包含“{token}”"),
            }))
        scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        # cross-market duplicates of the same listed name keep the highest-priority market
        deduped: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in scored:
            name = str(item[4]["display_name"])
            if name in seen_names:
                continue
            seen_names.add(name)
            deduped.append(item[4])
        return deduped

    def _context_reference_entity(
        self,
        text: str,
        context_entities: list[dict[str, Any]],
        *,
        min_confidence: float,
    ) -> SecurityEntity | None:
        if not context_entities or not _CONTEXT_REFERENCE_RE.search(text or ""):
            return None
        if _COMPARISON_QUERY_RE.search(text or ""):
            return None
        if _CN_CODE_RE.search(text or "") or _TS_CODE_RE.search(text or ""):
            return None
        entity = self._entity_from_row(context_entities[0], confidence=0.99, match_type="context_report_reference")
        return entity if entity.confidence >= min_confidence and entity.symbol else None

    def _markets_for_query(self, text: str) -> list[str]:
        if _TS_CODE_RE.search(text or "") or _CN_CODE_RE.search(text or ""):
            return ["CN"]
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", text or ""))
        hk_tokens = {token for token in _HK_CODE_RE.findall(text or "") if token.isdigit()}
        if hk_tokens and not has_cjk:
            return ["HK"]
        us_tokens = {
            token for token in _US_TICKER_RE.findall((text or "").upper())
            if token not in _US_TICKER_STOPWORDS
        }
        if us_tokens and not has_cjk:
            return ["US"]
        return list(SUPPORTED_MARKETS)

    async def _load_index(self, db: AsyncSession | None, market: str) -> list[dict[str, Any]]:
        market = market.upper()
        if self._sample_rows:
            return [self._normalize_row(row, market_hint=market) for row in self._sample_rows if (row.get("market") or market).upper() == market]
        if db is None:
            return []
        cache_key = f"security_entity_index:{market}:{INDEX_VERSION}"
        request_cache = self._request_cache(db)
        if request_cache is not None and cache_key in request_cache:
            _SECURITY_INDEX_METRICS["security_index_cache_hit"] = int(_SECURITY_INDEX_METRICS["security_index_cache_hit"]) + 1
            return self._copy_rows(request_cache[cache_key].rows)

        app_snapshot = _APP_INDEX_SNAPSHOTS.get(cache_key)
        if app_snapshot is not None and self._index_is_usable(list(app_snapshot.rows), market):
            if request_cache is not None:
                request_cache[cache_key] = app_snapshot
            _SECURITY_INDEX_METRICS["security_index_cache_hit"] = int(_SECURITY_INDEX_METRICS["security_index_cache_hit"]) + 1
            return self._copy_rows(app_snapshot.rows)

        cached, swr_status, _ = await company_v2_snapshot_cache_service.get_swr(cache_key)
        cached_rows = self._rows_from_cached_index(cached, market)
        if swr_status in {"fresh", "stale"} and self._index_is_usable(cached_rows, market):
            snapshot = self._snapshot_from_rows(market, cached_rows, cached.get("metadata") if isinstance(cached, dict) else None)
            _APP_INDEX_SNAPSHOTS[cache_key] = snapshot
            if request_cache is not None:
                request_cache[cache_key] = snapshot
            _SECURITY_INDEX_METRICS["security_index_cache_hit"] = int(_SECURITY_INDEX_METRICS["security_index_cache_hit"]) + 1
            return cached_rows

        _SECURITY_INDEX_METRICS["security_index_cache_miss"] = int(_SECURITY_INDEX_METRICS["security_index_cache_miss"]) + 1
        lock = _APP_INDEX_LOCKS.setdefault(cache_key, asyncio.Lock())
        async with lock:
            app_snapshot = _APP_INDEX_SNAPSHOTS.get(cache_key)
            if app_snapshot is not None and self._index_is_usable(list(app_snapshot.rows), market):
                if request_cache is not None:
                    request_cache[cache_key] = app_snapshot
                _SECURITY_INDEX_METRICS["security_index_cache_hit"] = int(_SECURITY_INDEX_METRICS["security_index_cache_hit"]) + 1
                return self._copy_rows(app_snapshot.rows)

            cached, swr_status, _ = await company_v2_snapshot_cache_service.get_swr(cache_key)
            cached_rows = self._rows_from_cached_index(cached, market)
            if swr_status in {"fresh", "stale"} and self._index_is_usable(cached_rows, market):
                snapshot = self._snapshot_from_rows(market, cached_rows, cached.get("metadata") if isinstance(cached, dict) else None)
                _APP_INDEX_SNAPSHOTS[cache_key] = snapshot
                if request_cache is not None:
                    request_cache[cache_key] = snapshot
                _SECURITY_INDEX_METRICS["security_index_cache_hit"] = int(_SECURITY_INDEX_METRICS["security_index_cache_hit"]) + 1
                return cached_rows

            _SECURITY_INDEX_METRICS["security_index_rebuild"] = int(_SECURITY_INDEX_METRICS["security_index_rebuild"]) + 1
            try:
                rows = await self._load_master_rows(db, market)
            except Exception:
                fallback = _APP_INDEX_SNAPSHOTS.get(cache_key)
                if fallback is not None:
                    return self._copy_rows(fallback.rows)
                raise

        if self._index_is_usable(rows, market):
            snapshot = self._snapshot_from_rows(market, rows)
            _APP_INDEX_SNAPSHOTS[cache_key] = snapshot
            if request_cache is not None:
                request_cache[cache_key] = snapshot
            await company_v2_snapshot_cache_service.set_swr(
                cache_key,
                self._index_payload(rows, market),
                fresh_ttl=6 * 3600,
                stale_ttl=24 * 3600,
            )
        elif rows:
            await company_v2_snapshot_cache_service.set_swr(
                cache_key,
                self._index_payload(rows, market),
                fresh_ttl=60,
                stale_ttl=120,
            )
        return rows

    async def _load_master_rows(self, db: AsyncSession, market: str) -> list[dict[str, Any]]:
        _SECURITY_INDEX_METRICS["security_index_db_full_scan"] = int(_SECURITY_INDEX_METRICS["security_index_db_full_scan"]) + 1
        by_key: dict[tuple[str, str], dict[str, Any]] = {}

        industry_stmt = (
            select(StockIndustryMap)
            .where(StockIndustryMap.market == market, StockIndustryMap.is_primary.is_(True))
            .limit(30000)
        )
        industry_rows = (await db.execute(industry_stmt)).scalars().all()
        for row in industry_rows:
            normalized = self._normalize_row({
                "market": row.market,
                "symbol": row.symbol,
                "short_name": row.stock_name,
                "full_name": row.stock_name,
                "industry": row.industry_name,
                "entity_type": "equity",
                "source": f"stock_industry_map:{row.source}",
            })
            by_key[(normalized["market"], normalized["symbol"])] = normalized

        master_stmt = select(StockMaster).where(StockMaster.market == market, StockMaster.status == "active").limit(30000)
        master_rows = (await db.execute(master_stmt)).scalars().all()
        for row in master_rows:
            normalized = self._normalize_row({
                "market": row.market,
                "symbol": row.symbol,
                "short_name": row.name,
                "full_name": getattr(row, "full_name", "") or row.name,
                "exchange": row.exchange,
                "entity_type": row.asset_type or "equity",
                "source": f"stock_master:{row.source}",
            })
            key = (normalized["market"], normalized["symbol"])
            existing = by_key.get(key)
            if existing:
                normalized["industry"] = normalized.get("industry") or existing.get("industry") or ""
                normalized["aliases"] = sorted(set((normalized.get("aliases") or []) + (existing.get("aliases") or [])))
                normalized["source"] = f"{normalized.get('source')};{existing.get('source')}"
                normalized["normalized_names"] = sorted(set((normalized.get("normalized_names") or []) + (existing.get("normalized_names") or [])))
            by_key[key] = normalized

        return sorted(by_key.values(), key=lambda r: (r.get("market", ""), r.get("symbol", "")))

    def _request_cache(self, db: AsyncSession | None) -> dict[str, _IndexSnapshot] | None:
        if db is None:
            return None
        info = getattr(db, "info", None)
        if not isinstance(info, dict):
            sync_session = getattr(db, "sync_session", None)
            info = getattr(sync_session, "info", None)
        if not isinstance(info, dict):
            return None
        cache = info.setdefault(_REQUEST_CACHE_KEY, {})
        return cache if isinstance(cache, dict) else None

    def _snapshot_from_rows(
        self,
        market: str,
        rows: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> _IndexSnapshot:
        payload_meta = metadata or self._index_payload(rows, market).get("metadata") or {}
        return _IndexSnapshot(
            market=market.upper(),
            version=INDEX_VERSION,
            rows=tuple(dict(row) for row in rows),
            metadata=dict(payload_meta),
            built_at=time.time(),
        )

    def _copy_rows(self, rows: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def _index_checksum(self, rows: list[dict[str, Any]]) -> str:
        parts = [
            "|".join([
                str(row.get("market") or ""),
                str(row.get("symbol") or ""),
                str(row.get("short_name") or ""),
                str(row.get("full_name") or ""),
                ",".join(sorted(row.get("normalized_names") or [])),
            ])
            for row in rows
        ]
        return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()

    def _index_payload(self, rows: list[dict[str, Any]], market: str) -> dict[str, Any]:
        source_counts: dict[str, int] = {}
        for row in rows:
            for source in str(row.get("source") or "unknown").split(";"):
                source_counts[source] = source_counts.get(source, 0) + 1
        return {
            "version": INDEX_VERSION,
            "market": market,
            "rows": rows,
            "metadata": {
                "version": INDEX_VERSION,
                "market": market,
                "source_counts": source_counts,
                "indexed_count": len(rows),
                "built_at": time.time(),
                "checksum": self._index_checksum(rows),
            },
        }

    def _rows_from_cached_index(self, cached: Any, market: str) -> list[dict[str, Any]]:
        if isinstance(cached, list):
            return []
        if not isinstance(cached, dict):
            return []
        if cached.get("version") != INDEX_VERSION:
            return []
        metadata = cached.get("metadata") or {}
        rows = cached.get("rows")
        if not isinstance(rows, list):
            return []
        if metadata.get("checksum") and metadata.get("checksum") != self._index_checksum(rows):
            return []
        if metadata.get("market") and str(metadata.get("market")).upper() != market.upper():
            return []
        return rows

    def _index_is_usable(self, rows: list[dict[str, Any]], market: str) -> bool:
        if not rows:
            return False
        minimums = {"CN": 1000, "HK": 10, "US": 1}
        if len(rows) < minimums.get(market.upper(), 1):
            return False
        named = sum(1 for row in rows if row.get("short_name") and row.get("normalized_names"))
        return named > 0

    def _normalize_row(self, row: dict[str, Any], *, market_hint: str | None = None) -> dict[str, Any]:
        market = str(row.get("market") or market_hint or "CN").upper()
        symbol = normalize_symbol_for_market(market, str(row.get("symbol") or ""))
        short_name = str(row.get("short_name") or row.get("name") or row.get("stock_name") or symbol)
        full_name = str(row.get("full_name") or row.get("company_name") or short_name)
        aliases = [str(v) for v in (row.get("aliases") or []) if v]
        former_names = [str(v) for v in (row.get("former_names") or []) if v]
        exchange = str(row.get("exchange") or infer_exchange(market, symbol))
        names = [short_name, full_name, *aliases, *former_names]
        normalized_names = {
            normalize_security_text(name) for name in names if normalize_security_text(name)
        }
        normalized_names.update({
            normalize_security_text(name, strip_st_prefix=True) for name in names if normalize_security_text(name, strip_st_prefix=True)
        })
        return {
            "entity_type": row.get("entity_type") or row.get("asset_type") or "equity",
            "market": market,
            "symbol": symbol,
            "exchange": exchange,
            "ts_code": row.get("ts_code") or ts_code_for(market, symbol, exchange),
            "short_name": short_name,
            "full_name": full_name,
            "aliases": aliases + former_names,
            "industry": row.get("industry") or row.get("industry_name") or "",
            "source": row.get("source") or "",
            "normalized_names": list(normalized_names),
            "english_name": row.get("english_name") or "",
            "pinyin": row.get("pinyin") or "",
            "pinyin_initials": row.get("pinyin_initials") or "",
        }

    def _match_candidates(self, text: str, index: list[dict[str, Any]], *, min_confidence: float) -> list[SecurityEntity]:
        normalized_text = normalize_security_text(text)
        query_terms = _query_terms(text)
        candidates_by_key: dict[tuple[str, str, str], SecurityEntity] = {}
        candidate_rank: dict[tuple[str, str, str], int] = {}
        candidate_position: dict[tuple[str, str, str], int] = {}
        code_tokens = set(_CN_CODE_RE.findall(text))
        ts_tokens = {(m.group(1), m.group(2).upper()) for m in _TS_CODE_RE.finditer(text)}
        hk_tokens = {token for token in _HK_CODE_RE.findall(text) if token.isdigit()}
        us_tokens = {
            token for token in _US_TICKER_RE.findall(text.upper())
            if token not in _US_TICKER_STOPWORDS
        }

        compiled = self._compile_index(index)

        def add(row: dict[str, Any] | None, confidence: float, match_type: str, *, rank: int = 0, position: int = 9999) -> None:
            if not row or confidence < min_confidence:
                return
            entity = self._entity_from_row(row, confidence=round(confidence, 4), match_type=match_type)
            key = (entity.market, entity.symbol, match_type)
            existing = candidates_by_key.get(key)
            existing_rank = candidate_rank.get(key, -1)
            existing_position = candidate_position.get(key, 9999)
            if (
                existing is None
                or entity.confidence > existing.confidence
                or (entity.confidence == existing.confidence and position < existing_position)
                or (entity.confidence == existing.confidence and position == existing_position and rank > existing_rank)
            ):
                candidates_by_key[key] = entity
                candidate_rank[key] = rank
                candidate_position[key] = position

        suffix_to_exchange = {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}
        for code in code_tokens:
            add(compiled["cn_code"].get(code), 1.0, "exact_code", rank=1000, position=max(text.find(code), 0))
        for code, suffix in ts_tokens:
            row = compiled["cn_code"].get(code)
            if row and row.get("exchange") == suffix_to_exchange.get(suffix):
                add(row, 1.0, "exact_ts_code", rank=1000, position=max(text.upper().find(f"{code}.{suffix}"), 0))
        normalized_hk_tokens = {normalize_symbol_for_market("HK", token) for token in hk_tokens}
        for token in normalized_hk_tokens:
            add(compiled["hk_code"].get(token), 0.98, "exact_code", rank=1000, position=max(text.find(token.lstrip("0")), 0))
        for token in us_tokens:
            add(compiled["us_ticker"].get(token.upper()), 0.98, "exact_ticker", rank=1000, position=max(text.upper().find(token.upper()), 0))

        for row in compiled["exact_name"].get(normalized_text, []):
            add(row, 0.99, "exact_short_name", rank=len(normalized_text))

        for row, match_len, position in self._continuous_name_matches(compiled["name_trie"], normalized_text):
            add(row, 1.0, "continuous_name_match", rank=match_len, position=position)

        # Fallback scans are intentionally behind compiled lookups. They keep
        # fuzzy/candidate behavior for ambiguous names without making the common
        # continuous Chinese path scan every listed security.
        if not candidates_by_key:
            for row in index:
                confidence = 0.0
                match_type = ""
                for name in row["normalized_names"]:
                    if not name:
                        continue
                    if (len(normalized_text) >= 2 and normalized_text in name) or any(term in name for term in query_terms):
                        confidence, match_type = max(confidence, 0.94), "normalized_name_contains"
                    elif len(name) >= 2:
                        score = SequenceMatcher(None, normalized_text, name).ratio()
                        if score >= min_confidence and score > confidence:
                            confidence, match_type = score, "fuzzy_name"
                if row.get("pinyin") and row["pinyin"].upper() in normalized_text:
                    confidence, match_type = max(confidence, 0.9), "pinyin"
                if row.get("pinyin_initials") and row["pinyin_initials"].upper() in normalized_text:
                    confidence, match_type = max(confidence, 0.88), "pinyin_initials"
                add(row, confidence, match_type, rank=max((len(name) for name in row.get("normalized_names") or []), default=0))

        candidates = list(candidates_by_key.values())
        candidates.sort(key=lambda c: (
            -c.confidence,
            candidate_position.get((c.market, c.symbol, c.match_type), 9999),
            -candidate_rank.get((c.market, c.symbol, c.match_type), 0),
            c.market,
            c.symbol,
        ))
        return candidates

    def _compile_index(self, index: list[dict[str, Any]]) -> dict[str, Any]:
        checksum = self._index_checksum(index)
        cached = self._compiled_indexes.get(checksum)
        if cached is not None:
            return cached

        compiled: dict[str, Any] = {
            "cn_code": {},
            "hk_code": {},
            "us_ticker": {},
            "exact_name": {},
            "name_trie": {},
        }

        for row in index:
            normalized = self._normalize_row(row)
            market = normalized["market"]
            symbol = normalized["symbol"]
            if market == "CN":
                compiled["cn_code"][symbol] = normalized
                if normalized.get("ts_code"):
                    compiled["cn_code"][str(normalized["ts_code"]).upper()] = normalized
            elif market == "HK":
                compiled["hk_code"][symbol] = normalized
                compiled["hk_code"][symbol.lstrip("0") or symbol] = normalized
            elif market == "US":
                compiled["us_ticker"][symbol.upper()] = normalized

            for name in normalized.get("normalized_names") or []:
                if not name:
                    continue
                compiled["exact_name"].setdefault(name, []).append(normalized)
                node = compiled["name_trie"]
                for char in name:
                    node = node.setdefault(char, {})
                node.setdefault("_rows", []).append(normalized)

        self._compiled_indexes[checksum] = compiled
        return compiled

    def _continuous_name_matches(self, trie: dict[str, Any], normalized_text: str) -> list[tuple[dict[str, Any], int, int]]:
        matches: list[tuple[dict[str, Any], int, int]] = []
        seen: set[tuple[str, str]] = set()
        if not normalized_text or not trie:
            return matches
        for start in range(len(normalized_text)):
            node = trie
            best_rows: list[dict[str, Any]] = []
            best_len = 0
            for pos in range(start, len(normalized_text)):
                node = node.get(normalized_text[pos])
                if node is None:
                    break
                if node.get("_rows"):
                    best_rows = node["_rows"]
                    best_len = pos - start + 1
            for row in best_rows:
                key = (row.get("market", ""), row.get("symbol", ""))
                if key in seen:
                    continue
                seen.add(key)
                matches.append((row, best_len, start))
        return matches

    def _entity_from_row(self, row: dict[str, Any], *, confidence: float, match_type: str) -> SecurityEntity:
        normalized = self._normalize_row(row)
        return SecurityEntity(
            entity_type=str(normalized["entity_type"]),
            market=str(normalized["market"]),
            symbol=str(normalized["symbol"]),
            exchange=str(normalized["exchange"]),
            ts_code=str(normalized["ts_code"]),
            short_name=str(normalized["short_name"]),
            full_name=str(normalized["full_name"]),
            aliases=list(normalized["aliases"]),
            industry=str(normalized["industry"]),
            source=str(normalized["source"]),
            confidence=confidence,
            match_type=match_type,
        )

    def _dedupe_entities(self, candidates: list[SecurityEntity]) -> list[SecurityEntity]:
        seen: set[tuple[str, str]] = set()
        out: list[SecurityEntity] = []
        for entity in candidates:
            key = (entity.market, entity.symbol)
            if key in seen:
                continue
            seen.add(key)
            out.append(entity)
        return out


security_entity_resolver = SecurityEntityResolver()
