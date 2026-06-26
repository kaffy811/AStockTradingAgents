"""
orchestrator/fundamental_agent.py — Phase 2E-1: Fundamental Analysis Sub-Agent.

Responsibilities
----------------
* Search RAG knowledge base for financial report content.
* Detect whether an official (exchange-filed) report was found.
* Return AgentFinding — never LLM output; structured evidence only.

Reuses (does NOT re-implement)
-------------------------------
* financial_rag_search   (app.agents.financial_rag_tool)
* parse_financial_analysis_intent is already done by the orchestrator upstream.

Safety rules
------------
* If the requested report year / type cannot be found in official sources,
  status=partial and risk_flags includes "official_report_not_found".
* The agent NEVER fabricates financial data — if evidence is missing, it
  says so explicitly in summary.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator.schemas import make_agent_finding

log = logging.getLogger(__name__)

AGENT_NAME = "fundamental_agent"
TIMEOUT_SECONDS = 45.0


class FundamentalAgent:
    """
    Sub-agent for fundamental / financial report analysis.

    Accepts an injectable `rag_search_fn` parameter for unit testing.
    In production the default (financial_rag_search) is used.
    """

    def __init__(self, rag_search_fn: Any = None) -> None:
        self._rag_search_fn = rag_search_fn  # None → import lazily

    async def run(
        self,
        intent: dict,
        db: AsyncSession,
        *,
        event_callback: Callable | None = None,
    ) -> dict:
        """
        Run fundamental analysis and return an AgentFinding dict.

        Parameters
        ----------
        intent        : TaskIntent dict produced by orchestrator
        db            : async DB session (passed to financial_rag_search)
        event_callback: optional async SSE event emitter

        Returns
        -------
        AgentFinding dict — never raises.
        """
        symbol      = intent.get("symbol", "")
        market      = intent.get("market", "")
        report_year = intent.get("report_year")
        report_type = intent.get("report_type", "annual_report")
        query       = intent.get("query", "")

        risk_flags:   list[str]  = []
        sources:      list[dict] = []
        data_points:  list[str]  = []
        evidence:     list[str]  = []
        data_quality: dict       = {"report_verified": False}

        if not symbol or not market:
            return make_agent_finding(
                AGENT_NAME,
                status="failed",
                summary="缺少股票代码或市场信息，无法执行基本面分析。",
                risk_flags=["missing_symbol"],
            )

        # ── RAG search ────────────────────────────────────────────────────────
        rag_results: list[dict] = []
        try:
            rag_fn = self._rag_search_fn
            if rag_fn is None:
                from app.agents.financial_rag_tool import financial_rag_search  # noqa: PLC0415
                rag_fn = financial_rag_search

            rag = await rag_fn(
                query, db,
                symbol=symbol,
                market=market,
                top_k=5,
                source_type=report_type if intent.get("need_report") else None,
                report_year=report_year,
                search_mode="keyword",   # keyword is CI-safe (no pgvector required)
            )
            if rag.get("ok"):
                rag_results = rag.get("results", [])
                for r in rag_results:
                    chunk = r.get("chunk", "")
                    if chunk:
                        evidence.append(chunk[:500])
                    meta = r.get("metadata", {})
                    src = {
                        "title":          r.get("title", ""),
                        "source_type":    r.get("source_type", ""),
                        "source":         r.get("source", ""),
                        "published_at":   r.get("published_at", ""),
                        "url":            meta.get("url", ""),
                        "verified":       bool(meta.get("verified")),
                        "source_level":   meta.get("source_level", "general"),
                        "authority_score": float(meta.get("authority_score", 0.0)),
                    }
                    sources.append(src)
                    if src["verified"]:
                        data_quality["report_verified"] = True
        except Exception as exc:
            log.warning("FundamentalAgent: RAG search failed: %s", exc)
            risk_flags.append("rag_search_failed")

        # ── Official report check ─────────────────────────────────────────────
        official_sources = [
            s for s in sources
            if s.get("source_level") == "official_exchange"
        ]
        if intent.get("need_report") and not official_sources:
            risk_flags.append("official_report_not_found")

        # ── Extract data points ────────────────────────────────────────────────
        for r in rag_results[:5]:
            chunk = r.get("chunk", "")
            if chunk:
                data_points.append(chunk[:200])

        # ── Status ───────────────────────────────────────────────────────────
        if "official_report_not_found" in risk_flags:
            year_str = f"{report_year}年" if report_year else ""
            rt_str   = "年报" if report_type == "annual_report" else "财报"
            status   = "partial"
            summary  = (
                f"未检索到 {symbol}{year_str}{rt_str} 的官方披露文件。"
                "现有分析基于已收录公开信息，不能基于未披露财报作出确定性判断。"
            )
        elif not rag_results:
            status  = "partial"
            summary = f"未找到 {symbol} 相关财务数据，基本面分析数据不足。"
            risk_flags.append("no_rag_data")
        else:
            status  = "success"
            src_names = ", ".join(
                dict.fromkeys(s.get("source", "") for s in sources[:3] if s.get("source"))
            )
            summary = (
                f"检索到 {len(rag_results)} 条 {symbol} 财务相关文档片段。"
                + (f"来源：{src_names}。" if src_names else "")
            )

        data_quality["rag_chunks_found"] = len(rag_results)

        return make_agent_finding(
            AGENT_NAME,
            status=status,
            summary=summary,
            evidence=evidence[:10],
            data_points=data_points[:10],
            risk_flags=risk_flags,
            sources=sources[:10],
            data_quality=data_quality,
        )
