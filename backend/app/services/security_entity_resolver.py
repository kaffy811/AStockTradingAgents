"""Market-wide security entity resolution.

The resolver is data-driven: it builds a versioned index from the local
security master tables and optional caller-provided rows. Small hand-written
stock maps are intentionally not used here.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.industry import StockIndustryMap
from app.models.stock_master import StockMaster
from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service


INDEX_VERSION = "v2_d6_3"
SUPPORTED_MARKETS = ("CN", "HK", "US")
_CORP_SUFFIX_RE = re.compile(r"(股份有限公司|有限责任公司|有限公司|公司|集团)$")
_ST_PREFIX_RE = re.compile(r"^\*?ST", re.IGNORECASE)
_QUERY_NOISE_RE = re.compile(r"最近|表现|如何|怎么样|怎样|财报|年报|对比|比较|相比|看看|分析|一下|它|该股|这家公司|这只股票|呢|吗")
_TS_CODE_RE = re.compile(r"(?<!\d)(\d{6})\.(SH|SZ|BJ)(?![A-Z0-9])", re.IGNORECASE)
_CN_CODE_RE = re.compile(r"(?<!\d)\d{6}(?!\d)")
_HK_CODE_RE = re.compile(r"(?<!\d)0?\d{1,5}(?!\d)")
_US_TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:[.-][A-Z])?\b")


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
        markets = [market_hint.upper()] if market_hint else list(SUPPORTED_MARKETS)
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
        }

    async def _load_index(self, db: AsyncSession | None, market: str) -> list[dict[str, Any]]:
        market = market.upper()
        if self._sample_rows:
            return [self._normalize_row(row, market_hint=market) for row in self._sample_rows if (row.get("market") or market).upper() == market]
        if db is None:
            return []
        cache_key = f"security_entity_index:{market}:{INDEX_VERSION}"
        cached, swr_status, _ = await company_v2_snapshot_cache_service.get_swr(cache_key)
        if swr_status in {"fresh", "stale"} and isinstance(cached, list) and cached:
            return cached

        rows = await self._load_master_rows(db, market)
        if rows:
            await company_v2_snapshot_cache_service.set_swr(cache_key, rows, fresh_ttl=6 * 3600, stale_ttl=24 * 3600)
        return rows

    async def _load_master_rows(self, db: AsyncSession, market: str) -> list[dict[str, Any]]:
        stmt = select(StockMaster).where(StockMaster.market == market, StockMaster.status == "active").limit(20000)
        rows = (await db.execute(stmt)).scalars().all()
        if rows:
            return [
                self._normalize_row({
                    "market": row.market,
                    "symbol": row.symbol,
                    "short_name": row.name,
                    "full_name": getattr(row, "full_name", "") or row.name,
                    "exchange": row.exchange,
                    "entity_type": row.asset_type or "equity",
                    "source": row.source,
                })
                for row in rows
            ]
        fallback_stmt = select(StockIndustryMap).where(StockIndustryMap.market == market, StockIndustryMap.is_primary.is_(True)).limit(20000)
        fallback = (await db.execute(fallback_stmt)).scalars().all()
        return [
            self._normalize_row({
                "market": row.market,
                "symbol": row.symbol,
                "short_name": row.stock_name,
                "full_name": row.stock_name,
                "industry": row.industry_name,
                "entity_type": "equity",
                "source": row.source,
            })
            for row in fallback
        ]

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
            "normalized_names": list(normalized_names),
            "english_name": row.get("english_name") or "",
            "pinyin": row.get("pinyin") or "",
            "pinyin_initials": row.get("pinyin_initials") or "",
        }

    def _match_candidates(self, text: str, index: list[dict[str, Any]], *, min_confidence: float) -> list[SecurityEntity]:
        normalized_text = normalize_security_text(text)
        query_terms = _query_terms(text)
        candidates: list[SecurityEntity] = []
        code_tokens = set(_CN_CODE_RE.findall(text))
        ts_tokens = {(m.group(1), m.group(2).upper()) for m in _TS_CODE_RE.finditer(text)}
        hk_tokens = {token for token in _HK_CODE_RE.findall(text) if token.isdigit()}
        us_tokens = set(_US_TICKER_RE.findall(text.upper()))

        for row in index:
            market = row["market"]
            symbol = row["symbol"]
            match_type = ""
            confidence = 0.0
            if market == "CN" and symbol in code_tokens:
                confidence, match_type = 1.0, "exact_code"
            elif market == "CN" and any(symbol == code and row["ts_code"].endswith(f".{suffix}") for code, suffix in ts_tokens):
                confidence, match_type = 1.0, "exact_ts_code"
            elif market == "HK" and symbol in {normalize_symbol_for_market("HK", token) for token in hk_tokens}:
                confidence, match_type = 0.98, "exact_code"
            elif market == "US" and symbol.upper() in us_tokens:
                confidence, match_type = 0.98, "exact_ticker"
            else:
                for name in row["normalized_names"]:
                    if not name:
                        continue
                    if normalized_text == name:
                        confidence, match_type = 0.99, "exact_short_name"
                        break
                    if name in normalized_text:
                        confidence, match_type = max(confidence, 0.97), "continuous_name_match"
                    elif (len(normalized_text) >= 2 and normalized_text in name) or any(term in name for term in query_terms):
                        confidence, match_type = max(confidence, 0.94), "normalized_name_contains"
                    elif len(name) >= 2:
                        score = SequenceMatcher(None, normalized_text, name).ratio()
                        if score >= min_confidence and score > confidence:
                            confidence, match_type = score, "fuzzy_name"
                if row.get("pinyin") and row["pinyin"].upper() in normalized_text:
                    confidence, match_type = max(confidence, 0.9), "pinyin"
                if row.get("pinyin_initials") and row["pinyin_initials"].upper() in normalized_text:
                    confidence, match_type = max(confidence, 0.88), "pinyin_initials"
            if confidence >= min_confidence:
                candidates.append(self._entity_from_row(row, confidence=round(confidence, 4), match_type=match_type))
        candidates.sort(key=lambda c: (-c.confidence, c.market, c.symbol))
        return candidates

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
