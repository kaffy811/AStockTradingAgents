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
from app.agents.financial_runtime.contracts import IntentRoutingResult, SecurityEntity, STATUS_CLARIFICATION_REQUIRED, STATUS_SUCCESS
from app.agents.financial_runtime.planner import execution_planner, financial_context_builder
from app.agents.financial_runtime.router import intent_safety_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.official_report_entity_hints import ambiguous_official_report_entity_hint


_YEAR_RE = re.compile(r"(20\d{2}|19\d{2})\s*年?")
_REPORT_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"一季报|第一季度|q1", re.IGNORECASE), "q1"),
    (re.compile(r"三季报|第三季度|q3", re.IGNORECASE), "q3"),
    (re.compile(r"中报|半年报|半年度", re.IGNORECASE), "semi"),
    (re.compile(r"年报|年度报告|annual", re.IGNORECASE), "annual"),
]
_OFFICIAL_REPORT_PDF_RE = re.compile(
    r"官方\s*PDF|PDF\s*在哪|pdf链接|报告链接|年报链接|报告原文|年报原文|年度报告原文|这份报告.*在哪|这个报告.*在哪|这个年报|官方报告地址"
    r"|年报\s*PDF|季报\s*PDF|中报\s*PDF|年度报告\s*PDF|半年报\s*PDF|季报原文|中报原文|半年报原文|年报官方|官方年报",
    re.IGNORECASE,
)
_AMBIGUOUS_OFFICIAL_PDF_ALIASES: dict[str, list[dict[str, Any]]] = {
    "平安": [
        {"market": "CN", "symbol": "000001", "ts_code": "000001.SZ", "short_name": "平安银行"},
        {"market": "CN", "symbol": "601318", "ts_code": "601318.SH", "short_name": "中国平安"},
    ],
    "招商": [
        {"market": "CN", "symbol": "600036", "ts_code": "600036.SH", "short_name": "招商银行"},
        {"market": "CN", "symbol": "600999", "ts_code": "600999.SH", "short_name": "招商证券"},
    ],
    "茅台": [
        {"market": "CN", "symbol": "600519", "ts_code": "600519.SH", "short_name": "贵州茅台"},
    ],
}
# A bare alias must not fire when the text already contains an unambiguous
# longer company name (e.g. "中国平安" contains "平安" but is not ambiguous).
_ALIAS_LONGER_NAMES: dict[str, tuple[str, ...]] = {
    "平安": ("平安银行", "中国平安"),
    "招商": ("招商银行", "招商证券"),
    "茅台": ("贵州茅台",),
}


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
        correlation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        correlation = dict(correlation or {})
        trace_id = str(correlation.get("request_trace_id") or "") or new_id("trace")
        run_id = str(correlation.get("shadow_run_id") or "") or new_id("run")
        effective_query = normalized_query or raw_query
        request = AgentRequest(
            trace_id=trace_id,
            status="started",
            raw_query=effective_query,
            conversation_id=conversation_id,
            page_context=page_context or {},
            user_context={"user_id": user_id},
        )
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
        routing = self._routing_from_snapshot(
            trace_id=trace_id,
            raw_query=raw_query,
            normalized_query=effective_query,
            resolved_entity_snapshot=resolved_entity_snapshot,
        )
        if routing is None:
            routing = await intent_safety_router.route(db, request)
        if routing.needs_clarification:
            options = self._dedup_clarification_options(list(routing.clarification_options or []))[:5]
            return {
                "schema_version": "pi_financial_runtime_v1",
                "trace_id": trace_id,
                "run_id": run_id,
                "status": "clarification_required",
                "agent_id": official_report_pdf_manifest.agent_id,
                "turn_count": 0,
                "tool_call_count": 0,
                "events": [],
                "findings": [],
                "evidence_ids": [],
                "structured_answer": {
                    "status": "clarification_required",
                    "clarification_options": options,
                    "ambiguity_term": self._ambiguity_term(raw_query, effective_query),
                    "provider": "security_entity_resolver_hint",
                    "selection_not_performed_reason": "candidate_selection_requires_user_confirmation",
                },
                "error": None,
                "metrics": {"latency_ms": 0, "model_calls": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0},
                "shadow_input": input_snapshot,
            }
        snapshot_entity = (resolved_entity_snapshot or {}).get("primary_entity")
        is_official_report_query = self._looks_like_official_pdf_intent(raw_query, effective_query)
        if routing.intent != "official_report_pdf" and is_official_report_query:
            routing.intent = "official_report_pdf"
            if snapshot_entity and not routing.resolved_entities:
                routing.resolved_entities = [self._security_entity_from_snapshot(snapshot_entity, trace_id=trace_id)]
        if routing.intent != "official_report_pdf":
            return self._skip_result(
                trace_id=trace_id,
                run_id=run_id,
                reason_code="PI_SHADOW_INTENT_NOT_SUPPORTED",
                detected_intent=routing.intent,
                normalized_intent="official_report_pdf" if self._looks_like_official_pdf_intent(raw_query, effective_query) else routing.intent,
                input_snapshot=input_snapshot,
            )
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
        if snapshot_entity and not context_dict.get("primary_entity"):
            context_dict["primary_entity"] = snapshot_entity
        input_snapshot["financial_context_snapshot"] = self._compact_financial_context(context_dict)
        plan = execution_planner.plan(trace_id=trace_id, routing=routing, context=context)
        pi_request = PiRuntimeRequest(
            trace_id=trace_id,
            run_id=run_id,
            conversation_id=conversation_id,
            user_id=user_id,
            intent="official_report_pdf",
            entities=[asdict(entity) for entity in routing.resolved_entities] or ([snapshot_entity] if snapshot_entity else []),
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

    def _routing_from_snapshot(
        self,
        *,
        trace_id: str,
        raw_query: str,
        normalized_query: str,
        resolved_entity_snapshot: dict[str, Any] | None,
    ) -> IntentRoutingResult | None:
        if not self._looks_like_official_pdf_intent(raw_query, normalized_query):
            return None
        snapshot = resolved_entity_snapshot or {}
        if snapshot.get("ambiguity"):
            return IntentRoutingResult(
                trace_id=trace_id,
                status=STATUS_CLARIFICATION_REQUIRED,
                intent="official_report_pdf",
                intent_confidence=0.9,
                policy_class="normal",
                needs_clarification=True,
                clarification_options=list(snapshot.get("resolver_candidates") or [])[:5],
                reason="snapshot_security_entity_ambiguous",
            )
        alias_options = self._ambiguous_alias_options(raw_query, normalized_query)
        if alias_options:
            return IntentRoutingResult(
                trace_id=trace_id,
                status=STATUS_CLARIFICATION_REQUIRED,
                intent="official_report_pdf",
                intent_confidence=0.92,
                policy_class="normal",
                needs_clarification=True,
                clarification_options=alias_options,
                reason="official_pdf_alias_ambiguous",
            )
        primary = snapshot.get("primary_entity") or {}
        if not primary:
            return None
        entity = self._security_entity_from_dict(trace_id, primary)
        if not entity.symbol:
            return None
        return IntentRoutingResult(
            trace_id=trace_id,
            status=STATUS_SUCCESS,
            intent="official_report_pdf",
            intent_confidence=0.96,
            resolved_entities=[entity],
            policy_class="normal",
            needs_clarification=False,
            reason="legacy_snapshot_official_report_pdf",
        )

    def _looks_like_official_pdf_intent(self, raw_query: str, normalized_query: str | None = None) -> bool:
        text = f"{raw_query or ''}\n{normalized_query or ''}"
        return bool(_OFFICIAL_REPORT_PDF_RE.search(text))

    def _ambiguity_term(self, raw_query: str, normalized_query: str | None = None) -> str | None:
        text = f"{raw_query or ''}\n{normalized_query or ''}"
        for alias in _AMBIGUOUS_OFFICIAL_PDF_ALIASES:
            if alias in text and not any(longer in text for longer in _ALIAS_LONGER_NAMES.get(alias, ())):
                return alias
        return None

    def _dedup_clarification_options(self, options: list[Any]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for item in options:
            if not isinstance(item, dict):
                continue
            key = (str(item.get("market") or "CN"), str(item.get("symbol") or item.get("code") or ""))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(dict(item))
        return deduped

    def _ambiguous_alias_options(self, raw_query: str, normalized_query: str | None = None) -> list[dict[str, Any]]:
        text = f"{raw_query or ''}\n{normalized_query or ''}"
        for alias, options in _AMBIGUOUS_OFFICIAL_PDF_ALIASES.items():
            if alias in text:
                if any(longer in text for longer in _ALIAS_LONGER_NAMES.get(alias, ())):
                    continue
                return [dict(item) for item in options]
        hint = ambiguous_official_report_entity_hint(text)
        return [
            {
                "market": item.get("market") or "CN",
                "symbol": item.get("symbol") or "",
                "short_name": item.get("short_name") or item.get("name") or item.get("symbol") or "",
            }
            for item in (hint.get("candidates") or [])
        ]

    def _security_entity_from_dict(self, trace_id: str, data: dict[str, Any]) -> SecurityEntity:
        return SecurityEntity(
            trace_id=trace_id,
            status=STATUS_SUCCESS,
            entity_type=data.get("entity_type") or "equity",
            market=data.get("market") or "CN",
            symbol=data.get("symbol") or data.get("code") or "",
            exchange=data.get("exchange") or "",
            ts_code=data.get("ts_code") or "",
            short_name=data.get("short_name") or data.get("name") or "",
            full_name=data.get("full_name") or "",
            aliases=list(data.get("aliases") or []),
            industry=data.get("industry"),
            confidence=float(data.get("confidence") or 0.99),
            match_type=data.get("match_type") or "legacy_snapshot",
            source=data.get("source") or "legacy_snapshot",
        )

    def _skip_result(
        self,
        *,
        trace_id: str,
        reason_code: str,
        detected_intent: str,
        normalized_intent: str,
        input_snapshot: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "pi_financial_runtime_v1",
            "trace_id": trace_id,
            "run_id": run_id or new_id("run"),
            "status": "skipped",
            "agent_id": None,
            "turn_count": 0,
            "tool_call_count": 0,
            "events": [],
            "findings": [],
            "evidence_ids": [],
            "structured_answer": {
                "reason_code": reason_code,
                "detected_intent": detected_intent,
                "normalized_intent": normalized_intent,
                "eligible_agents": [official_report_pdf_manifest.agent_id] if normalized_intent == "official_report_pdf" else [],
                "selected_agent": None,
                "active_report_present": bool((input_snapshot.get("active_report") or {}).get("report_id_present")),
            },
            "error": {"code": reason_code, "message": reason_code},
            "metrics": {"latency_ms": 0, "model_calls": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0},
            "shadow_input": input_snapshot,
        }

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
        correlation: dict[str, Any] | None = None,
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
                correlation=correlation,
            )

    def compare(
        self,
        *,
        legacy: dict[str, Any],
        pi_compatible: dict[str, Any],
        case_id: str = "",
        query_type: str = "",
        side_effect_count: int = 0,
        expected_status: str | None = None,
    ) -> dict[str, Any]:
        from app.agent_runtime.shadow_taxonomy import (  # noqa: PLC0415
            assess_safety_correctness,
            normalize_status,
            status_specific_provenance_complete,
        )

        legacy_norm = self._normalize_observation(legacy)
        pi_norm = self._normalize_observation(self._pi_observation(pi_compatible))
        pi_error_code = (pi_compatible.get("error") or {}).get("code")
        normalized_legacy_status = normalize_status(legacy_norm["status"], legacy_norm.get("error_code"))
        normalized_pi_status = normalize_status(pi_norm["status"], pi_error_code)
        status_match = normalized_legacy_status == normalized_pi_status
        safety_correctness = assess_safety_correctness(
            normalized_pi_status=normalized_pi_status,
            pi_pdf_url=pi_norm["pdf_url"],
            expected_status=expected_status,
        )
        provenance_complete, provenance_missing = status_specific_provenance_complete(
            normalized_status=normalized_pi_status,
            findings=pi_compatible.get("findings") or [],
            structured_answer=pi_compatible.get("structured_answer") or {},
            evidence_ids=pi_compatible.get("evidence_ids") or [],
            error_code=pi_error_code,
            pdf_url=pi_norm["pdf_url"],
        )
        comparison = {
            "status_match": status_match,
            "normalized_legacy_status": normalized_legacy_status,
            "normalized_pi_status": normalized_pi_status,
            "behavior_match": status_match,
            "safety_correctness": safety_correctness,
            "entity_match": self._same_or_unknown(legacy_norm["symbol"], pi_norm["symbol"]),
            "year_match": self._same_or_unknown(legacy_norm["report_year"], pi_norm["report_year"]),
            "report_type_match": self._same_or_unknown(legacy_norm["report_type"], pi_norm["report_type"]),
            "source_url_match": self._same_url_or_unknown(legacy_norm["source_page_url"], pi_norm["source_page_url"]),
            "pdf_url_match": self._same_url_or_unknown(legacy_norm["pdf_url"], pi_norm["pdf_url"]),
            "provenance_complete": provenance_complete,
            "provenance_missing_fields": provenance_missing,
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
        if comparison["decision"] == "review":
            reasons = []
            if not status_match:
                reasons.append(
                    f"status_mismatch legacy={normalized_legacy_status} pi={normalized_pi_status}"
                    + (" (pi_safe)" if safety_correctness else "")
                )
            if not comparison["pdf_url_match"]:
                reasons.append("pdf_url_mismatch")
            if not provenance_complete:
                reasons.append("provenance_incomplete:" + ",".join(provenance_missing))
            if side_effect_count:
                reasons.append(f"side_effects={side_effect_count}")
            comparison["review_reasons"] = reasons
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
                "metrics": pi_compatible.get("metrics") or {},
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

    def _security_entity_from_snapshot(self, entity: dict[str, Any], *, trace_id: str) -> SecurityEntity:
        return SecurityEntity(
            trace_id=trace_id,
            status="success",
            entity_type=str(entity.get("entity_type") or "equity"),
            market=str(entity.get("market") or "CN"),
            symbol=str(entity.get("symbol") or entity.get("code") or ""),
            short_name=str(entity.get("short_name") or entity.get("name") or entity.get("symbol") or ""),
            full_name=str(entity.get("name") or entity.get("short_name") or entity.get("symbol") or ""),
            source=str(entity.get("source") or "shadow_input_snapshot"),
            confidence=1.0,
            match_type="snapshot",
        )

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
