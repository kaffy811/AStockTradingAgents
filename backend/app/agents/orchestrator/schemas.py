"""
orchestrator/schemas.py — Phase 2E-1: Multi-Agent Orchestrator Data Structures.

All structures are plain dicts built by helper functions (not Pydantic) for
maximum flexibility and zero extra dependencies.

Canonical shapes:

TaskIntent
----------
{
    "query":          str,
    "symbol":         str,
    "market":         str,       # US | CN | HK
    "exchange":       str,       # SSE | SZSE | NASDAQ | NYSE | HKEX | SEC
    "company_name":   str,
    "need_fundamental": bool,
    "need_market":    bool,
    "need_news":      bool,
    "need_report":    bool,
    "need_rag":       bool,
    "need_quote":     bool,
    "need_kline":     bool,
    "report_year":    int | None,
    "report_type":    str,       # annual_report | quarterly_report
    "kline_period":   str,       # daily | weekly | monthly
    "kline_limit":    int,
    "risk_level":     str,       # normal | sensitive
}

AgentFinding
------------
{
    "agent_name":   str,
    "status":       str,   # success | failed | partial
    "summary":      str,
    "evidence":     list[str],
    "data_points":  list[str],
    "risk_flags":   list[str],
    "sources":      list[dict],
    "data_quality": dict,
}

EvidencePack
------------
{
    "query":        str,
    "intent":       dict,         # TaskIntent
    "findings":     list[dict],   # list[AgentFinding]
    "sources":      list[dict],
    "data_quality": dict,
    "warnings":     list[str],
}

RiskReviewResult
----------------
{
    "passed":          bool,
    "blocked":         bool,
    "issues":          list[str],
    "required_edits":  list[str],
    "compliance_notes": list[str],
}

OrchestratorResponse
--------------------
{
    "summary":            str,
    "business_analysis":  str,
    "market_analysis":    str,
    "news_analysis":      str,
    "linkage_analysis":   str,
    "risk_points":        list[str],
    "sources":            list[dict],
    "data_quality":       dict,
    "disclaimer":         str,
}
"""
from __future__ import annotations


# ── TaskIntent builder ────────────────────────────────────────────────────────

def build_task_intent(base_intent: dict, query: str) -> dict:
    """
    Enrich a base intent dict (from parse_financial_analysis_intent) with
    orchestrator-specific fields.

    Parameters
    ----------
    base_intent : output of parse_financial_analysis_intent(query)
    query       : original user query string
    """
    need_report = bool(base_intent.get("need_report"))
    need_rag    = bool(base_intent.get("need_rag"))
    need_kline  = bool(base_intent.get("need_kline"))
    need_quote  = bool(base_intent.get("need_quote"))
    need_news   = bool(base_intent.get("need_news"))

    return {
        "query":            query,
        "symbol":           base_intent.get("symbol", ""),
        "market":           base_intent.get("market", ""),
        "exchange":         base_intent.get("exchange", ""),
        "company_name":     base_intent.get("company_name", ""),
        # Orchestrator-level flags (aggregated)
        "need_fundamental": need_report or need_rag,
        "need_market":      need_kline or need_quote,
        "need_news":        need_news,
        # Raw intent flags (preserved for sub-agents)
        "need_report":      need_report,
        "need_rag":         need_rag,
        "need_quote":       need_quote,
        "need_kline":       need_kline,
        # Report metadata
        "report_year":      base_intent.get("report_year"),
        "report_type":      base_intent.get("report_type") or "annual_report",
        # Kline metadata
        "kline_period":     base_intent.get("kline_period") or "daily",
        "kline_limit":      int(base_intent.get("kline_limit") or 30),
        # Risk level
        "risk_level":       "normal",
    }


def is_complex_financial_query(intent: dict) -> bool:
    """
    Return True if the query warrants multi-agent orchestration.

    Complexity threshold: at least 2 of the following signals are active:
      • need_report  — user asks about financial reports / fundamentals
      • need_rag     — knowledge-base retrieval required
      • need_kline   — historical price / chart data requested
      • need_news    — news / event analysis requested

    Simple queries (e.g. "AAPL price today") score 0-1 and route to
    the existing FinancialAgent single-agent path.
    """
    signals = [
        bool(intent.get("need_report")),
        bool(intent.get("need_rag")),
        bool(intent.get("need_kline")),
        bool(intent.get("need_news")),
    ]
    return sum(signals) >= 2


# ── AgentFinding builder ──────────────────────────────────────────────────────

