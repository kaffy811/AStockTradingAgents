"""Multi-company financial-report comparison skill."""
from __future__ import annotations

import re
from typing import Any

from app.agent.report_chat_copilot_agent import _query_indexed_report_db_evidence
from app.agent.report_context import resolve_report_selection
from app.agents.chat_skills.base import BaseSkill, SkillContext, SkillResult, _DISCLAIMER
from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service
from app.services.report_financial_table_extractor_tool import report_financial_table_extractor_tool
from app.services.security_entity_resolver import SecurityEntity, security_entity_resolver


_COMPARE_RE = re.compile(r"对比|比较|相比|和.+比|比呢|哪个更好")
_PRONOUN_RE = re.compile(r"它|该股|这家公司|这只股票|该公司")
_FORMER_RE = re.compile(r"前者|第一家|第一只")
_LATTER_RE = re.compile(r"后者|第二家|第二只")
_METRICS = [
    ("revenue", "营业收入"),
    ("parent_net_profit", "归母净利润"),
    ("roe", "净资产收益率"),
    ("operating_cashflow", "经营现金流"),
    ("total_assets", "总资产"),
    ("parent_equity", "归母净资产"),
    ("eps", "基本每股收益"),
]
_METRIC_VERSION = "metric_v1"


def _entity_key(entity: dict[str, Any]) -> tuple[str, str]:
    return (str(entity.get("market") or "").upper(), str(entity.get("symbol") or ""))


def _memory_stock(context: SkillContext) -> dict[str, Any]:
    memory_context = getattr(context, "memory_context", None)
    if not memory_context:
        return {}
    for entity in getattr(memory_context, "active_entities", []) or []:
        if getattr(entity, "type", "") == "stock" and getattr(entity, "code", ""):
            return {
                "market": getattr(entity, "market", "") or "CN",
                "symbol": getattr(entity, "code", ""),
                "name": getattr(entity, "name", "") or getattr(entity, "code", ""),
                "short_name": getattr(entity, "name", "") or getattr(entity, "code", ""),
                "source": "conversation_context",
            }
    return {}


def _memory_entities(context: SkillContext) -> list[dict[str, Any]]:
    memory_context = getattr(context, "memory_context", None)
    entities: list[dict[str, Any]] = []
    if not memory_context:
        return entities
    for entity in getattr(memory_context, "active_entities", []) or []:
        if getattr(entity, "type", "") == "stock" and getattr(entity, "code", ""):
            entities.append({
                "entity_type": "equity",
                "market": getattr(entity, "market", "") or "CN",
                "symbol": getattr(entity, "code", ""),
                "short_name": getattr(entity, "name", "") or getattr(entity, "code", ""),
                "name": getattr(entity, "name", "") or getattr(entity, "code", ""),
                "source": "conversation_context",
            })
    return entities


def _append_unique(out: list[dict[str, Any]], entity: dict[str, Any], *, source: str) -> None:
    market = str(entity.get("market") or "").upper()
    symbol = str(entity.get("symbol") or "")
    if not market or not symbol:
        return
    normalized = {
        **entity,
        "market": market,
        "symbol": symbol,
        "name": entity.get("name") or entity.get("short_name") or symbol,
        "short_name": entity.get("short_name") or entity.get("name") or symbol,
        "source": source,
    }
    if _entity_key(normalized) in {_entity_key(e) for e in out}:
        return
    out.append(normalized)


