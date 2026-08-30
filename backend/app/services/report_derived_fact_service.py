"""Deterministic, request-local derived financial facts for Report Chat.

Only explicitly allowlisted arithmetic is performed.  Every operand must be a
direct value in a retrieved evidence chunk from the selected report and period.
The model never supplies operands or results.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


_NUMBER = r"(?<![\d,，.])([-+]?\d[\d,，]*(?:\.\d+)?)(?![\d,，.])"
_DIRECT_LABELS = {
    "revenue": ("营业收入", "营业总收入"),
    "net_profit": ("归属于上市公司股东的净利润", "归母净利润"),
    "investing_cashflow": ("投资活动产生的现金流量净额",),
    "financing_cashflow": ("筹资活动产生的现金流量净额",),
    "total_assets": ("资产总计", "总资产"),
}
_QUESTION_METRICS = (
    (("净利率",), ("net_margin",)),
    (("投资现金流", "投资活动现金"), ("investing_cashflow",)),
    (("筹资现金流", "筹资活动现金"), ("financing_cashflow",)),
    (("资产", "负债"), ("total_assets",)),
)
_ROUNDING = "ROUND_HALF_UP_2DP"


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value).replace(",", "").replace("，", ""))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _plain(value: Decimal) -> str:
    return format(value, "f")


def _display(value: Decimal, *, unit: str) -> str:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if unit == "%":
        return f"{rounded:.2f}%"
    return f"{rounded:,.2f}"


def _metric_requested(question: str, metric: str) -> bool:
    selected: set[str] = set()
    for triggers, metrics in _QUESTION_METRICS:
        if any(trigger in question for trigger in triggers):
            selected.update(metrics)
    return metric in selected


def _direct_facts(
    chunks: list[dict[str, Any]], evidence_map: dict[str, dict[str, Any]], report_id: Any, report_year: int,
) -> dict[str, list[dict[str, Any]]]:
    chunk_labels = {
        str(chunk.get("chunk_id") or chunk.get("id")): evidence_id
        for evidence_id, chunk in evidence_map.items()
    }
    facts: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        if chunk.get("report_id") is not None and str(chunk.get("report_id")) != str(report_id):
            continue
        if chunk.get("report_year") is not None and str(chunk.get("report_year")) != str(report_year):
            continue
        evidence_id = chunk_labels.get(str(chunk.get("chunk_id") or chunk.get("id")))
        if not evidence_id:
            continue
        compact = re.sub(r"\s+", " ", str(chunk.get("content") or ""))
        currency = re.search(r"币种[：:]?\s*([^\s]+)", compact)
        if currency and not currency.group(1).startswith("人民币"):
            continue
        for metric, labels in _DIRECT_LABELS.items():
            for label in labels:
                flexible_label = r"\s*".join(re.escape(char) for char in label)
                match = re.search(
                    rf"{flexible_label}[^\d+-]{{0,45}}{_NUMBER}[^\d+-]{{0,30}}{_NUMBER}",
                    compact,
                )
                if not match:
                    continue
                current, previous = _decimal(match.group(1)), _decimal(match.group(2))
                if current is None or previous is None:
                    continue
                facts[metric] = [
                    {"metric": metric, "canonical_value": _plain(current), "unit": "CNY", "period": str(report_year), "evidence_ids": [evidence_id]},
                    {"metric": metric, "canonical_value": _plain(previous), "unit": "CNY", "period": str(report_year - 1), "evidence_ids": [evidence_id]},
                ]
                break
    return facts


def _structured_facts(
    structured_financial_data: dict[str, Any] | None,
    evidence_map: dict[str, dict[str, Any]],
    report_id: Any,
    report_year: int,
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(structured_financial_data, dict):
        return {}
    chunk_labels = {
        str(chunk.get("chunk_id") or chunk.get("id")): evidence_id
        for evidence_id, chunk in evidence_map.items()
    }
    facts: dict[str, list[dict[str, Any]]] = {}
    for field_name, item in (structured_financial_data.get("fields") or {}).items():
        if not isinstance(item, dict):
            continue
        if item.get("report_id") is not None and str(item.get("report_id")) != str(report_id):
            continue
        period_end = str(item.get("period_end") or "")
        if period_end and not period_end.startswith(str(report_year)):
            continue
        evidence_ids = item.get("source_evidence_ids") or []
        evidence_id = chunk_labels.get(str(item.get("source_chunk_id") or item.get("chunk_id") or item.get("id")))
        if evidence_id and evidence_id not in evidence_ids:
            evidence_ids = [evidence_id]
        if not evidence_ids or item.get("provenance_complete") is False:
            continue
        canonical_value = _decimal(item.get("normalized_value") or item.get("canonical_value") or item.get("raw_value"))
        if canonical_value is None:
            continue
        unit = str(item.get("unit") or "CNY")
        if unit not in {"CNY", "元"}:
            continue
        metric = {
            "revenue": "revenue",
            "parent_net_profit": "net_profit",
            "operating_cashflow": "operating_cashflow",
            "total_assets": "total_assets",
        }.get(str(field_name))
        if not metric:
            continue
        facts.setdefault(metric, []).append({
            "metric": metric,
            "canonical_value": _plain(canonical_value),
            "unit": "CNY",
            "period": str(report_year),
            "evidence_ids": list(evidence_ids),
        })
        previous_period_value = item.get("previous_period_value")
        previous_period = str(int(report_year) - 1)
        if previous_period_value is not None:
            previous_decimal = _decimal(previous_period_value)
            if previous_decimal is not None:
                facts.setdefault(metric, []).append({
                    "metric": metric,
                    "canonical_value": _plain(previous_decimal),
                    "unit": "CNY",
                    "period": previous_period,
                    "evidence_ids": [evidence_id],
                })
    return facts


def _record(metric: str, operation: str, operands: list[dict[str, Any]], result: Decimal, unit: str) -> dict[str, Any]:
    evidence_ids = list(dict.fromkeys(eid for operand in operands for eid in operand["evidence_ids"]))
    display = _display(result, unit=unit)
    return {
        "derived_fact_id": "",
        "metric": metric,
        "operation": operation,
        "formula_type": "ratio_percentage" if operation == "ratio" and unit == "%" else operation,
        "operands": operands,
        "canonical_result": _plain(result),
        "display_result": display,
        "display_unit": unit,
        "rounding_policy": _ROUNDING,
        "evidence_ids": evidence_ids,
        "validation_tokens": list(dict.fromkeys([_plain(result), display])),
    }


def build_report_derived_facts(
    *, question: str, report_id: Any, report_year: Any,
    chunks: list[dict[str, Any]], evidence_map: dict[str, dict[str, Any]],
    structured_financial_data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build allowlisted derived facts from direct, same-report evidence only."""
    try:
        year = int(report_year)
    except (TypeError, ValueError):
        return []
    direct = _structured_facts(structured_financial_data, evidence_map, report_id, year)
    for metric, items in _direct_facts(chunks, evidence_map, report_id, year).items():
        direct.setdefault(metric, [])
        direct[metric].extend(item for item in items if item not in direct[metric])
    records: list[dict[str, Any]] = []

    if _metric_requested(question, "net_margin"):
        profit = next((item for item in direct.get("net_profit", []) if item["period"] == str(year)), None)
        revenue = next((item for item in direct.get("revenue", []) if item["period"] == str(year)), None)
        if profit and revenue and profit["unit"] == revenue["unit"]:
            denominator = _decimal(revenue["canonical_value"])
            numerator = _decimal(profit["canonical_value"])
            if numerator is not None and denominator not in {None, Decimal("0")}:
                records.append(_record("net_margin", "ratio", [profit, revenue], numerator / denominator * Decimal("100"), "%"))

    for metric in ("investing_cashflow", "financing_cashflow", "total_assets"):
        if not _metric_requested(question, metric):
            continue
        values = direct.get(metric, [])
        current = next((item for item in values if item["period"] == str(year)), None)
        previous = next((item for item in values if item["period"] == str(year - 1)), None)
        if not current or not previous or current["unit"] != previous["unit"]:
            continue
        current_value = _decimal(current["canonical_value"])
        previous_value = _decimal(previous["canonical_value"])
        if current_value is None or previous_value is None:
            continue
        records.append(_record(f"{metric}_difference", "difference", [current, previous], current_value - previous_value, "CNY"))
        if metric == "total_assets" and previous_value != 0:
            records.append(_record(f"{metric}_percentage_change", "percentage_change", [current, previous], (current_value - previous_value) / abs(previous_value) * Decimal("100"), "%"))

    for index, record in enumerate(records, start=1):
        record["derived_fact_id"] = f"C{index}"
        record["report_id"] = report_id
        record["report_year"] = year
    return records