def make_agent_finding(
    agent_name: str,
    *,
    status: str = "success",
    summary: str = "",
    evidence: list | None = None,
    data_points: list | None = None,
    risk_flags: list | None = None,
    sources: list | None = None,
    data_quality: dict | None = None,
) -> dict:
    """Build a validated AgentFinding dict."""
    assert status in ("success", "failed", "partial"), f"Invalid status: {status!r}"
    return {
        "agent_name":   agent_name,
        "status":       status,
        "summary":      summary,
        "evidence":     list(evidence or []),
        "data_points":  list(data_points or []),
        "risk_flags":   list(risk_flags or []),
        "sources":      list(sources or []),
        "data_quality": dict(data_quality or {}),
    }


# ── EvidencePack builder ──────────────────────────────────────────────────────

def make_evidence_pack(
    query: str,
    intent: dict,
    findings: list[dict],
    *,
    extra_warnings: list[str] | None = None,
) -> dict:
    """
    Aggregate findings into an EvidencePack.

    Collects all sources, computes aggregate data_quality, and surfaces any
    agent-level risk_flags as pack-level warnings.
    """
    sources: list[dict] = []
    data_quality: dict = {
        "report_verified":      False,
        "market_data_available": False,
        "warnings":             list(extra_warnings or []),
    }
    warnings: list[str] = list(extra_warnings or [])

    for finding in findings:
        sources.extend(finding.get("sources", []))
        warnings.extend(finding.get("risk_flags", []))

        # Aggregate data quality signals
        for src in finding.get("sources", []):
            if src.get("verified"):
                data_quality["report_verified"] = True

        dq = finding.get("data_quality", {})
        if dq.get("market_data_available"):
            data_quality["market_data_available"] = True
        if dq.get("report_verified"):
            data_quality["report_verified"] = True

    data_quality["warnings"] = list(dict.fromkeys(warnings))  # deduplicate, preserve order

    return {
        "query":        query,
        "intent":       intent,
        "findings":     findings,
        "sources":      sources,
        "data_quality": data_quality,
        "warnings":     warnings,
    }


# ── RiskReviewResult builder ──────────────────────────────────────────────────

def make_risk_review_result(
    *,
    passed: bool = True,
    blocked: bool = False,
    issues: list[str] | None = None,
    required_edits: list[str] | None = None,
    compliance_notes: list[str] | None = None,
) -> dict:
    return {
        "passed":           passed,
        "blocked":          blocked,
        "issues":           list(issues or []),
        "required_edits":   list(required_edits or []),
        "compliance_notes": list(compliance_notes or []),
    }


# ── OrchestratorResponse builder ─────────────────────────────────────────────

_DISCLAIMER = "仅供研究参考，不构成投资建议。"


def make_orchestrator_response(
    *,
    summary: str = "",
    business_analysis: str = "",
    market_analysis: str = "",
    news_analysis: str = "",
    linkage_analysis: str = "",
    risk_points: list[str] | None = None,
    sources: list[dict] | None = None,
    data_quality: dict | None = None,
    disclaimer: str = _DISCLAIMER,
) -> dict:
    return {
        "summary":            summary,
        "business_analysis":  business_analysis,
        "market_analysis":    market_analysis,
        "news_analysis":      news_analysis,
        "linkage_analysis":   linkage_analysis,
        "risk_points":        list(risk_points or []),
        "sources":            list(sources or []),
        "data_quality":       dict(data_quality or {}),
        "disclaimer":         disclaimer,
    }


def response_to_final_answer(resp: dict) -> dict:
    """
    Convert OrchestratorResponse to the legacy final_answer wire format.

    The legacy format has an `analysis` field that concatenates
    business_analysis + market_analysis + linkage_analysis so older
    front-ends that only render `analysis` still work.
    """
    parts = [
        p for p in [
            resp.get("business_analysis", ""),
            resp.get("market_analysis", ""),
            resp.get("linkage_analysis", ""),
        ]
        if p
    ]
    analysis = "\n\n".join(parts)
    return {
        "summary":            resp.get("summary", ""),
        "analysis":           analysis,
        "business_analysis":  resp.get("business_analysis", ""),
        "market_analysis":    resp.get("market_analysis", ""),
        "news_analysis":      resp.get("news_analysis", ""),
        "linkage_analysis":   resp.get("linkage_analysis", ""),
        "data_points":        [],
        "risk_points":        resp.get("risk_points", []),
        "sources":            resp.get("sources", []),
        "data_quality":       resp.get("data_quality", {}),
        "disclaimer":         resp.get("disclaimer", _DISCLAIMER),
    }
