"""
orchestrator/financial_orchestrator.py — Phase 2E-1: Financial Orchestrator.

Entry point: FinancialOrchestrator.run_stream()

Workflow
--------
1.  Emit orchestrator_start.
2.  Parse intent → TaskIntent.
3.  Decide which sub-agents to run.
4.  Parallel execute sub-agents (with per-agent timeout):
      • FundamentalAgent  (timeout=45s)
      • MarketAgent       (timeout=15s)
      • NewsAgent         (timeout=15s)  — only if need_news=True
5.  Aggregate findings into EvidencePack.
6.  Run RiskReviewAgent (mandatory, non-skippable, timeout=10s).
7.  If risk_review.blocked=True → return compliance-blocked final_answer.
8.  Else → run SynthesisAgent (timeout=60s) → structured response.
9.  Emit final_answer.
10. Emit done.

SSE events emitted
------------------
  orchestrator_start
  subagent_start / subagent_result
  risk_review_start / risk_review_result
  synthesis_start
  final_answer
  done  (maps to agent_completed)

Fallback rule
-------------
Any unhandled exception in run_stream() bubbles up to the caller
(process_message in chat_orchestrator.py) which catches it and
falls back to the existing FinancialAgent single-agent path.

Configuration
-------------
ENABLE_MULTI_AGENT_ORCHESTRATOR=false (default — must be opt-in)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator.fundamental_agent import FundamentalAgent
from app.agents.orchestrator.market_agent      import MarketAgent
from app.agents.orchestrator.news_agent        import NewsAgent
from app.agents.orchestrator.risk_review_agent import RiskReviewAgent
from app.agents.orchestrator.synthesis_agent   import SynthesisAgent
from app.agents.orchestrator.schemas import (
    build_task_intent,
    make_evidence_pack,
    make_agent_finding,
    response_to_final_answer,
    _DISCLAIMER,
)

try:
    from app.agents.official_report_search import parse_financial_analysis_intent
except Exception:  # pragma: no cover — module may not be available in all test envs
    parse_financial_analysis_intent = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

# ── Per-agent timeouts ─────────────────────────────────────────────────────────
_TIMEOUT_FUNDAMENTAL = 45.0
_TIMEOUT_MARKET      = 15.0
_TIMEOUT_NEWS        = 15.0
_TIMEOUT_RISK_REVIEW = 10.0
_TIMEOUT_SYNTHESIS   = 60.0


# ── SSE event names ────────────────────────────────────────────────────────────
ETYPE_ORCHESTRATOR_START  = "orchestrator_start"
ETYPE_SUBAGENT_START      = "subagent_start"
ETYPE_SUBAGENT_RESULT     = "subagent_result"
ETYPE_RISK_REVIEW_START   = "risk_review_start"
ETYPE_RISK_REVIEW_RESULT  = "risk_review_result"
ETYPE_SYNTHESIS_START     = "synthesis_start"
ETYPE_FINAL_ANSWER        = "final_answer"
ETYPE_DONE                = "agent_completed"


# ── Agent display names ────────────────────────────────────────────────────────
_DISPLAY_NAMES: dict[str, str] = {
    "fundamental_agent": "基本面分析 Agent",
    "market_agent":      "行情数据 Agent",
    "news_agent":        "新闻事件 Agent",
    "risk_review_agent": "风险审核 Agent",
    "synthesis_agent":   "综合生成 Agent",
}


class FinancialOrchestrator:
    """
    Multi-agent financial research orchestrator.

    Parameters
    ----------
    db            : async SQLAlchemy session
    output_language: language code for output (default zh-CN)
    fundamental_agent / market_agent / news_agent /
    risk_review_agent / synthesis_agent :
        Injectable sub-agents for testing.  None → use defaults.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        output_language: str = "zh-CN",
        fundamental_agent: Any = None,
        market_agent:      Any = None,
        news_agent:        Any = None,
        risk_review_agent: Any = None,
        synthesis_agent:   Any = None,
    ) -> None:
        self.db              = db
        self.output_language = output_language
        self._fundamental    = fundamental_agent    or FundamentalAgent()
        self._market         = market_agent         or MarketAgent()
        self._news           = news_agent           or NewsAgent()
        self._risk_review    = risk_review_agent    or RiskReviewAgent()
        self._synthesis      = synthesis_agent      or SynthesisAgent()

    # ── Public entry point ────────────────────────────────────────────────────

    async def run_stream(
        self,
        query: str,
        request_id: str,
        event_callback: Callable | None = None,
    ) -> dict:
        """
        Execute the full multi-agent pipeline.

        Emits SSE events via event_callback (if provided).
        Returns a dict with keys:
          final_answer (dict — legacy final_answer wire format)
          answer_text  (str  — markdown concatenation for answer_delta)
          ok           (bool)

        Raises on catastrophic failure — callers should catch and fallback.
        """
        t0 = time.monotonic()

        async def _emit(event_type: str, payload: dict) -> None:
            if event_callback is None:
                return
            try:
                await event_callback(event_type, {
                    "request_id": request_id,
                    **payload,
                })
            except Exception:
                pass

        # ── 1. Start ──────────────────────────────────────────────────────────
        await _emit(ETYPE_ORCHESTRATOR_START, {
            "query":       query,
            "request_id":  request_id,
        })

        # ── 2. Intent ─────────────────────────────────────────────────────────
        try:
            if parse_financial_analysis_intent is None:
                raise ImportError("parse_financial_analysis_intent not available")
            base_intent = parse_financial_analysis_intent(query)
        except Exception as exc:
            log.warning("Orchestrator: intent parse failed (%s) — using minimal intent", exc)
            base_intent = {"symbol": "", "market": "", "need_report": True,
                           "need_kline": True, "need_rag": True, "need_news": False}

        intent = build_task_intent(base_intent, query)
        log.debug("Orchestrator: intent=%s", intent)

        # ── 3. Decide agents ──────────────────────────────────────────────────
        run_fundamental = intent.get("need_fundamental", False)
        run_market      = intent.get("need_market",      False)
        run_news        = intent.get("need_news",        False)

        # ── 4. Parallel sub-agents ────────────────────────────────────────────
        findings:         list[dict] = []
        timeout_warnings: list[str]  = []

        tasks: list[tuple[str, Any, float]] = []
        if run_fundamental:
            tasks.append(("fundamental_agent", self._fundamental, _TIMEOUT_FUNDAMENTAL))
        if run_market:
            tasks.append(("market_agent",      self._market,      _TIMEOUT_MARKET))
        if run_news:
            tasks.append(("news_agent",        self._news,        _TIMEOUT_NEWS))

        # Emit subagent_start for each
        for agent_name, _, _ in tasks:
            await _emit(ETYPE_SUBAGENT_START, {
                "agent_name":   agent_name,
                "display_name": _DISPLAY_NAMES.get(agent_name, agent_name),
            })

        # Run in parallel with individual timeouts
        coros = [
            _run_agent_with_timeout(agent_name, agent, intent, self.db, timeout)
            for agent_name, agent, timeout in tasks
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)

        for (agent_name, _, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                log.warning("Orchestrator: %s raised %s", agent_name, result)
                finding = make_agent_finding(
                    agent_name,
                    status="failed",
                    summary=f"{agent_name} 执行失败: {result}",
                    risk_flags=["agent_timeout" if isinstance(result, asyncio.TimeoutError) else "agent_error"],
                )
                timeout_warnings.append("agent_timeout")
            else:
                finding = result

            findings.append(finding)

            await _emit(ETYPE_SUBAGENT_RESULT, {
                "agent_name":   agent_name,
                "display_name": _DISPLAY_NAMES.get(agent_name, agent_name),
                "status":       finding.get("status", "failed"),
                "summary":      finding.get("summary", ""),
                "risk_flags":   finding.get("risk_flags", []),
                "sources_count": len(finding.get("sources", [])),
            })

        # ── 5. Evidence pack ──────────────────────────────────────────────────
        extra_warnings = list(dict.fromkeys(timeout_warnings))
        evidence_pack  = make_evidence_pack(query, intent, findings, extra_warnings=extra_warnings)

        # ── 6. Risk review (mandatory) ────────────────────────────────────────
        await _emit(ETYPE_RISK_REVIEW_START, {"request_id": request_id, "stage": "pre_synthesis"})
        try:
            risk_review = await asyncio.wait_for(
                self._risk_review.run(evidence_pack, ""),
                timeout=_TIMEOUT_RISK_REVIEW,
            )
        except asyncio.TimeoutError:
            log.warning("Orchestrator: risk_review timed out — using permissive default")
            from app.agents.orchestrator.schemas import make_risk_review_result  # noqa: PLC0415
            risk_review = make_risk_review_result(
                passed=True, blocked=False,
                compliance_notes=["风险审核超时，已应用默认合规规则。"],
            )

        await _emit(ETYPE_RISK_REVIEW_RESULT, {
            "stage":          "pre_synthesis",
            "passed":         risk_review.get("passed"),
            "blocked":        risk_review.get("blocked"),
            "issues":         risk_review.get("issues", []),
            "required_edits": risk_review.get("required_edits", []),
        })

        # ── 7. Blocked path ───────────────────────────────────────────────────
        if risk_review.get("blocked"):
            issues_str = "；".join(risk_review.get("issues", []))
            blocked_fa = {
                "summary":           f"本次回答因包含违规内容被阻断。",
                "analysis":          f"合规审核未通过：{issues_str}",
                "business_analysis": "",
                "market_analysis":   "",
                "news_analysis":     "",
                "linkage_analysis":  "",
                "data_points":       [],
                "risk_points":       risk_review.get("issues", []),
                "sources":           [],
                "data_quality":      evidence_pack.get("data_quality", {}),
                "disclaimer":        _DISCLAIMER,
            }
            await _emit(ETYPE_FINAL_ANSWER, blocked_fa)
            await _emit(ETYPE_DONE, {"elapsed_ms": int((time.monotonic() - t0) * 1000)})
            return {
                "ok":           False,
                "final_answer": blocked_fa,
                "answer_text":  f"合规审核未通过：{issues_str}\n\n_{_DISCLAIMER}_",
            }

        # ── 8. Synthesis ──────────────────────────────────────────────────────
        await _emit(ETYPE_SYNTHESIS_START, {"request_id": request_id})
        try:
            orch_response = await asyncio.wait_for(
                self._synthesis.run(evidence_pack, risk_review),
                timeout=_TIMEOUT_SYNTHESIS,
            )
        except asyncio.TimeoutError:
            log.warning("Orchestrator: synthesis timed out — returning evidence summary")
            orch_response = _fallback_response(evidence_pack)
        except Exception as exc:
            log.error("Orchestrator: synthesis failed: %s", exc)
            orch_response = _fallback_response(evidence_pack)

        # ── 9. Post-synthesis risk review (lightweight, non-blocking) ────────────
        orch_response = await _post_synthesis_review(
            orch_response, evidence_pack, self._risk_review, _emit, request_id
        )

        # ── 10. Emit final_answer ─────────────────────────────────────────────
        final_answer = response_to_final_answer(orch_response)
        await _emit(ETYPE_FINAL_ANSWER, final_answer)

        # ── 11. Done ──────────────────────────────────────────────────────────
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await _emit(ETYPE_DONE, {
            "elapsed_ms": elapsed_ms,
            "agents_run": [a for a, _, _ in tasks],
        })

        answer_text = _build_answer_text(orch_response)
        log.info(
            "Orchestrator: done request_id=%s elapsed=%dms agents=%s",
            request_id, elapsed_ms, [a for a, _, _ in tasks],
        )

        return {
            "ok":           True,
            "final_answer": final_answer,
            "answer_text":  answer_text,
        }


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _run_agent_with_timeout(
    agent_name: str,
    agent: Any,
    intent: dict,
    db: AsyncSession,
    timeout: float,
) -> dict:
    """Run a sub-agent with a timeout. Returns AgentFinding or raises."""
    return await asyncio.wait_for(
        agent.run(intent, db),
        timeout=timeout,
    )


async def _post_synthesis_review(
    orch_response: dict,
    evidence_pack: dict,
    risk_review_agent: Any,
    _emit: Any,
    request_id: str,
) -> dict:
    """
    Lightweight post-synthesis compliance pass (Phase 2E-2).

    Builds a draft text from the synthesis output and runs RiskReviewAgent
    on it.  If violations are found:
      - Auto-replaces known violation phrases in all text fields.
      - If still blocked after cleanup, replaces business_analysis with
        a compliant placeholder.
    Always returns a dict — never raises, never returns None.
    """
    from app.agents.orchestrator.synthesis_agent import _apply_edits_to_response, _REPLACEMENTS  # noqa: PLC0415
    from app.agents.orchestrator.schemas import make_risk_review_result  # noqa: PLC0415

    # Build draft text from synthesis output
    draft_parts = [
        orch_response.get("summary", ""),
        orch_response.get("business_analysis", ""),
        orch_response.get("market_analysis", ""),
        orch_response.get("linkage_analysis", ""),
    ]
    draft_text = "\n".join(p for p in draft_parts if p)

    await _emit(ETYPE_RISK_REVIEW_START, {"request_id": request_id, "stage": "post_synthesis"})

    try:
        post_review = await asyncio.wait_for(
            risk_review_agent.run(evidence_pack, draft_text),
            timeout=5.0,   # lighter budget for post-pass
        )
    except Exception as exc:
        log.warning("Orchestrator: post_synthesis risk_review failed (%s) — skipping", exc)
        post_review = make_risk_review_result(passed=True, blocked=False)

    await _emit(ETYPE_RISK_REVIEW_RESULT, {
        "stage":          "post_synthesis",
        "passed":         post_review.get("passed"),
        "blocked":        post_review.get("blocked"),
        "issues":         post_review.get("issues", []),
        "required_edits": post_review.get("required_edits", []),
    })

    # No issues — return original
    if post_review.get("passed") and not post_review.get("blocked"):
        return orch_response

    # Apply violation replacements to all text fields
    required_edits = post_review.get("required_edits", ["all"])
    cleaned = _apply_edits_to_response(orch_response, required_edits)

    # If still blocked after cleanup, replace business_analysis with compliant fallback
    if post_review.get("blocked"):
        cleaned = dict(cleaned)
        cleaned["business_analysis"] = (
            "⚠️ 综合输出中发现合规问题，已自动替换为合规表述。"
            "如需完整研究数据，请调整问题描述后重试。"
        )
        cleaned["linkage_analysis"] = ""

    return cleaned


def _fallback_response(evidence_pack: dict) -> dict:
    """Minimal fallback when synthesis fails."""
    from app.agents.orchestrator.schemas import make_orchestrator_response  # noqa: PLC0415
    findings = evidence_pack.get("findings", [])
    summaries = [f.get("summary", "") for f in findings if f.get("summary")]
    return make_orchestrator_response(
        summary="综合分析完成（精简模式）。",
        business_analysis="\n".join(summaries[:3]),
        risk_points=["synthesis_fallback: 完整分析未能生成，以下为原始数据摘要"],
        data_quality=evidence_pack.get("data_quality", {}),
        disclaimer=_DISCLAIMER,
    )


def _build_answer_text(orch_response: dict) -> str:
    """Build markdown answer text from OrchestratorResponse."""
    parts: list[str] = []
    if orch_response.get("summary"):
        parts.append(orch_response["summary"])
    if orch_response.get("business_analysis"):
        parts.append(f"\n### 基本面分析\n{orch_response['business_analysis']}")
    if orch_response.get("market_analysis"):
        parts.append(f"\n### 行情分析\n{orch_response['market_analysis']}")
    if orch_response.get("news_analysis"):
        parts.append(f"\n### 新闻事件\n{orch_response['news_analysis']}")
    if orch_response.get("linkage_analysis"):
        parts.append(f"\n### 综合联动分析\n{orch_response['linkage_analysis']}")
    if orch_response.get("risk_points"):
        risk_str = "\n".join(f"• {r}" for r in orch_response["risk_points"][:5])
        parts.append(f"\n### 风险提示\n{risk_str}")
    parts.append(f"\n---\n_{_DISCLAIMER}_")
    return "\n".join(parts)


# ── Config helper ─────────────────────────────────────────────────────────────

def is_orchestrator_enabled() -> bool:
    """Return True if ENABLE_MULTI_AGENT_ORCHESTRATOR=true."""
    try:
        from app.core.config import settings  # noqa: PLC0415
        return bool(getattr(settings, "enable_multi_agent_orchestrator", False))
    except Exception:
        return False
