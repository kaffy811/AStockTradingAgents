"""Shadow runner for Pi-compatible financial runtime."""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.capability_manifest import official_report_pdf_manifest
from app.agent_runtime.contracts import PiRuntimeBudgets, PiRuntimeRequest, new_id
from app.agent_runtime.executor import PiCompatibleAgentExecutor
from app.agent_runtime.url_utils import normalize_report_url, official_domain_verified
from app.agents.financial_runtime.contracts import AgentRequest
from app.agents.financial_runtime.planner import execution_planner, financial_context_builder
from app.agents.financial_runtime.router import intent_safety_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal


_YEAR_RE = re.compile(r"(20\d{2}|19\d{2})\s*年?")
_REPORT_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"一季报|第一季度|q1", re.IGNORECASE), "q1"),
    (re.compile(r"三季报|第三季度|q3", re.IGNORECASE), "q3"),
    (re.compile(r"中报|半年报|半年度", re.IGNORECASE), "semi"),
    (re.compile(r"年报|年度报告|annual", re.IGNORECASE), "annual"),
]


class PiCompatibleShadowRunner:
    def __init__(self, *, executor: PiCompatibleAgentExecutor | None = None) -> None:
        self.executor = executor or PiCompatibleAgentExecutor()

    def enabled(self) -> bool:
        allowed = {
            item.strip()
            for item in str(getattr(settings, "pi_agent_allowed_agents", "") or "").split(",")
            if item.strip()
        }
        return (
            str(getattr(settings, "agent_executor_mode", "legacy") or "legacy").strip().lower() == "pi_compatible_shadow"
            and bool(getattr(settings, "pi_agent_shadow_enabled", False))
            and official_report_pdf_manifest.agent_id in allowed
        )

    async def run_official_report_pdf_shadow(
        self,
        *,
        raw_query: str,
        db: AsyncSession,
        user_id: str,
        conversation_id: str = "",
        normalized_query: str | None = None,
        page_context: dict[str, Any] | None = None,
        memory_context: Any = None,
        resolved_entity_snapshot: dict[str, Any] | None = None,
        output_language: str = "zh-CN",
    ) -> dict[str, Any]:
        trace_id = new_id("trace")
        effective_query = normalized_query or raw_query
        request = AgentRequest(
            trace_id=trace_id,
            status="started",
            raw_query=effective_query,
            conversation_id=conversation_id,
            page_context=page_context or {},
            user_context={"user_id": user_id},
        )
        routing = await intent_safety_router.route(db, request)
        input_snapshot = {
            "raw_query": raw_query,
            "normalized_query": effective_query,
            "conversation_id": conversation_id,
            "message_snapshot": self._message_snapshot(memory_context),
            "financial_context_snapshot": {},
            "resolved_entity_snapshot": self._compact_entity_snapshot(resolved_entity_snapshot),
            "active_report": self._active_report_snapshot(memory_context),
            "page_context": self._compact_page_context(page_context or {}),
            "output_language": output_language,
        }
        if routing.needs_clarification:
            return {
                "schema_version": "pi_financial_runtime_v1",
                "trace_id": trace_id,
                "run_id": new_id("run"),
                "status": "clarification_required",
                "agent_id": official_report_pdf_manifest.agent_id,
                "turn_count": 0,
                "tool_call_count": 0,
                "events": [],
                "findings": [],
                "evidence_ids": [],
                "structured_answer": {
                    "status": "clarification_required",
                    "clarification_options": list(routing.clarification_options or [])[:5],
                },
                "error": None,
                "metrics": {"latency_ms": 0, "model_calls": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0},
                "shadow_input": input_snapshot,
            }
        if routing.intent != "official_report_pdf":
            return {"status": "skipped", "reason": routing.intent, "trace_id": trace_id, "shadow_input": input_snapshot}
        context = financial_context_builder.build(
            trace_id=trace_id,
            routing=routing,
            page_context=page_context or {},
            memory_context=memory_context,
        )
        year = self._extract_year(raw_query) or context.active_report_year
        report_type = self._extract_report_type(raw_query) or context.active_report_type or "annual"
        context_dict = context.to_dict()
        context_dict["report_year"] = year
        context_dict["report_type"] = report_type
        input_snapshot["financial_context_snapshot"] = self._compact_financial_context(context_dict)
        plan = execution_planner.plan(trace_id=trace_id, routing=routing, context=context)
        pi_request = PiRuntimeRequest(
            trace_id=trace_id,
            run_id=new_id("run"),
            conversation_id=conversation_id,
            user_id=user_id,
            intent="official_report_pdf",
            entities=[asdict(entity) for entity in routing.resolved_entities],
            context=context_dict,
            execution_plan=plan.to_dict(),
            allowed_tools=list(official_report_pdf_manifest.allowed_tools),
            model_profile=official_report_pdf_manifest.model_profile,
            budgets=PiRuntimeBudgets(
                deadline_ms=int(getattr(settings, "pi_agent_default_deadline_ms", 5000)),
                max_turns=int(getattr(settings, "pi_agent_max_turns", 3)),
                max_tool_calls=int(getattr(settings, "pi_agent_max_tool_calls", 4)),
                max_parallel_tools=int(getattr(settings, "pi_agent_max_parallel_tools", 2)),
                max_output_tokens=1000,
            ),
            runtime_mode="shadow",
            read_only=True,
        )
        result = await self.executor.run(request=pi_request, financial_context=context)
        payload = result.to_dict()
        payload["shadow_input"] = input_snapshot
        return payload

    async def run_official_report_pdf_shadow_with_new_session(
        self,
        *,
        raw_query: str,
        user_id: str,
        conversation_id: str = "",
        normalized_query: str | None = None,
        page_context: dict[str, Any] | None = None,
        memory_context: Any = None,
        resolved_entity_snapshot: dict[str, Any] | None = None,
        output_language: str = "zh-CN",
    ) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            return await self.run_official_report_pdf_shadow(
                raw_query=raw_query,
                db=db,
                user_id=user_id,
                conversation_id=conversation_id,
                normalized_query=normalized_query,
                page_context=page_context,
                memory_context=memory_context,
                resolved_entity_snapshot=resolved_entity_snapshot,
                output_language=output_language,
            )

    def compare(
        self,
        *,
        legacy: dict[str, Any],
        pi_compatible: dict[str, Any],
        case_id: str = "",
        query_type: str = "",
        side_effect_count: int = 0,
    ) -> dict[str, Any]:
        legacy_norm = self._normalize_observation(legacy)
        pi_norm = self._normalize_observation(self._pi_observation(pi_compatible))
        status_match = legacy_norm["status"] == pi_norm["status"] or "failed" in {legacy_norm["status"], pi_norm["status"]}
        comparison = {
            "status_match": status_match,
            "entity_match": self._same_or_unknown(legacy_norm["symbol"], pi_norm["symbol"]),
            "year_match": self._same_or_unknown(legacy_norm["report_year"], pi_norm["report_year"]),
            "report_type_match": self._same_or_unknown(legacy_norm["report_type"], pi_norm["report_type"]),
            "source_url_match": self._same_url_or_unknown(legacy_norm["source_page_url"], pi_norm["source_page_url"]),
            "pdf_url_match": self._same_url_or_unknown(legacy_norm["pdf_url"], pi_norm["pdf_url"]),
            "provenance_complete": bool(pi_compatible.get("evidence_ids")) or pi_norm["status"] in {"unavailable", "clarification_required"},
            "unsupported_url_count": 0 if pi_norm["official_domain_verified"] or not pi_norm["pdf_url"] else 1,
            "side_effect_count": side_effect_count,
        }
        comparison["decision"] = "pass" if all([
            comparison["status_match"],
            comparison["entity_match"],
            comparison["year_match"],
            comparison["report_type_match"],
            comparison["source_url_match"],
            comparison["pdf_url_match"],
            comparison["provenance_complete"],
            comparison["unsupported_url_count"] == 0,
            comparison["side_effect_count"] == 0,
        ]) else "review"
        return {
            "schema_version": "pi_official_report_shadow_v1",
            "trace_id": pi_compatible.get("trace_id"),
            "case_id": case_id,
            "query_type": query_type,
            "legacy": legacy_norm,
            "pi_compatible": {
                **pi_norm,
                "latency_ms": (pi_compatible.get("metrics") or {}).get("latency_ms", 0),
                "turn_count": pi_compatible.get("turn_count", 0),
                "tool_call_count": pi_compatible.get("tool_call_count", 0),
                "llm_call_count": (pi_compatible.get("metrics") or {}).get("model_calls", 0),
                "error_code": (pi_compatible.get("error") or {}).get("code"),
            },
            "comparison": comparison,
            "event_summary": self._compact_events(pi_compatible.get("events") or []),
        }

    def _extract_year(self, raw_query: str) -> int | None:
        match = _YEAR_RE.search(raw_query or "")
        return int(match.group(1)) if match else None

    def _extract_report_type(self, raw_query: str) -> str | None:
        for pattern, report_type in _REPORT_TYPE_PATTERNS:
            if pattern.search(raw_query or ""):
                return report_type
        return None

    def _pi_observation(self, pi_compatible: dict[str, Any]) -> dict[str, Any]:
        findings = pi_compatible.get("findings") or []
        if findings:
            finding = dict(findings[0])
            finding["status"] = pi_compatible.get("status")
            return finding
        answer = pi_compatible.get("structured_answer") or {}
        return {"status": pi_compatible.get("status") or answer.get("status"), "report_type": answer.get("report_type")}

    def _normalize_observation(self, item: dict[str, Any]) -> dict[str, Any]:
        source_page_url = item.get("source_page_url") or item.get("source_url")
        pdf_url = item.get("pdf_url") or item.get("official_url")
        return {
            "status": item.get("status") or "failed",
            "market": item.get("market") or "",
            "symbol": item.get("symbol") or "",
            "company_name": item.get("company_name") or item.get("short_name") or "",
            "report_year": item.get("report_year"),
            "report_type": item.get("report_type"),
            "source_page_url": source_page_url,
            "pdf_url": pdf_url,
            "official_domain_verified": bool(item.get("official_domain_verified")) or official_domain_verified(pdf_url) or official_domain_verified(source_page_url),
            "latency_ms": int(item.get("latency_ms") or 0),
            "error_code": item.get("error_code"),
        }

    def _same_or_unknown(self, left: Any, right: Any) -> bool:
        return left in {None, ""} or right in {None, ""} or left == right

    def _same_url_or_unknown(self, left: Any, right: Any) -> bool:
        if not left or not right:
            return True
        return normalize_report_url(str(left)) == normalize_report_url(str(right))

    def _message_snapshot(self, memory_context: Any) -> list[dict[str, Any]]:
        return [
            {"role": item.get("role"), "snippet_len": len(str(item.get("snippet") or ""))}
            for item in (getattr(memory_context, "recent_messages", []) or [])[-8:]
            if isinstance(item, dict)
        ]

    def _active_report_snapshot(self, memory_context: Any) -> dict[str, Any]:
        prefs = getattr(memory_context, "user_preferences", {}) or {}
        return {
            "report_id_present": bool(prefs.get("last_report_id")),
            "report_year": prefs.get("last_report_year"),
            "report_type": prefs.get("last_report_type"),
        }

    def _compact_entity_snapshot(self, snapshot: dict[str, Any] | None) -> dict[str, Any]:
        if not snapshot:
            return {}
        return {
            "resolver_called": bool(snapshot.get("resolver_called")),
            "resolver_result_count": snapshot.get("resolver_result_count"),
            "context_source": snapshot.get("context_source"),
            "ambiguity": bool(snapshot.get("ambiguity")),
            "candidate_count": len(snapshot.get("resolver_candidates") or []),
            "primary_entity": self._compact_entity(snapshot.get("primary_entity") or {}),
        }

    def _compact_financial_context(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "active_market": context.get("active_market"),
            "active_symbol": context.get("active_symbol"),
            "active_report_id_present": bool(context.get("active_report_id")),
            "active_report_year": context.get("active_report_year"),
            "active_report_type": context.get("active_report_type"),
            "report_year": context.get("report_year"),
            "report_type": context.get("report_type"),
            "primary_entity": self._compact_entity(context.get("primary_entity") or {}),
        }

    def _compact_entity(self, entity: dict[str, Any]) -> dict[str, Any]:
        return {
            "market": entity.get("market"),
            "symbol": entity.get("symbol") or entity.get("code"),
            "ts_code": entity.get("ts_code"),
            "short_name": entity.get("short_name") or entity.get("name"),
            "source": entity.get("source"),
        }

    def _compact_page_context(self, page_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "market": page_context.get("market") or page_context.get("active_market"),
            "symbol": page_context.get("symbol") or page_context.get("active_symbol"),
            "has_report_context": bool(page_context.get("report_id") or page_context.get("active_report_id")),
        }

    def _compact_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "event_type": event.get("event_type"),
                "timestamp": event.get("timestamp"),
                "sequence": event.get("sequence"),
                "status": (event.get("payload") or {}).get("status"),
            }
            for event in events
        ]


pi_compatible_shadow_runner = PiCompatibleShadowRunner()
