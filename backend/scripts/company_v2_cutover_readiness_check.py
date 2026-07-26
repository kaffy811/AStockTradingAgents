from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


# Anchor to repo root (this script lives at <repo>/backend/scripts/) so doc
# checks are CWD-independent (works from repo root, backend/, or elsewhere).
_REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_DOCS = [
    str(_REPO_ROOT / "backend/docs/artifacts/company_v2_production_staged_cutover.md"),
    str(_REPO_ROOT / "backend/docs/artifacts/company_v2_phase6s_pre_cutover_gate.md"),
    str(_REPO_ROOT / "backend/docs/artifacts/company_v2_phase6s_post_cutover_smoke.md"),
    str(_REPO_ROOT / "backend/docs/artifacts/company_v2_phase6s_rollback_verification.md"),
    str(_REPO_ROOT / "backend/docs/artifacts/company_v2_phase6s_observation_window.md"),
    str(_REPO_ROOT / "backend/docs/artifacts/company_v2_production_cutover_monitoring_checklist.md"),
]


def _read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _check_smoke(smoke: dict[str, Any]) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []
    if not smoke.get("smoke_gate_pass"):
        blocking.append("production smoke gate did not pass")
    for record in smoke.get("records") or []:
        symbol = record.get("symbol")
        if int(record.get("providers_data_success") or 0) == 0:
            blocking.append(f"{symbol}: providers_data_success=0")
        if int(record.get("modules_renderable") or 0) < 8:
            blocking.append(f"{symbol}: modules_renderable<8")
        if int(record.get("strong_failed_count") or 0) > 0:
            blocking.append(f"{symbol}: strong_failed_count>0")
        if int(record.get("critical_validation_failures") or 0) > 0:
            blocking.append(f"{symbol}: critical_validation_failures>0")
        if float(record.get("data_quality_score") or 0) < 70:
            blocking.append(f"{symbol}: data_quality_score<70")
        if int(record.get("mapping_error_count") or 0) > 0:
            blocking.append(f"{symbol}: mapping_error_count>0")
        if int(record.get("render_rule_error_count") or 0) > 0:
            blocking.append(f"{symbol}: render_rule_error_count>0")
        if int(record.get("trace_missing_count") or 0) > 0:
            blocking.append(f"{symbol}: trace_missing_count>0")
        semantic = int(record.get("semantic_warning_count") or 0)
        if semantic > 0:
            warnings.append(f"{symbol}: semantic_warnings={semantic}, accepted as provider/accounting definition differences")
    return blocking, warnings


def _check_daily(daily: dict[str, Any]) -> tuple[list[str], list[str]]:
    summary = daily.get("summary") or {}
    blocking: list[str] = []
    warnings: list[str] = []
    if int(summary.get("pass_count") or 0) < 3:
        blocking.append("daily health pass_count<3")
    if int(summary.get("fail_count") or 0) != 0:
        blocking.append("daily health fail_count is not zero")
    semantic = int(summary.get("total_semantic_warnings") or 0)
    if semantic:
        warnings.append(f"semantic_warnings={semantic}, accepted as provider/accounting definition differences")
    if int(summary.get("total_strong_failures") or 0) > 0:
        blocking.append("daily health total_strong_failures>0")
    return blocking, warnings


def analyze_readiness(smoke: dict[str, Any], daily: dict[str, Any], *, docs: list[str] | None = None) -> dict[str, Any]:
    blocking: list[str] = []
    warnings: list[str] = []
    smoke_blocking, smoke_warnings = _check_smoke(smoke)
    daily_blocking, daily_warnings = _check_daily(daily)
    blocking.extend(smoke_blocking)
    blocking.extend(daily_blocking)
    warnings.extend(smoke_warnings)
    warnings.extend(daily_warnings)
    missing_docs = [doc for doc in (docs or REQUIRED_DOCS) if not Path(doc).exists()]
    blocking.extend(f"missing doc: {doc}" for doc in missing_docs)
    rollback_available = (_REPO_ROOT / "backend/docs/artifacts/company_v2_phase6s_rollback_verification.md").exists()
    legacy_available = True
    if not rollback_available:
        blocking.append("rollback verification doc missing")
    return {
        "cutover_ready": not blocking,
        "recommended_level": "Level 3 production default v2" if not blocking else "Level 0 legacy only",
        "blocking_issues": blocking,
        "warnings": list(dict.fromkeys(warnings)),
        "rollback_available": rollback_available,
        "legacy_available": legacy_available,
        "required_env_change": "VITE_COMPANY_TAB_VERSION=v2",
    }


def _write_md(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# CompanyV2 Cutover Readiness Report",
        "",
        f"- cutover_ready: {report['cutover_ready']}",
        f"- recommended_level: {report['recommended_level']}",
        f"- rollback_available: {report['rollback_available']}",
        f"- legacy_available: {report['legacy_available']}",
        f"- required_env_change: `{report['required_env_change']}`",
        "",
        "## Blocking Issues",
    ]
    if report["blocking_issues"]:
        lines.extend(f"- {item}" for item in report["blocking_issues"])
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings"])
    if report["warnings"]:
        lines.extend(f"- {item}" for item in report["warnings"])
    else:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check CompanyV2 production cutover readiness.")
    parser.add_argument("--smoke-json", required=True)
    parser.add_argument("--daily-json", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()

    report = analyze_readiness(_read_json(args.smoke_json), _read_json(args.daily_json))
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_md(Path(args.out_md), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["cutover_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