async def _build_comparison_entities(message: str, context: SkillContext) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_query = str((context.metadata or {}).get("raw_query") or message or "")
    effective_query = str((context.metadata or {}).get("effective_query") or message or "")
    context_entities = _memory_entities(context)
    current_resolved = await security_entity_resolver.resolve(
        context.db,
        raw_query,
        context_entities=context_entities,
        min_confidence=0.72,
    )
    explicit_entities: list[SecurityEntity] = list(current_resolved.get("entities") or [])
    comparison_entities: list[dict[str, Any]] = []
    resolved_pronouns: dict[str, Any] = {}

    if _PRONOUN_RE.search(raw_query) and context_entities:
        _append_unique(comparison_entities, context_entities[0], source="pronoun_context")
        resolved_pronouns["it"] = context_entities[0]
    if _FORMER_RE.search(raw_query) and context_entities:
        _append_unique(comparison_entities, context_entities[0], source="ordinal_context")
        resolved_pronouns["former"] = context_entities[0]
    if _LATTER_RE.search(raw_query) and len(context_entities) >= 2:
        _append_unique(comparison_entities, context_entities[1], source="ordinal_context")
        resolved_pronouns["latter"] = context_entities[1]

    for entity in explicit_entities:
        _append_unique(comparison_entities, entity.to_hint(), source="current_query_explicit")

    if len(comparison_entities) < 2 and effective_query != raw_query:
        effective_resolved = await security_entity_resolver.resolve(
            context.db,
            effective_query,
            context_entities=context_entities,
            min_confidence=0.72,
        )
        for entity in list(effective_resolved.get("entities") or []):
            _append_unique(comparison_entities, entity.to_hint(), source="effective_query")
    else:
        effective_resolved = {"entities": [], "ambiguity": False, "candidates": []}

    if len(comparison_entities) == 1 and context_entities:
        _append_unique(comparison_entities, context_entities[0], source="context_fallback")

    diagnostics = {
        "raw_query": raw_query,
        "normalized_query": raw_query.strip(),
        "effective_query": effective_query,
        "resolver_candidates": current_resolved.get("candidates", [])[:8],
        "current_query_entities": [e.to_dict() for e in explicit_entities],
        "resolved_pronouns": resolved_pronouns,
        "context_before": {"entities": context_entities},
        "candidate_context": {"comparison_entities": comparison_entities},
        "comparison_parser_output": {
            "entities": comparison_entities,
            "comparison_type": "financial_report",
            "dimensions": ["revenue", "profitability", "cashflow"],
            "time_alignment": "latest_common_annual",
        },
        "effective_resolver_candidates": effective_resolved.get("candidates", [])[:8],
    }
    return comparison_entities[:5], diagnostics


def _last_report_id(context: SkillContext) -> int | None:
    memory_context = getattr(context, "memory_context", None)
    raw = getattr(memory_context, "user_preferences", {}).get("last_report_id") if memory_context else None
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _fmt_value(item: dict[str, Any] | None) -> str:
    if not item:
        return "暂无可靠证据"
    value = item.get("normalized_value")
    unit = str(item.get("unit") or "")
    if value is None:
        return "暂无可靠证据"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "暂无可靠证据"
    if unit == "%":
        return f"{number:.2f}%"
    if unit == "元/股":
        return f"{number:.2f} 元/股"
    if abs(number) >= 1e8:
        return f"{number / 1e8:.2f} 亿元"
    if abs(number) >= 1e4:
        return f"{number / 1e4:.2f} 万元"
    return f"{number:.2f} {unit}".strip()


