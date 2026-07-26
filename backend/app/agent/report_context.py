"""Shared report selection and prompt-context helpers for report explanation chains."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.models.report_document import ReportDocument
from app.services.report_document_classifier import KIND_ANNUAL_FULL, classify_report_document


FORMAL_REPORT_TYPES = ("annual", "semi", "semi_annual", "q1", "q3")

_REPORT_ID_RE = re.compile(r"\breport_id\s*[=:：]?\s*(\d+)\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2})\s*(?:年|年度)?")
_PERIOD_RE = re.compile(r"\b(20\d{2})[-/](0[1369]|12)[-/](3[01]|30)\b")


@dataclass(frozen=True)
class ReportSelection:
    report_id: int | None
    symbol: str
    market: str
    ts_code: str
    stock_name: str | None
    report_year: int | None
    report_type: str | None
    period_end: str | None
    title: str | None
    disclosure_date: str | None
    selection_reason: str
    pdf_url: str | None = None
    source_url: str | None = None
    parsed: bool | None = None
    rag_status: str | None = None
    chunk_count: int | None = None
    switched_from_report_id: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.report_id is not None

    def metadata(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "symbol": self.symbol,
            "market": self.market,
            "ts_code": self.ts_code,
            "stock_name": self.stock_name,
            "report_year": self.report_year,
            "report_type": self.report_type,
            "period_end": self.period_end,
            "title": self.title,
            "disclosure_date": self.disclosure_date,
            "pdf_url": self.pdf_url,
            "source_url": self.source_url,
            "parsed": self.parsed,
            "rag_status": self.rag_status,
            "chunk_count": self.chunk_count,
            "selection_reason": self.selection_reason,
            "switched_from_report_id": self.switched_from_report_id,
            "error": self.error,
        }


def parse_explicit_report_id(text: str) -> int | None:
    match = _REPORT_ID_RE.search(text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def parse_explicit_year(text: str) -> int | None:
    period = _PERIOD_RE.search(text or "")
    if period:
        return int(period.group(1))
    match = _YEAR_RE.search(text or "")
    if not match:
        return None
    return int(match.group(1))


def parse_explicit_period(text: str) -> str | None:
    match = _PERIOD_RE.search(text or "")
    return match.group(0).replace("/", "-") if match else None


def parse_explicit_report_type(text: str, report_types: list[str] | None = None) -> str | None:
    normalized = [str(item).strip() for item in (report_types or []) if str(item).strip()]
    if normalized:
        return normalized[0]
    text = text or ""
    if "年报" in text or "年度报告" in text:
        return "annual"
    if "半年报" in text or "中报" in text or "半年度报告" in text:
        return "semi"
    if "一季报" in text or "第一季度" in text:
        return "q1"
    if "三季报" in text or "第三季度" in text:
        return "q3"
    return None


def latest_memory_report_id(memory_turns: list[dict] | None) -> int | None:
    for turn in reversed(memory_turns or []):
        meta = turn.get("report_context") or turn.get("metadata") or {}
        report_id = meta.get("report_id") if isinstance(meta, dict) else None
        try:
            if report_id is not None:
                return int(report_id)
        except (TypeError, ValueError):
            continue
    return None


def _ts_code_for(market: str, symbol: str) -> str:
    if "." in symbol:
        return symbol.upper()
    market = (market or "CN").upper()
    if market == "CN":
        suffix = "SH" if symbol.startswith(("6", "9")) else "SZ"
        return f"{symbol}.{suffix}"
    return symbol.upper()


def _empty_selection(*, market: str, symbol: str, reason: str, error: str, stock_name: str | None = None) -> ReportSelection:
    return ReportSelection(
        report_id=None,
        symbol=symbol,
        market=(market or "").upper(),
        ts_code=_ts_code_for(market, symbol) if symbol else "",
        stock_name=stock_name,
        report_year=None,
        report_type=None,
        period_end=None,
        title=None,
        disclosure_date=None,
        pdf_url=None,
        source_url=None,
        parsed=None,
        rag_status=None,
        chunk_count=None,
        selection_reason=reason,
        error=error,
    )


def _from_doc(
    doc: ReportDocument,
    *,
    market: str,
    symbol: str,
    stock_name: str | None = None,
    reason: str,
    switched_from_report_id: int | None = None,
) -> ReportSelection:
    return ReportSelection(
        report_id=int(doc.id),
        symbol=symbol,
        market=(market or "CN").upper(),
        ts_code=str(doc.ts_code or _ts_code_for(market, symbol)),
        stock_name=stock_name,
        report_year=doc.report_year,
        report_type=doc.report_type,
        period_end=doc.period_end,
        title=doc.title,
        disclosure_date=doc.disclosure_date,
        pdf_url=doc.pdf_url,
        source_url=doc.source_url,
        parsed=bool(doc.parsed),
        rag_status=doc.rag_status,
        chunk_count=doc.chunk_count,
        selection_reason=reason,
        switched_from_report_id=switched_from_report_id,
    )


def _formal_stmt(ts_code: str):
    return select(ReportDocument).where(
        ReportDocument.ts_code == ts_code,
        ReportDocument.report_type.in_(FORMAL_REPORT_TYPES),
    )


def _is_formal_doc_for_question(doc: ReportDocument, explicit_type: str | None = None) -> bool:
    classification = classify_report_document(doc.title, report_type=doc.report_type, category=doc.source)
    requested_type = explicit_type or doc.report_type
    if requested_type == "annual":
        return classification.report_document_kind == KIND_ANNUAL_FULL
    return classification.report_document_kind in {KIND_ANNUAL_FULL, "semi_annual_full", "quarterly"}


def _first_formal_doc(docs: list[ReportDocument], explicit_type: str | None = None) -> ReportDocument | None:
    for doc in docs:
        if _is_formal_doc_for_question(doc, explicit_type):
            return doc
    return None


def _scalars_to_formal_doc(scalars: Any, explicit_type: str | None = None) -> ReportDocument | None:
    if hasattr(scalars, "all"):
        docs = scalars.all()
        if isinstance(docs, (list, tuple)):
            return _first_formal_doc(list(docs), explicit_type)
    doc = scalars.first() if hasattr(scalars, "first") else None
    if doc is not None and _is_formal_doc_for_question(doc, explicit_type):
        return doc
    return None


async def resolve_report_selection(
    *,
    db: Any,
    market: str,
    symbol: str,
    stock_name: str | None = None,
    question: str,
    report_id: int | None = None,
    report_types: list[str] | None = None,
    years: list[int] | None = None,
    memory_turns: list[dict] | None = None,
) -> ReportSelection:
    if not symbol:
        return _empty_selection(
            market=market,
            symbol=symbol,
            stock_name=stock_name,
            reason="missing_symbol",
            error="无法确定股票代码，请明确要分析的公司。",
        )
    if not market:
        return _empty_selection(
            market=market,
            symbol=symbol,
            stock_name=stock_name,
            reason="missing_market",
            error="无法确定市场，请明确市场，例如 CN/600519。",
        )

    market = market.upper()
    ts_code = _ts_code_for(market, symbol)
    explicit_report_id = report_id or parse_explicit_report_id(question)
    explicit_year = (years or [None])[0] or parse_explicit_year(question)
    explicit_period = parse_explicit_period(question)
    explicit_type = parse_explicit_report_type(question, report_types)
    memory_report_id = latest_memory_report_id(memory_turns)

    if explicit_report_id is not None:
        result = await db.execute(select(ReportDocument).where(ReportDocument.id == int(explicit_report_id)))
        doc = result.scalars().first()
        if doc is None:
            return _empty_selection(
                market=market,
                symbol=symbol,
                stock_name=stock_name,
                reason="explicit_report_id_not_found",
                error=f"未找到 report_id={explicit_report_id} 的财报，不能回退到其他报告。",
            )
        if doc.ts_code != ts_code:
            return _empty_selection(
                market=market,
                symbol=symbol,
                stock_name=stock_name,
                reason="explicit_report_id_mismatch",
                error=f"report_id={explicit_report_id} 不属于 {market}/{symbol}，不能混用其他公司的报告。",
            )
        return _from_doc(doc, market=market, symbol=symbol, stock_name=stock_name, reason="explicit_report_id")

    if explicit_year or explicit_period:
        stmt = _formal_stmt(ts_code)
        if explicit_year:
            stmt = stmt.where(ReportDocument.report_year == int(explicit_year))
        if explicit_period:
            stmt = stmt.where(ReportDocument.period_end == explicit_period)
        if explicit_type:
            stmt = stmt.where(ReportDocument.report_type == explicit_type)
        stmt = stmt.order_by(
            ReportDocument.period_end.desc().nullslast(),
            ReportDocument.disclosure_date.desc().nullslast(),
            ReportDocument.id.desc(),
        )
        result = await db.execute(stmt.limit(20))
        doc = _scalars_to_formal_doc(result.scalars(), explicit_type)
        if doc is None:
            detail = f"{explicit_year or explicit_period}"
            return _empty_selection(
                market=market,
                symbol=symbol,
                stock_name=stock_name,
                reason="explicit_period_not_found",
                error=f"未找到 {market}/{symbol} 在 {detail} 对应的正式财报。",
            )
        return _from_doc(doc, market=market, symbol=symbol, stock_name=stock_name, reason="explicit_year_or_period")

    if memory_report_id is not None:
        result = await db.execute(select(ReportDocument).where(ReportDocument.id == int(memory_report_id)))
        doc = result.scalars().first()
        if doc is not None and doc.ts_code == ts_code:
            return _from_doc(doc, market=market, symbol=symbol, stock_name=stock_name, reason="session_report_id")

    stmt = _formal_stmt(ts_code).order_by(
        ReportDocument.report_year.desc().nullslast(),
        ReportDocument.period_end.desc().nullslast(),
        ReportDocument.disclosure_date.desc().nullslast(),
        ReportDocument.id.desc(),
    )
    result = await db.execute(stmt.limit(20))
    doc = _scalars_to_formal_doc(result.scalars(), None)
    if doc is None:
        return _empty_selection(
            market=market,
            symbol=symbol,
            stock_name=stock_name,
            reason="no_formal_report",
            error=f"未找到 {market}/{symbol} 的可用正式财报。",
        )
    switched = memory_report_id if memory_report_id and memory_report_id != doc.id else None
    return _from_doc(
        doc,
        market=market,
        symbol=symbol,
        stock_name=stock_name,
        reason="latest_formal_report",
        switched_from_report_id=switched,
    )


def is_narrow_question(question: str) -> bool:
    text = question or ""
    narrow_terms = ("现金流", "毛利率", "净利润", "利润", "营收", "收入", "负债", "分红", "ROE", "roe")
    return len(text.strip()) <= 24 and any(term in text for term in narrow_terms)


def report_scope_line(selection: ReportSelection) -> str:
    if not selection.ok:
        return selection.error or "报告范围无法确定。"
    return (
        f"{selection.market}/{selection.symbol}，report_id={selection.report_id}，"
        f"{selection.report_year or '未知年份'}，{selection.report_type or '未知类型'}，"
        f"报告期 {selection.period_end or '未知'}"
    )
