from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.company_v2_data_validation_engine import validate_company_v2_envelope

FORBIDDEN_TEXT = [
    "DATA_MODE=free：BaoStock 和 AkShare 均未返回数据",
    "请检查 ENABLE_BAOSTOCK / ENABLE_AKSHARE 配置",
    "目标价",
    "保证上涨",
]


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_local_artifact(symbol: str, artifacts_dir: Path | None = None) -> dict[str, Any] | None:
    base = artifacts_dir or (ROOT / "backend/docs/artifacts")
    for suffix in ("phase6p_recapture", "phase6p"):
        path = base / f"company_v2_debug_full_{symbol}_{suffix}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def _http_get_json(url: str, timeout: int = 60) -> tuple[int, dict[str, Any]]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return int(response.status), json.loads(body)


async def fetch_payload(
    *,
    base_url: str | None,
    market: str,
    symbol: str,
    include_raw: bool,
    force_refresh: bool,
    artifacts_dir: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    if not base_url:
        payload = _load_local_artifact(symbol, artifacts_dir=artifacts_dir)
        return (200, payload) if payload else (0, {"error": "LOCAL_ARTIFACT_NOT_FOUND"})
    query = urllib.parse.urlencode({
        "include_raw": str(include_raw).lower(),
        "force_refresh": str(force_refresh).lower(),
        "max_validation_checks": "200",
    })
    url = f"{base_url.rstrip('/')}/api/v2/company/{market}/{symbol}/debug/full?{query}"
    return await asyncio.to_thread(_http_get_json, url)


def _contains_forbidden(payload: dict[str, Any]) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False)
    return [item for item in FORBIDDEN_TEXT if item in text]


def analyze_smoke_payload(payload: dict[str, Any], *, symbol: str, http_status: int = 200) -> dict[str, Any]:
    if isinstance(payload, dict) and (
        "validation_summary" not in payload
        or "strong_failed_count" not in (payload.get("validation_summary") or {})
    ):
        validation_result = validate_company_v2_envelope(payload)
        payload = dict(payload)
        payload["validation_summary"] = validation_result["validation_summary"]
        payload["validation_checks"] = validation_result["validation_checks"]
    summary = payload.get("summary") or {}
    validation = payload.get("validation_summary") or {}
    forbidden = _contains_forbidden(payload)
    stale_ok = bool(summary.get("cache_stale_count", 0))
    failure_reasons: list[str] = []
    if http_status != 200:
        failure_reasons.append("HTTP_NOT_200")
    if payload.get("schema_version") != "2.0":
        failure_reasons.append("SCHEMA_VERSION_NOT_2")
    if int(summary.get("providers_data_success") or 0) < 1:
        failure_reasons.append("NO_PROVIDER_DATA_SUCCESS")
    if int(summary.get("modules_renderable") or 0) < 8:
        failure_reasons.append("MODULES_RENDERABLE_LT_8")
    if int(summary.get("providers_timeout") or 0) > 0 and not stale_ok:
        failure_reasons.append("PROVIDER_TIMEOUT_WITHOUT_STALE")
    if int(summary.get("mapping_error_count") or 0) > 0:
        failure_reasons.append("MAPPING_ERROR")
    if int(summary.get("render_rule_error_count") or 0) > 0:
        failure_reasons.append("RENDER_RULE_ERROR")
    if int(summary.get("trace_missing_count") or 0) > 0:
        failure_reasons.append("TRACE_MISSING")
    if int(validation.get("strong_failed_count") or 0) > 0:
        failure_reasons.append("STRONG_VALIDATION_FAILURE")
    if int(validation.get("critical_failures") or 0) > 0:
        failure_reasons.append("CRITICAL_VALIDATION_FAILURE")
    if float(validation.get("data_quality_score") or 0) < 70:
        failure_reasons.append("DATA_QUALITY_SCORE_LT_70")
    if forbidden:
        failure_reasons.append("FORBIDDEN_TEXT_FOUND")
    return {
        "symbol": symbol,
        "http_status": http_status,
        "request_id": payload.get("request_id"),
        "schema_version": payload.get("schema_version"),
        "providers_data_success": summary.get("providers_data_success", 0),
        "providers_timeout": summary.get("providers_timeout", 0),
        "modules_renderable": summary.get("modules_renderable", 0),
        "mapping_error_count": summary.get("mapping_error_count", 0),
        "render_rule_error_count": summary.get("render_rule_error_count", 0),
        "trace_missing_count": summary.get("trace_missing_count", 0),
        "validation_status": validation.get("status"),
        "data_quality_score": validation.get("data_quality_score", 0),
        "strong_failed_count": validation.get("strong_failed_count", 0),
        "semantic_warning_count": validation.get("semantic_warning_count", 0),
        "critical_validation_failures": validation.get("critical_failures", 0),
        "smoke_gate_pass": not failure_reasons,
        "failure_reasons": failure_reasons,
        "forbidden_text": forbidden,
    }


def _write_md(path: Path, records: list[dict[str, Any]]) -> None:
    lines = [
        "# CompanyV2 Production Smoke Summary",
        "",
        "| Symbol | Pass | Modules | Provider Data | Timeout | Quality | Strong Fail | Semantic Warnings | Reasons |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for record in records:
        lines.append(
            "| {symbol} | {smoke_gate_pass} | {modules_renderable} | {providers_data_success} | {providers_timeout} | "
            "{data_quality_score} | {strong_failed_count} | {semantic_warning_count} | {reasons} |".format(
                reasons=",".join(record.get("failure_reasons") or []),
                **record,
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


async def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    records: list[dict[str, Any]] = []
    for symbol in symbols:
        try:
            status, payload = await fetch_payload(
                base_url=args.base_url,
                market=args.market,
                symbol=symbol,
                include_raw=args.include_raw,
                force_refresh=args.force_refresh,
                artifacts_dir=Path(args.artifacts_dir) if args.artifacts_dir else None,
            )
        except Exception as exc:
            status, payload = 0, {"error": type(exc).__name__, "message": str(exc)[:200]}
        records.append(analyze_smoke_payload(payload, symbol=symbol, http_status=status))
    result = {
        "smoke_gate_pass": all(record["smoke_gate_pass"] for record in records),
        "records": records,
    }
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.out_md:
        _write_md(Path(args.out_md), records)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CompanyV2 production smoke gate.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--symbols", default="600519,000725,601686")
    parser.add_argument("--market", default="CN")
    parser.add_argument("--include-raw", type=_parse_bool, default=False)
    parser.add_argument("--force-refresh", type=_parse_bool, default=False)
    parser.add_argument("--out-json", default="backend/docs/artifacts/company_v2_production_smoke_summary.json")
    parser.add_argument("--out-md", default="backend/docs/artifacts/company_v2_production_smoke_summary.md")
    parser.add_argument("--artifacts-dir", default=None)
    args = parser.parse_args()
    result = asyncio.run(run_smoke(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["smoke_gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