async def _structured_fields_for_report(db: Any, *, selection: Any, query: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not selection.ok:
        return {}, []
    evidence = await _query_indexed_report_db_evidence(
        db=db,
        ts_code=selection.ts_code,
        report_context=selection.metadata(),
        query_text=query or "主要会计数据 财务指标 营业收入 净利润 经营现金流 ROE EPS 总资产",
        top_k=8,
    )
    chunks = evidence.get("chunks") or []
    extracted = report_financial_table_extractor_tool.extract_from_chunks(
        report_id=selection.report_id,
        chunks=chunks,
        report_year=selection.report_year,
    )
    return extracted.get("fields") or {}, chunks


class ReportComparisonSkill(BaseSkill):
    name = "report_comparison_skill"
    description = "对比两家公司正式财报中的结构化财务指标"
    intent_examples = ["它和五粮液比呢", "贵州茅台和五粮液财报对比", "和宁德时代相比"]
    required_tools: list[str] = []
    safety_level = "read_only"
    priority = 12

    def can_handle(self, message: str, context: SkillContext) -> bool:
        if not _COMPARE_RE.search(message or ""):
            return False
        return True

    async def run(self, message: str, context: SkillContext) -> SkillResult:
        raw_query = str((context.metadata or {}).get("raw_query") or message or "")
        resolved = await security_entity_resolver.resolve(
            context.db,
            raw_query,
            context_entities=_memory_entities(context),
            min_confidence=0.72,
        )
        if resolved.get("ambiguity"):
            names = "、".join(
                f"{c.get('short_name') or c.get('symbol')}（{c.get('market')}/{c.get('symbol')}）"
                for c in (resolved.get("candidates") or [])[:5]
            )
            answer = f"对比对象存在歧义，可能指：{names}。请明确选择后再比较。" + _DISCLAIMER
            return SkillResult(ok=True, skill_name=self.name, answer=answer, data={"status": "failed", "error_code": "AMBIGUOUS_SECURITY", "candidates": resolved.get("candidates", [])[:5]})
        comparison_entities, diagnostics = await _build_comparison_entities(message, context)
        comparison_input = {
            "entities": comparison_entities,
            "comparison_type": "financial_report",
            "dimensions": diagnostics["comparison_parser_output"]["dimensions"],
            "time_alignment": "latest_common_annual",
            "conversation_context_version": getattr(getattr(context, "memory_context", None), "context_version", None),
        }
        if len(comparison_entities) >= 2:
            left, right = comparison_entities[0], comparison_entities[1]
        else:
            answer = "当前没有足够上下文确认对比双方。请明确两家公司或股票代码后再比较。" + _DISCLAIMER
            diagnostics.update({
                "comparison_skill_input": comparison_input,
                "comparison_agent_input": None,
                "context_after": diagnostics.get("context_before"),
                "context_commit_reason": "not_committed_failed_entity_missing",
                "first_entity_loss_layer": "comparison_entity_merge",
            })
            return SkillResult(
                ok=True,
                skill_name=self.name,
                answer=answer,
                data={
                    "status": "failed",
                    "error_code": "COMPARE_ENTITY_MISSING",
                    "diagnostics": diagnostics,
                    "pending_context": {"last_failed_intent": "financial_report_comparison"},
                },
            )

        if left.get("symbol") == right.get("symbol"):
            answer = "对比双方解析为同一家公司，请再指定另一家公司。" + _DISCLAIMER
            diagnostics.update({
                "comparison_skill_input": comparison_input,
                "comparison_agent_input": comparison_input,
                "context_after": diagnostics.get("context_before"),
                "context_commit_reason": "not_committed_failed_same_entity",
            })
            return SkillResult(ok=True, skill_name=self.name, answer=answer, data={"status": "failed", "error_code": "COMPARE_SAME_ENTITY", "diagnostics": diagnostics})

        left_selection = await resolve_report_selection(
            db=context.db,
            market=str(left.get("market") or "CN"),
            symbol=str(left.get("symbol") or ""),
            stock_name=str(left.get("name") or ""),
            question=message,
            report_id=_last_report_id(context),
            report_types=["annual"],
        )
        right_selection = await resolve_report_selection(
            db=context.db,
            market=str(right.get("market") or "CN"),
            symbol=str(right.get("symbol") or ""),
            stock_name=str(right.get("name") or ""),
            question=message,
            report_types=["annual"],
            years=[left_selection.report_year] if left_selection.report_year else None,
        )
        if not right_selection.ok:
            right_selection = await resolve_report_selection(
                db=context.db,
                market=str(right.get("market") or "CN"),
                symbol=str(right.get("symbol") or ""),
                stock_name=str(right.get("name") or ""),
                question=message,
                report_types=["annual"],
            )

        cache_key = ""
        cached_compare = None
        if left_selection.report_id and right_selection.report_id:
            cache_key = company_v2_snapshot_cache_service.make_company_key(
                "report_compare",
                "CN",
                str(left_selection.report_id),
                str(right_selection.report_id),
                _METRIC_VERSION,
                version="v1",
            )
            cached_compare, swr_status, _ = await company_v2_snapshot_cache_service.get_swr(cache_key)
            if swr_status not in {"fresh", "stale"}:
                cached_compare = None
        if isinstance(cached_compare, dict):
            left_fields = cached_compare.get("left_fields") or {}
            right_fields = cached_compare.get("right_fields") or {}
            left_chunks = cached_compare.get("left_chunks") or []
            right_chunks = cached_compare.get("right_chunks") or []
        else:
            left_fields, left_chunks = await _structured_fields_for_report(context.db, selection=left_selection, query=message)
            right_fields, right_chunks = await _structured_fields_for_report(context.db, selection=right_selection, query=message)
            if cache_key and (left_fields or right_fields):
                await company_v2_snapshot_cache_service.set_swr(
                    cache_key,
                    {
                        "left_fields": left_fields,
                        "right_fields": right_fields,
                        "left_chunks": left_chunks,
                        "right_chunks": right_chunks,
                    },
                    fresh_ttl=15 * 60,
                    stale_ttl=30 * 60,
                )
        rows: list[dict[str, Any]] = []
        for field, label in _METRICS:
            left_item = left_fields.get(field)
            right_item = right_fields.get(field)
            rows.append({
                "field": field,
                "label": label,
                "left_value": left_item,
                "right_value": right_item,
                "evidence_ids": [
                    item.get("source_chunk_id")
                    for item in (left_item, right_item)
                    if isinstance(item, dict) and item.get("source_chunk_id")
                ],
            })

        left_name = str(left.get("name") or left.get("symbol"))
        right_name = str(right.get("name") or right.get("symbol"))
        period_note = ""
        if left_selection.report_year != right_selection.report_year:
            period_note = f"\n\n两家公司可用正式年报年份不同：{left_name} 为 {left_selection.report_year or '未知'}，{right_name} 为 {right_selection.report_year or '未知'}，下表不做同比式结论。"
        table_lines = [
            f"### {left_name} 与 {right_name} 财报核心指标对比",
            "",
            f"- {left_name}：{left_selection.title or '未找到正式年报'}（{left_selection.report_year or '未知'}）",
            f"- {right_name}：{right_selection.title or '未找到正式年报'}（{right_selection.report_year or '未知'}）",
            period_note,
            "| 指标 | " + left_name + " | " + right_name + " | 来源 |",
            "| --- | ---: | ---: | --- |",
        ]
        for row in rows:
            evidence = "正式年报结构化表格" if row["evidence_ids"] else "暂无可靠证据"
            table_lines.append(
                f"| {row['label']} | {_fmt_value(row['left_value'])} | {_fmt_value(row['right_value'])} | {evidence} |"
            )
        limitations = []
        if not left_chunks:
            limitations.append(f"{left_name} 缺少可检索的年报片段")
        if not right_chunks:
            limitations.append(f"{right_name} 缺少可检索的年报片段")
        if limitations:
            table_lines.extend(["", "**数据限制：** " + "；".join(limitations) + "。"])
        else:
            table_lines.extend([
                "",
                "**解读口径：** 表格只展示从正式报告片段中确定抽取到的字段；缺失项不填 0，也不跨年度替代。",
            ])
        answer = "\n".join(part for part in table_lines if part != "") + _DISCLAIMER
        source_chunks = left_chunks + right_chunks
        return SkillResult(
            ok=True,
            skill_name=self.name,
            answer=answer,
            tool_events=[
                self._tool_event("report_compare_select", "选择双方正式年报", "success"),
                self._tool_event("report_compare_extract", f"结构化字段对齐：{len(rows)} 项", "success"),
            ],
            data={
                "status": "completed" if source_chunks else "partial_success",
                "answer_owner": self.name,
                "left": left_selection.metadata(),
                "right": right_selection.metadata(),
                "comparison_rows": rows,
                "comparison_input": comparison_input,
                "diagnostics": {
                    **diagnostics,
                    "comparison_skill_input": comparison_input,
                    "comparison_agent_input": comparison_input,
                    "context_after": {
                        "primary_entity": comparison_entities[0],
                        "secondary_entities": comparison_entities[1:],
                    },
                    "context_commit_reason": "completed",
                },
                "source_chunks": source_chunks,
            },
            metadata={
                "answer_owner": self.name,
                "verified_financial_data": bool(source_chunks),
                "source_chunks_count": len(source_chunks),
            },
        )
