"""
app/agent/fundamental_ai_orchestrator.py — AI Orchestrator (Phase 3)

编排链：Data Agent → Analysis Agent → Review Agent → cache → DataEnvelope
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.agent.fundamental_data_agent import FundamentalDataAgent
from app.agent.fundamental_analysis_agent import FundamentalAnalysisAgent
from app.agent.fundamental_review_agent import FundamentalReviewAgent
from app.agent.schemas import SAFE_PLACEHOLDER
from app.agent import ai_cache

log = logging.getLogger(__name__)

# Prompt version — bump when prompts change to invalidate old cache
PROMPT_VERSION = "v1"


def _ai_provider() -> str:
    """Return the configured AI provider name (default: deepseek)."""
    try:
        from app.core.config import settings
        return settings.ai_provider
    except Exception:
        return "deepseek"


def _now_cst() -> str:
    from datetime import datetime, timezone, timedelta
    cst = timezone(timedelta(hours=8))
    return datetime.now(cst).isoformat(timespec="seconds")


def _build_envelope(
    market: str, symbol: str, ts_code: str,
    final_analysis: dict,
    review_status: str,
    data_quality: dict,
    missing_modules: list,
    stale: bool = False,
    partial: bool = False,
    errors: list[str] | None = None,
    source_chunks: list[dict] | None = None,
    rag_status: str = "unavailable",
) -> dict:
    ai_analysis_data: dict = {
        **final_analysis,
        "data_quality": data_quality,
    }
    if source_chunks is not None:
        ai_analysis_data["source_chunks"] = source_chunks
        ai_analysis_data["rag_status"] = rag_status

    return {
        "market": market,
        "symbol": symbol,
        "ts_code": ts_code,
        "module_key": "ai_analysis",
        "module_name": "AI 财报分析",
        "group": "AI分析",
        "group_seq": 8,
        "data": {
            "ai_analysis": ai_analysis_data,
        },
        "errors": errors or [],
        "partial": partial,
        "stale": stale,
        "partial_errors": [m["reason"] for m in missing_modules] if missing_modules else [],
        "generated_at": _now_cst(),
        "source": {
            "primary": _ai_provider(),
            "fallback": None,
            "actual": _ai_provider() if not stale else "cache",
        },
        "meta": {
            "render_type": "ai_card",
            "chart_type": "radar",
            "unit_hints": {},
            "field_labels": {},
            "empty_state": "AI 分析暂不可用",
            "disclaimer_type": "ai_generated",
        },
        "cached_at": None,
    }


class FundamentalAIOrchestrator:

    def __init__(self) -> None:
        self._data_agent     = FundamentalDataAgent()
        self._analysis_agent = FundamentalAnalysisAgent()
        self._review_agent   = FundamentalReviewAgent()

    async def run(
        self,
        market: str,
        symbol: str,
        mode: str = "summary",
        force_refresh: bool = False,
        db=None,
    ) -> dict:
        """
        Returns a DataEnvelope dict for ai_analysis module.
        Never raises.
        db: optional AsyncSession — if provided, RAG context is injected.
        """
        try:
            return await self._run_internal(market, symbol, mode, force_refresh, db=db)
        except Exception as e:
            log.error("AIOrchestrator unexpected error: %s", e, exc_info=True)
            return _build_envelope(
                market=market, symbol=symbol, ts_code=f"{symbol}.SH",
                final_analysis=dict(SAFE_PLACEHOLDER),
                review_status="rejected",
                data_quality={"score": 0, "level": "low", "issues": []},
                missing_modules=[],
                partial=True,
                errors=[f"AI 分析服务异常: {e}"],
            )

    async def _run_internal(
        self,
        market: str,
        symbol: str,
        mode: str,
        force_refresh: bool,
        db=None,
    ) -> dict:
        # Step 1: Data Agent (deterministic, optionally with RAG)
        log.info("AI Orchestrator: collecting data for %s/%s mode=%s", market, symbol, mode)
        try:
            data_pack = await self._data_agent.collect(market, symbol, mode, db=db)
        except Exception as e:
            log.error("Data Agent failed: %s", e)
            return _build_envelope(
                market=market, symbol=symbol, ts_code=f"{symbol}.SH",
                final_analysis=dict(SAFE_PLACEHOLDER),
                review_status="rejected",
                data_quality={"score": 0, "level": "low", "issues": [str(e)]},
                missing_modules=[],
                partial=True,
                errors=[f"数据收集失败: {e}"],
            )

        ts_code = data_pack.get("ts_code", f"{symbol}.SH")
        data_quality = data_pack.get("data_quality", {})
        missing = data_pack.get("missing_modules", [])

        # Step 2: Check cache (unless force_refresh)
        if not force_refresh:
            cached = await ai_cache.read_cache(ts_code, mode, data_pack)
            if cached is not None:
                log.info("AI cache HIT for %s", ts_code)
                return _build_envelope(
                    market=market, symbol=symbol, ts_code=ts_code,
                    final_analysis=cached.get("ai_analysis", {}),
                    review_status=cached.get("review", {}).get("review_status", "approved"),
                    data_quality=data_quality,
                    missing_modules=missing,
                    stale=cached.get("_stale", False),
                )

        # Step 3: Analysis Agent (LLM)
        log.info("AI Orchestrator: calling Analysis Agent for %s", ts_code)
        try:
            raw_analysis = await self._analysis_agent.analyze(data_pack, mode)
        except RuntimeError as e:
            # LLM unavailable — try stale cache
            log.warning("Analysis Agent unavailable: %s. Trying stale cache.", e)
            stale_cached = await ai_cache.read_stale_cache(ts_code, mode, data_pack)
            if stale_cached is not None:
                return _build_envelope(
                    market=market, symbol=symbol, ts_code=ts_code,
                    final_analysis=stale_cached.get("ai_analysis", {}),
                    review_status=stale_cached.get("review", {}).get("review_status", "approved"),
                    data_quality=data_quality,
                    missing_modules=missing,
                    stale=True,
                    partial=True,
                    errors=[str(e)],
                )
            # No stale cache either
            safe = dict(SAFE_PLACEHOLDER)
            return _build_envelope(
                market=market, symbol=symbol, ts_code=ts_code,
                final_analysis=safe,
                review_status="rejected",
                data_quality=data_quality,
                missing_modules=missing,
                partial=True,
                errors=[str(e)],
            )
        except ValueError as e:
            # LLM returned non-JSON
            log.error("Analysis Agent parse error: %s", e)
            safe = dict(SAFE_PLACEHOLDER)
            return _build_envelope(
                market=market, symbol=symbol, ts_code=ts_code,
                final_analysis=safe,
                review_status="rejected",
                data_quality=data_quality,
                missing_modules=missing,
                partial=True,
                errors=[f"AI 输出解析失败: {e}"],
            )

        # Step 4: Review Agent
        log.info("AI Orchestrator: calling Review Agent for %s", ts_code)
        review_result = await self._review_agent.review(raw_analysis, data_pack)
        review_status = review_result.get("review_status", "approved")
        final_analysis = review_result.get("final", {})
        review_audit = review_result.get("audit", {})

        # Step 5: Enrich source_chunks with full chunk data from rag_context
        rag_context = data_pack.get("report_rag_context", [])
        rag_meta = data_pack.get("rag_meta", {})
        rag_by_id = {c["chunk_id"]: c for c in rag_context}
        raw_source_chunks = final_analysis.get("source_chunks", [])

        enriched_chunks: list[dict] = []
        for sc in raw_source_chunks:
            cid = sc.get("chunk_id")
            if cid and cid in rag_by_id:
                full = rag_by_id[cid]
                enriched_chunks.append({
                    "chunk_id":      cid,
                    "report_id":     full.get("report_id"),
                    "ts_code":       full.get("ts_code"),
                    "report_type":   full.get("report_type"),
                    "report_year":   full.get("report_year"),
                    "period":        full.get("period"),
                    "section_title": full.get("section_title"),
                    "content":       (full.get("content") or "")[:800],
                    "score":         full.get("score"),
                    "citation":      sc.get("citation", ""),
                    "provider":      rag_meta.get("provider", "mock"),
                    "fallback_used": rag_meta.get("fallback_used", False),
                })

        # Determine rag_status for frontend
        if not rag_context:
            rag_status = "unavailable"
        elif rag_meta.get("fallback_used"):
            rag_status = "keyword_only"
        elif rag_meta.get("provider") == "local":
            rag_status = "local"
        else:
            rag_status = "mock"

        # Update final_analysis with enriched chunks and review_audit
        if enriched_chunks or rag_context or review_audit:
            final_analysis = dict(final_analysis)
            if enriched_chunks or rag_context:
                final_analysis["source_chunks"] = enriched_chunks
            if review_audit:
                final_analysis["review_audit"] = review_audit

        # Step 6: Cache (only approved/revised, never rejected)
        if review_status in ("approved", "revised"):
            cache_payload = {
                "ai_analysis": final_analysis,
                "review": {
                    "review_status": review_status,
                    "review_notes": review_result.get("review_notes", []),
                    "blocked_phrases": review_result.get("blocked_phrases", []),
                },
            }
            await ai_cache.write_cache(ts_code, mode, data_pack, cache_payload)

        return _build_envelope(
            market=market, symbol=symbol, ts_code=ts_code,
            final_analysis=final_analysis,
            review_status=review_status,
            data_quality=data_quality,
            missing_modules=missing,
            partial=(review_status == "rejected"),
            source_chunks=enriched_chunks if (enriched_chunks or rag_context) else None,
            rag_status=rag_status if rag_context else "unavailable",
        )


# Module-level singleton
_orchestrator: FundamentalAIOrchestrator | None = None

def get_ai_orchestrator() -> FundamentalAIOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = FundamentalAIOrchestrator()
    return _orchestrator
