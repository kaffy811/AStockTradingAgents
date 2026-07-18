"""Acceptance helpers for official_report_pdf Pi shadow validation."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.capability_manifest import official_report_pdf_manifest
from app.agent_runtime.contracts import utc_now
from app.agent_runtime.shadow_runner import PiCompatibleShadowRunner
from app.agent_runtime.url_utils import official_domain_verified
from app.models.analysis_report import AnalysisReport
from app.models.chat import ChatMessage, ChatSession
from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob
from app.models.report_document import ReportDocument
from app.models.watchlist_item import WatchlistItem


SHADOW_RESULT_SCHEMA_VERSION = "pi_official_report_shadow_v1"
ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "docs" / "artifacts"


@dataclass(slots=True)
class OfficialReportShadowCase:
    case_id: str
    query_type: str
    query: str
    setup_query: str | None = None
    expected_status: str | None = None
    expected_symbol: str | None = None
    expected_report_year: int | None = None
    expected_report_type: str | None = None


@dataclass(slots=True)
class ShadowSideEffectSnapshot:
    chat_sessions: int
    chat_messages: int
    chat_session_context_version_sum: int
    watchlist_items: int
    analysis_reports: int
    report_documents: int
    report_indexing_jobs: int
    financial_jobs: int
    background_tasks: int
    pool_checked_out: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def planned_official_report_shadow_cases() -> list[OfficialReportShadowCase]:
    return [
        OfficialReportShadowCase("A01", "multi_turn_current_report", "这份报告的官方 PDF 在哪里？", setup_query="贵州茅台最新财报表现如何？", expected_symbol="600519", expected_report_type="annual"),
        OfficialReportShadowCase("A02", "multi_turn_current_report", "这个年报的官方PDF链接", setup_query="五粮液最新财报表现如何？", expected_symbol="000858", expected_report_type="annual"),
        OfficialReportShadowCase("A03", "multi_turn_current_report", "这份报告原文在哪里？", setup_query="宁德时代最新财报表现如何？", expected_symbol="300750", expected_report_type="annual"),
        OfficialReportShadowCase("B01", "explicit_company_name", "五粮液2025年年度报告PDF在哪里？", expected_symbol="000858", expected_report_year=2025, expected_report_type="annual"),
        OfficialReportShadowCase("B02", "explicit_company_name", "贵州茅台2024年年报原文在哪里？", expected_symbol="600519", expected_report_year=2024, expected_report_type="annual"),
        OfficialReportShadowCase("B03", "explicit_company_name", "宁德时代最新年报PDF在哪里？", expected_symbol="300750", expected_report_type="annual"),
        OfficialReportShadowCase("B04", "explicit_company_name", "中国平安2025年年度报告PDF链接", expected_symbol="601318", expected_report_year=2025, expected_report_type="annual"),
        OfficialReportShadowCase("B05", "explicit_company_name", "平安银行2024年年报PDF在哪里？", expected_symbol="000001", expected_report_year=2024, expected_report_type="annual"),
        OfficialReportShadowCase("B06", "explicit_company_name", "招商银行2025年年度报告原文", expected_symbol="600036", expected_report_year=2025, expected_report_type="annual"),
        OfficialReportShadowCase("B07", "explicit_company_name", "比亚迪2024年官方年报链接", expected_symbol="002594", expected_report_year=2024, expected_report_type="annual"),
        OfficialReportShadowCase("C01", "explicit_stock_code", "000858的2025年报PDF在哪里？", expected_symbol="000858", expected_report_year=2025, expected_report_type="annual"),
        OfficialReportShadowCase("C02", "explicit_stock_code", "600519官方年报链接", expected_symbol="600519", expected_report_type="annual"),
        OfficialReportShadowCase("C03", "explicit_stock_code", "300750最新年度报告原文", expected_symbol="300750", expected_report_type="annual"),
        OfficialReportShadowCase("C04", "explicit_stock_code", "601318 2025年年报PDF", expected_symbol="601318", expected_report_year=2025, expected_report_type="annual"),
        OfficialReportShadowCase("C05", "explicit_stock_code", "000001 2024年度报告PDF", expected_symbol="000001", expected_report_year=2024, expected_report_type="annual"),
        OfficialReportShadowCase("C06", "explicit_stock_code", "002594官方年报链接", expected_symbol="002594", expected_report_type="annual"),
        OfficialReportShadowCase("D01", "report_type", "贵州茅台2025年中报PDF", expected_symbol="600519", expected_report_year=2025, expected_report_type="semi"),
        OfficialReportShadowCase("D02", "report_type", "五粮液2025年一季报PDF", expected_symbol="000858", expected_report_year=2025, expected_report_type="q1"),
        OfficialReportShadowCase("D03", "report_type", "中国平安2025年三季报PDF", expected_symbol="601318", expected_report_year=2025, expected_report_type="q3"),
        OfficialReportShadowCase("D04", "report_type", "宁德时代2024年中报官方PDF", expected_symbol="300750", expected_report_year=2024, expected_report_type="semi"),
        OfficialReportShadowCase("D05", "report_type", "招商银行2025年一季报原文", expected_symbol="600036", expected_report_year=2025, expected_report_type="q1"),
        OfficialReportShadowCase("E01", "ambiguity", "平安的年报PDF在哪里？", expected_status="clarification_required", expected_report_type="annual"),
        OfficialReportShadowCase("E02", "ambiguity", "茅台的年报PDF在哪里？", expected_report_type="annual"),
        OfficialReportShadowCase("F01", "missing", "不存在的公司2025年年报PDF在哪里？", expected_status="unavailable", expected_report_year=2025, expected_report_type="annual"),
        OfficialReportShadowCase("F02", "missing", "贵州茅台1900年年报PDF在哪里？", expected_symbol="600519", expected_status="unavailable", expected_report_year=1900, expected_report_type="annual"),
        OfficialReportShadowCase("F03", "missing", "尚未索引公司2025年年报PDF在哪里？", expected_status="unavailable", expected_report_year=2025, expected_report_type="annual"),
        OfficialReportShadowCase("F04", "missing", "贵州茅台2035年年报PDF在哪里？", expected_symbol="600519", expected_status="unavailable", expected_report_year=2035, expected_report_type="annual"),
        OfficialReportShadowCase("F05", "missing", "000858 1900年度报告PDF", expected_symbol="000858", expected_status="unavailable", expected_report_year=1900, expected_report_type="annual"),
        OfficialReportShadowCase("F06", "missing", "没有官方链接的报告PDF在哪里？", expected_status="unavailable", expected_report_type="annual"),
        OfficialReportShadowCase("F07", "missing", "RAG不可用时贵州茅台2024年官方年报PDF", expected_symbol="600519", expected_report_year=2024, expected_report_type="annual"),
    ]


async def capture_side_effect_snapshot(db: AsyncSession) -> ShadowSideEffectSnapshot:
    return ShadowSideEffectSnapshot(
        chat_sessions=await _count(db, ChatSession),
        chat_messages=await _count(db, ChatMessage),
        chat_session_context_version_sum=await _session_context_version_sum(db),
        watchlist_items=await _count(db, WatchlistItem),
        analysis_reports=await _count(db, AnalysisReport),
        report_documents=await _count(db, ReportDocument),
        report_indexing_jobs=0,
        financial_jobs=await _count(db, CompanyV2FinancialFusionJob),
        background_tasks=0,
        pool_checked_out=_pool_checked_out(db),
    )


def compute_pi_side_effect_count(
    before: ShadowSideEffectSnapshot,
    after: ShadowSideEffectSnapshot,
    *,
    expected_legacy_chat_message_delta: int = 2,
) -> int:
    deltas = {
        key: max(0, int(after.to_dict().get(key) or 0) - int(before.to_dict().get(key) or 0))
        for key in (
            "chat_messages",
            "chat_sessions",
            "chat_session_context_version_sum",
            "watchlist_items",
            "analysis_reports",
            "report_documents",
            "report_indexing_jobs",
            "financial_jobs",
            "background_tasks",
        )
    }
    deltas["chat_messages"] = max(0, deltas["chat_messages"] - expected_legacy_chat_message_delta)
    return sum(deltas.values())


def build_live_shadow_case_result(
    *,
    runner: PiCompatibleShadowRunner,
    case: OfficialReportShadowCase,
    legacy: dict[str, Any],
    pi_result: dict[str, Any],
    side_effect_count: int,
) -> dict[str, Any]:
    expected_legacy = {
        "status": legacy.get("status") or case.expected_status or _status_from_answer(legacy.get("answer", "")),
        "market": legacy.get("market") or "CN",
        "symbol": legacy.get("symbol") or case.expected_symbol or "",
        "company_name": legacy.get("company_name") or "",
        "report_year": legacy.get("report_year") or case.expected_report_year,
        "report_type": legacy.get("report_type") or case.expected_report_type,
        "source_page_url": legacy.get("source_page_url"),
        "pdf_url": legacy.get("pdf_url") or _first_url(legacy.get("answer", "")),
        "official_domain_verified": bool(legacy.get("official_domain_verified")) or official_domain_verified(legacy.get("pdf_url") or _first_url(legacy.get("answer", ""))),
        "latency_ms": legacy.get("latency_ms") or 0,
        "error_code": legacy.get("error_code"),
    }
    return runner.compare(
        legacy=expected_legacy,
        pi_compatible=pi_result,
        case_id=case.case_id,
        query_type=case.query_type,
        side_effect_count=side_effect_count,
    )


def summarize_shadow_results(results: list[dict[str, Any]], *, planned_samples: int) -> dict[str, Any]:
    executed = len(results)
    complete_sample = executed == planned_samples and planned_samples >= 30
    latencies = [(item.get("pi_compatible") or {}).get("latency_ms", 0) for item in results]
    deterministic = [item for item in results if (item.get("pi_compatible") or {}).get("tool_call_count", 0) <= 2]
    def rate(key: str) -> float | None:
        if not complete_sample:
            return None
        return round(sum(1 for item in results if (item.get("comparison") or {}).get(key) is True) / executed, 4)

    return {
        "schema_version": "pi_official_report_shadow_summary_v1",
        "generated_at": utc_now(),
        "agent_id": official_report_pdf_manifest.agent_id,
        "planned_samples": planned_samples,
        "executed_samples": executed,
        "accepted_samples": sum(1 for item in results if (item.get("comparison") or {}).get("decision") == "pass"),
        "scenario_counts": _scenario_counts(results),
        "metrics": {
            "status_match_rate": rate("status_match"),
            "entity_match_rate": rate("entity_match"),
            "year_match_rate": rate("year_match"),
            "report_type_match_rate": rate("report_type_match"),
            "source_url_match_rate": rate("source_url_match"),
            "url_match_rate": rate("pdf_url_match"),
            "provenance_rate": rate("provenance_complete"),
            "clarification_correctness_rate": rate("status_match"),
            "unsupported_url_count": None if not complete_sample else sum((item.get("comparison") or {}).get("unsupported_url_count", 0) for item in results),
            "side_effect_count": None if not complete_sample else sum((item.get("comparison") or {}).get("side_effect_count", 0) for item in results),
            "context_mutation_count": None if not complete_sample else sum((item.get("side_effects") or {}).get("context_mutation_count", 0) for item in results),
            "double_write_count": None if not complete_sample else sum((item.get("side_effects") or {}).get("double_write_count", 0) for item in results),
            "llm_call_count": None if not complete_sample else sum((item.get("pi_compatible") or {}).get("llm_call_count", 0) for item in results),
            "raw_500_count": None if not complete_sample else sum(1 for item in results if (item.get("legacy") or {}).get("http_status") == 500),
            "p50_latency_ms": _percentile(latencies, 0.50) if complete_sample else None,
            "p95_latency_ms": _percentile(latencies, 0.95) if complete_sample else None,
            "deterministic_llm_call_count": None if not complete_sample else sum((item.get("pi_compatible") or {}).get("llm_call_count", 0) for item in deterministic),
        },
        "browser_acceptance": {"executed": False, "passed": False, "notes": "not_run"},
        "blockers": [] if complete_sample else [f"Live shadow samples incomplete: executed {executed}/{planned_samples}."],
    }


def build_agent_gate(summary: dict[str, Any]) -> dict[str, Any]:
    metrics = summary.get("metrics") or {}
    executed = int(summary.get("executed_samples") or 0)
    passed = all([
        executed >= 30,
        (metrics.get("status_match_rate") or 0) >= 0.99,
        (metrics.get("entity_match_rate") or 0) >= 0.99,
        (metrics.get("year_match_rate") or 0) >= 0.99,
        (metrics.get("report_type_match_rate") or 0) >= 0.99,
        (metrics.get("url_match_rate") or 0) >= 0.99,
        metrics.get("provenance_rate") == 1.0,
        metrics.get("clarification_correctness_rate") == 1.0,
        metrics.get("unsupported_url_count") == 0,
        metrics.get("side_effect_count") == 0,
        metrics.get("context_mutation_count") == 0,
        metrics.get("double_write_count") == 0,
        metrics.get("deterministic_llm_call_count") == 0,
        metrics.get("raw_500_count") == 0,
        bool((summary.get("browser_acceptance") or {}).get("passed")),
    ])
    blockers = list(summary.get("blockers") or [])
    if not passed and not blockers:
        blockers.append("Gate thresholds were not fully met.")
    return {
        "agent_id": official_report_pdf_manifest.agent_id,
        "planned_samples": int(summary.get("planned_samples") or 30),
        "executed_samples": executed,
        "passed": passed,
        "recommended_for_next_authorization": passed,
        "metrics": {
            "status_match_rate": metrics.get("status_match_rate"),
            "entity_match_rate": metrics.get("entity_match_rate"),
            "year_match_rate": metrics.get("year_match_rate"),
            "report_type_match_rate": metrics.get("report_type_match_rate"),
            "source_url_match_rate": metrics.get("source_url_match_rate"),
            "url_match_rate": metrics.get("url_match_rate"),
            "provenance_rate": metrics.get("provenance_rate"),
            "clarification_correctness_rate": metrics.get("clarification_correctness_rate"),
            "unsupported_url_count": metrics.get("unsupported_url_count"),
            "side_effect_count": metrics.get("side_effect_count"),
            "context_mutation_count": metrics.get("context_mutation_count"),
            "double_write_count": metrics.get("double_write_count"),
            "raw_500_count": metrics.get("raw_500_count"),
            "p95_latency_ms": metrics.get("p95_latency_ms"),
        },
        "blockers": blockers,
    }


def build_runtime_gate(agent_gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "phase": "6V-P1.3",
        "runtime_implemented": True,
        "shadow_samples": int(agent_gate.get("executed_samples") or 0),
        "shadow_passed": bool(agent_gate.get("passed")),
        "pi_executor_enabled": False,
        "authorized_agents": [],
        "decision": "do_not_enable_pi_compatible",
        "blockers": list(agent_gate.get("blockers") or []),
    }


def write_shadow_artifacts(
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    agent_gate: dict[str, Any],
    runtime_gate: dict[str, Any],
    *,
    environment: dict[str, Any] | None = None,
    side_effects: dict[str, Any] | None = None,
    browser_acceptance_markdown: str | None = None,
) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(ARTIFACT_DIR / "pi_official_report_pdf_live_shadow_results.json", {
        "schema_version": SHADOW_RESULT_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "results": results,
    })
    _write_json(ARTIFACT_DIR / "pi_official_report_pdf_agent_gate.json", agent_gate)
    _write_json(ARTIFACT_DIR / "pi_compatible_runtime_gate.json", runtime_gate)
    _write_json(ARTIFACT_DIR / "pi_shadow_acceptance_environment.json", environment or {})
    _write_json(ARTIFACT_DIR / "pi_shadow_acceptance_side_effects.json", side_effects or {"schema_version": "pi_shadow_side_effects_v1", "cases": []})
    (ARTIFACT_DIR / "pi_official_report_pdf_live_shadow_summary.md").write_text(_summary_markdown(summary, agent_gate), encoding="utf-8")
    (ARTIFACT_DIR / "pi_shadow_browser_acceptance.md").write_text(browser_acceptance_markdown or _browser_markdown(summary), encoding="utf-8")


async def _count(db: AsyncSession, model: Any) -> int:
    try:
        return int((await db.execute(select(func.count()).select_from(model))).scalar_one() or 0)
    except Exception:
        return 0


async def _session_context_version_sum(db: AsyncSession) -> int:
    try:
        rows = (await db.execute(select(ChatSession.session_metadata))).scalars().all()
        total = 0
        for item in rows:
            if isinstance(item, dict):
                total += int(item.get("context_version") or (item.get("memory_v1") or {}).get("context_version") or 0)
        return total
    except Exception:
        return 0


def _pool_checked_out(db: AsyncSession) -> int | None:
    try:
        bind = db.get_bind()
        pool = getattr(bind, "pool", None)
        checked_out = getattr(pool, "checkedout", None)
        return int(checked_out()) if callable(checked_out) else None
    except Exception:
        return None


def _first_url(text: str | None) -> str | None:
    if not text:
        return None
    import re
    match = re.search(r"https?://[^\s)）]+", text)
    return match.group(0) if match else None


def _status_from_answer(answer: str) -> str:
    if "暂未找到" in answer or "不可用" in answer:
        return "unavailable"
    if "请选择" in answer or "澄清" in answer:
        return "clarification_required"
    return "success" if _first_url(answer) else "success"


def _scenario_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        key = item.get("query_type") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _percentile(values: list[int], fraction: float) -> int | None:
    clean = sorted(int(value or 0) for value in values)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    index = min(len(clean) - 1, max(0, round((len(clean) - 1) * fraction)))
    return clean[index]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _summary_markdown(summary: dict[str, Any], agent_gate: dict[str, Any]) -> str:
    metrics = summary.get("metrics") or {}
    return "\n".join([
        "# Pi-Compatible official_report_pdf Live Shadow Summary",
        "",
        f"- Agent: `{summary.get('agent_id')}`",
        f"- Planned samples: {summary.get('planned_samples')}",
        f"- Executed samples: {summary.get('executed_samples')}",
        f"- Accepted samples: {summary.get('accepted_samples')}",
        f"- Scenario counts: `{summary.get('scenario_counts')}`",
        f"- Status/entity/year/type/url match: `{metrics.get('status_match_rate')}` / `{metrics.get('entity_match_rate')}` / `{metrics.get('year_match_rate')}` / `{metrics.get('report_type_match_rate')}` / `{metrics.get('url_match_rate')}`",
        f"- Source URL / clarification match: `{metrics.get('source_url_match_rate')}` / `{metrics.get('clarification_correctness_rate')}`",
        f"- Provenance completeness: `{metrics.get('provenance_rate')}`",
        f"- Unsupported URL count: `{metrics.get('unsupported_url_count')}`",
        f"- Deterministic LLM calls: `{metrics.get('deterministic_llm_call_count')}`",
        f"- Latency p50/p95 ms: `{metrics.get('p50_latency_ms')}` / `{metrics.get('p95_latency_ms')}`",
        f"- Side effect count: `{metrics.get('side_effect_count')}`",
        f"- Context mutation / double writes / raw 500: `{metrics.get('context_mutation_count')}` / `{metrics.get('double_write_count')}` / `{metrics.get('raw_500_count')}`",
        f"- Browser acceptance: `{summary.get('browser_acceptance')}`",
        f"- Gate passed: `{agent_gate.get('passed')}`",
        f"- Recommended for next authorization: `{agent_gate.get('recommended_for_next_authorization')}`",
        "",
        "## Blockers",
        "",
        "\n".join(f"- {item}" for item in (agent_gate.get("blockers") or ["None"])) or "- None",
        "",
        "Production defaults remain disabled: `AGENT_EXECUTOR_MODE=legacy`, `PI_AGENT_SHADOW_ENABLED=false`, `CHAT_RUNTIME_MODE=legacy`, `authorized_agents=[]`.",
    ])


def _browser_markdown(summary: dict[str, Any]) -> str:
    browser = summary.get("browser_acceptance") or {}
    return "\n".join([
        "# Pi Shadow Browser Acceptance",
        "",
        f"- Executed: `{bool(browser.get('executed'))}`",
        f"- Passed: `{bool(browser.get('passed'))}`",
        f"- Notes: `{browser.get('notes') or 'not_run'}`",
        "",
        "Required conversations were not marked passed unless a local/staging authenticated browser session was available.",
    ])