def compile_derived_fact_validation_corpus(derived_facts: list[dict[str, Any]]) -> str:
    """Compile only exact backend-generated canonical/display tokens."""
    tokens: list[str] = []
    for fact in derived_facts:
        tokens.extend(str(value) for value in fact.get("validation_tokens", []) if str(value).strip())
    return " ".join(dict.fromkeys(tokens))


def _formula_span(text: str, start: int, end: int) -> str:
    left = max(text.rfind(mark, 0, start) for mark in ("。", "！", "？", "\n")) + 1
    stops = [pos for mark in ("。", "！", "？", "\n") if (pos := text.find(mark, end)) >= 0]
    right = min(stops) + 1 if stops else len(text)
    return text[left:right]


def derived_fact_has_canonical_operands(
    fact: dict[str, Any], canonical_evidence_map: dict[str, dict[str, Any]],
) -> bool:
    evidence_ids = list(fact.get("evidence_ids") or [])
    operands = list(fact.get("operands") or [])
    if not evidence_ids or not operands or any(eid not in canonical_evidence_map for eid in evidence_ids):
        return False
    fact_year = str(fact.get("report_year") or "")
    canonical_text = " ".join(
        str(canonical_evidence_map[eid].get("content") or "") for eid in evidence_ids
    ).replace(",", "").replace("，", "")
    for operand in operands:
        if str(operand.get("period") or "") != fact_year:
            return False
        if str(operand.get("canonical_value") or "").replace(",", "") not in canonical_text:
            return False
    return True


