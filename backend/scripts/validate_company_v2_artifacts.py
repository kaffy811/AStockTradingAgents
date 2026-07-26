from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.company_v2_data_validation_engine import validate_company_v2_envelope


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _top_checks(checks: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    priority = {"fail": 0, "warning": 1, "pass": 2, "skipped": 3}
    return sorted(checks, key=lambda check: priority.get(str(check.get("status")), 9))[:limit]


def _summary_record(path: Path, payload: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    summary = validation.get("validation_summary") or {}
    checks = validation.get("validation_checks") or []
    return {
        "input": str(path),
        "symbol": payload.get("symbol"),
        "request_id": payload.get("request_id"),
        "schema_version": payload.get("schema_version"),
        "validation_status": summary.get("status"),
        "data_quality_score": summary.get("data_quality_score"),
        "checks_total": summary.get("checks_total"),
        "checks_passed": summary.get("checks_passed"),
        "checks_warning": summary.get("checks_warning"),
        "checks_failed": summary.get("checks_failed"),
        "checks_skipped": summary.get("checks_skipped"),
        "critical_failures": summary.get("critical_failures"),
        "strong_failed_count": summary.get("strong_failed_count"),
        "weak_warning_count": summary.get("weak_warning_count"),
        "semantic_warning_count": summary.get("semantic_warning_count"),
        "skipped_due_to_context_count": summary.get("skipped_due_to_context_count"),
        "formula_context_missing_count": summary.get("formula_context_missing_count"),
        "top_validation_checks": _top_checks(checks),
    }


def _context_from_check(check: dict[str, Any], field: str | None) -> dict[str, Any]:
    for evidence in check.get("evidence") or []:
        contexts = evidence.get("formula_context") if isinstance(evidence, dict) else None
        if isinstance(contexts, list):
            for context in contexts:
                if isinstance(context, dict) and context.get("normalized_field") == field:
                    return context
            return contexts[0] if contexts and isinstance(contexts[0], dict) else {}
    return {}


def _contexts_from_check(check: dict[str, Any]) -> dict[str, dict[str, Any]]:
    for evidence in check.get("evidence") or []:
        contexts = evidence.get("formula_context") if isinstance(evidence, dict) else None
        if isinstance(contexts, list):
            return {
                str(context.get("normalized_field")): context
                for context in contexts
                if isinstance(context, dict) and context.get("normalized_field")
            }
    return {}


def _suspected_issue(check: dict[str, Any]) -> str:
    tags = set(check.get("tags") or [])
    if "PERIOD_MISMATCH" in tags:
        return "PERIOD_MISMATCH"
    if "CUMULATIVE_VS_SINGLE_PERIOD_MISMATCH" in tags:
        return "CUMULATIVE_VS_SINGLE_PERIOD_MISMATCH"
    if "DUPONT_PROVIDER_DEFINED" in tags or "ACCOUNTING_DEFINITION_DIFFERENCE" in tags:
        return "PROVIDER_ACCOUNTING_DEFINITION_DIFFERENT"
    if "CROSS_MODULE_MIXED_SOURCE" in tags or "DUPONT_CROSS_MODULE_MIXED_SOURCE" in tags:
        return "CROSS_MODULE_MIXED_SOURCE"
    if "FORMULA_CONTEXT_MISSING" in tags:
        return "VALIDATION_FORMULA_NOT_APPLICABLE"
    if check.get("status") == "fail":
        return "FIELD_MAPPING_WRONG"
    return "PROVIDER_ACCOUNTING_DEFINITION_DIFFERENT"


def _audit_records(payload: dict[str, Any], validation: dict[str, Any]) -> list[dict[str, Any]]:
    symbol = payload.get("symbol")
    records: list[dict[str, Any]] = []
    for check in validation.get("validation_checks") or []:
        if check.get("check_id") not in {"dupont_roe_formula", "net_margin_formula", "gross_margin_formula"}:
            continue
        if check.get("status") not in {"warning", "fail", "skipped"}:
            continue
        context = _context_from_check(check, check.get("field"))
        contexts = _contexts_from_check(check)
        evidence = (check.get("evidence") or [{}])[0]
        numerator_field = "net_profit" if check.get("check_id") == "net_margin_formula" else None
        denominator_field = "revenue" if check.get("check_id") == "net_margin_formula" else None
        numerator_context = contexts.get(numerator_field or "") or {}
        denominator_context = contexts.get(denominator_field or "") or {}
        records.append({
            "symbol": symbol,
            "check_id": check.get("check_id"),
            "status": check.get("status"),
            "check_strength": check.get("check_strength"),
            "tags": check.get("tags") or [],
            "expected": check.get("expected"),
            "actual": check.get("actual"),
            "relative_diff_pct": check.get("relative_diff_pct"),
            "module_key": check.get("module_key"),
            "field_name": check.get("field"),
            "source_provider": context.get("source_provider"),
            "raw_field": context.get("raw_field"),
            "normalized_field": context.get("normalized_field"),
            "period": context.get("period"),
            "stat_date": context.get("period"),
            "publish_date": context.get("publish_date"),
            "report_period_type": context.get("report_period_type"),
            "value_unit": context.get("unit"),
            "percent_scale": context.get("percent_scale"),
            "numerator_field": numerator_field,
            "denominator_field": denominator_field,
            "numerator_period": numerator_context.get("period") if numerator_field else None,
            "denominator_period": denominator_context.get("period") if denominator_field else None,
            "denominator_unit": denominator_context.get("unit") if denominator_field else None,
            "suspected_issue": _suspected_issue(check),
            "evidence": evidence,
            "recommended_fix": check.get("recommended_fix") or [],
        })
    return records


def _write_md(path: Path, records: list[dict[str, Any]]) -> None:
    semantic_tags = {
        "PERIOD_MISMATCH",
        "CUMULATIVE_VS_SINGLE_PERIOD_MISMATCH",
        "TTM_VS_QUARTER_MISMATCH",
        "PROVIDER_ACCOUNTING_DEFINITION_DIFFERENT",
        "CROSS_MODULE_MIXED_SOURCE",
        "VALIDATION_FORMULA_NOT_APPLICABLE",
        "DUPONT_PROVIDER_DEFINED",
        "DUPONT_CROSS_MODULE_MIXED_SOURCE",
        "DUPONT_FORMULA_WEAK_CHECK",
        "ACCOUNTING_DEFINITION_DIFFERENCE",
        "FORMULA_CONTEXT_MISSING",
    }
    lines = [
        "# CompanyV2 Validation Summary",
        "",
        "| Symbol | Status | Score | Checks | Pass | Warning | Fail | Strong Fail | Semantic Warning | Context Skipped | Critical |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for record in records:
        lines.append(
            "| {symbol} | {validation_status} | {data_quality_score} | {checks_total} | "
            "{checks_passed} | {checks_warning} | {checks_failed} | {strong_failed_count} | "
            "{semantic_warning_count} | {skipped_due_to_context_count} | {critical_failures} |".format(
                **record
            )
        )
    lines.extend(["", "## Strong Failures", ""])
    for record in records:
        failures = [c for c in record.get("top_validation_checks") or [] if c.get("status") == "fail" and c.get("check_strength") == "strong"]
        if failures:
            lines.append(f"### {record.get('symbol')}")
            for check in failures:
                lines.append(f"- `{check.get('check_id')}` module=`{check.get('module_key')}` diff=`{check.get('relative_diff_pct')}`")
    lines.extend(["", "## Semantic Warnings", ""])
    for record in records:
        lines.append(f"### {record.get('symbol')}")
        for check in record.get("top_validation_checks") or []:
            if check.get("status") != "warning" or not (
                check.get("check_strength") == "weak"
                or any(tag in semantic_tags for tag in check.get("tags") or [])
            ):
                continue
            lines.append(
                "- `{check_id}` `{check_strength}` `{severity}` module=`{module_key}` field=`{field}` diff=`{relative_diff_pct}` tags=`{tags}`".format(
                    check_id=check.get("check_id"),
                    check_strength=check.get("check_strength"),
                    severity=check.get("severity"),
                    module_key=check.get("module_key"),
                    field=check.get("field"),
                    relative_diff_pct=check.get("relative_diff_pct"),
                    tags=",".join(check.get("tags") or []),
                )
            )
        lines.append("")
    lines.extend(["## Skipped Due To Missing Context", ""])
    for record in records:
        lines.append(f"- {record.get('symbol')}: {record.get('skipped_due_to_context_count')} skipped, {record.get('formula_context_missing_count')} context-missing checks")
    lines.extend(["", "## Provider / Accounting Definition Differences", ""])
    lines.append("Provider-defined financial ratios are reported as semantic warnings when period/value-basis context is incomplete.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_audit(out_dir: Path, audit_records: list[dict[str, Any]]) -> None:
    json_path = out_dir / "company_v2_formula_semantics_audit.json"
    md_path = out_dir / "company_v2_formula_semantics_audit.md"
    json_path.write_text(json.dumps({"records": audit_records}, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# CompanyV2 Formula Semantics Audit",
        "",
        "| Symbol | Check | Status | Strength | Diff % | Field | Period | Issue |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    for record in audit_records:
        lines.append(
            "| {symbol} | `{check_id}` | {status} | {check_strength} | {relative_diff_pct} | {field_name} | {period} | {suspected_issue} |".format(
                **record
            )
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CompanyV2 debug artifacts.")
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()

    records: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []
    for input_path in args.inputs:
        path = Path(input_path)
        payload = _read_json(path)
        validation = validate_company_v2_envelope(payload)
        records.append(_summary_record(path, payload, validation))
        audit_records.extend(_audit_records(payload, validation))

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_md(Path(args.out_md), records)
    _write_audit(out_json.parent, audit_records)
    print(json.dumps({"records": records}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