def validate_numeric_claims_with_derived_formula_scales(
    text: str,
    evidence_text: str,
    derived_facts: list[dict[str, Any]],
    canonical_evidence_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Validate numerics while allowing only bound percentage scale constants.

    The global validator remains unchanged.  A rejected ``100``/``100%`` is
    removed from this request-local result only when its sentence is an
    explicit formula explanation for a validated ratio-percentage fact.
    """
    from app.agents.specialist_analysis_utils import validate_numeric_claims

    result = dict(validate_numeric_claims(text, evidence_text))
    unsupported = list(result.get("unsupported_tokens") or [])
    if not unsupported or any(token not in {"100", "100%"} for token in unsupported):
        return result

    eligible_facts = [
        fact for fact in derived_facts
        if fact.get("formula_type") == "ratio_percentage"
        and derived_fact_has_canonical_operands(fact, canonical_evidence_map)
    ]
    if not eligible_facts:
        return result

    occurrences = list(re.finditer(r"(?<![\d.])100%?(?![\d.])", text))
    if len(occurrences) != len(unsupported):
        return result
    for occurrence in occurrences:
        span = _formula_span(text, occurrence.start(), occurrence.end())
        explicit_formula = bool(
            re.search(r"(?:每\s*100\s*元|[×xX*]\s*100\s*%?)", span)
        )
        if not explicit_formula:
            return result
        if not any(
            any(str(token).replace(",", "") in span.replace(",", "") for token in fact.get("validation_tokens", []))
            for fact in eligible_facts
        ):
            return result

    result.update(valid=True, reason="ok", unsupported_tokens=[], replaced_count=0)
    return result


def model_visible_derived_facts(derived_facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the bounded prompt contract without raw database identifiers."""
    return [{key: value for key, value in fact.items() if key not in {"validation_tokens", "report_id"}} for fact in derived_facts]


def derived_fact_usage(answer: str, derived_facts: list[dict[str, Any]]) -> list[str]:
    """Identify facts whose exact approved display/canonical token is in answer."""
    used: list[str] = []
    normalized_answer = str(answer or "").replace(",", "")
    for fact in derived_facts:
        if any(str(token).replace(",", "") in normalized_answer for token in fact.get("validation_tokens", [])):
            used.append(str(fact["derived_fact_id"]))
    return used
