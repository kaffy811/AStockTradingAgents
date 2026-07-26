"""Dry-run first backfill for Company V2 financial metric provenance.

The script never performs full-market refresh by default. It inspects the same
Company V2 history payload used by the page and reports whether records already
carry financial_metric_v1 field provenance. When writes are explicitly enabled,
it delegates to the existing dashboard refresh/cache path instead of inventing a
second persistence mechanism.

Write mode is intentionally narrow:

* --apply must be present.
* --confirm-symbol must exactly match --symbol.
* --symbol and --report-year are required, so the script cannot accidentally run
  a full-market backfill.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.company_v2_history_service import build_company_history_dashboard

SENSITIVE_KEYS = {
    "database_url",
    "db_url",
    "password",
    "passwd",
    "secret",
    "token",
    "jwt",
    "api_key",
    "authorization",
}


def _row_status(module_key: str, row: dict[str, Any]) -> dict[str, Any]:
    field_provenance = row.get("field_provenance") or {}
    valued_fields = [
        key for key, value in row.items()
        if value not in (None, "")
        and not key.startswith("_")
        and key not in {
            "period",
            "disclosure_date",
            "source",
            "warnings",
            "aliases",
            "report_year",
            "quarter",
            "report_period_type",
            "value_basis",
            "source_provider",
            "source_table",
            "field_provenance",
            "financial_metric_schema_version",
        }
    ]
    missing = [field for field in valued_fields if field not in field_provenance]
    return {
        "module": module_key,
        "period": row.get("period"),
        "report_year": row.get("report_year"),
        "period_type": row.get("report_period_type") or row.get("period_type"),
        "schema_version": row.get("financial_metric_schema_version"),
        "valued_field_count": len(valued_fields),
        "provenance_field_count": len(field_provenance),
        "missing_fields": missing,
        "status": "complete" if valued_fields and not missing else ("legacy_unverified" if valued_fields else "empty"),
    }


def _validate_write_intent(args: argparse.Namespace) -> tuple[bool, list[str]]:
    """Return whether a write-capable run is allowed plus validation errors."""
    if not getattr(args, "apply", False):
        return False, []
    errors: list[str] = []
    if not getattr(args, "confirm_symbol", None):
        errors.append("CONFIRM_SYMBOL_REQUIRED")
    elif str(args.confirm_symbol).strip() != str(args.symbol).strip():
        errors.append("CONFIRM_SYMBOL_MISMATCH")
    if not getattr(args, "report_year", None):
        errors.append("REPORT_YEAR_REQUIRED")
    return not errors, errors


def _coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    requested_metrics = sum(row["valued_field_count"] for row in rows)
    verified_metrics = sum(row["provenance_field_count"] for row in rows if row["status"] == "complete")
    legacy_unverified = sum(len(row["missing_fields"]) for row in rows if row["status"] == "legacy_unverified")
    period_unknown = sum(1 for row in rows if not row.get("period") or not row.get("period_type"))
    unit_unknown = legacy_unverified
    return {
        "requested_metrics": requested_metrics,
        "available_metrics": requested_metrics,
        "verified_metrics": verified_metrics,
        "annual_exact_metrics": sum(
            row["provenance_field_count"]
            for row in rows
            if row.get("period_type") == "annual" and row["status"] == "complete"
        ),
        "legacy_unverified": legacy_unverified,
        "unit_unknown": unit_unknown,
        "period_unknown": period_unknown,
        "conflicts": 0,
        "coverage_rate": round(verified_metrics / requested_metrics, 4) if requested_metrics else 0.0,
    }


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in SENSITIVE_KEYS):
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = _redact_sensitive(item)
        return cleaned
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    write_allowed, write_errors = _validate_write_intent(args)
    should_write = bool(getattr(args, "apply", False) and write_allowed)
    dashboard = await build_company_history_dashboard(
        args.market,
        args.symbol,
        period="annual",
        start_year=args.report_year,
        end_year=args.report_year,
        force_refresh=should_write,
        include_stock_basic=True,
    )
    rows: list[dict[str, Any]] = []
    for module_key, module in (dashboard.get("modules") or {}).items():
        for row in (module or {}).get("history") or []:
            if args.limit and len(rows) >= args.limit:
                break
            if args.report_year and row.get("report_year") != args.report_year:
                continue
            rows.append(_row_status(module_key, row))
    legacy = [row for row in rows if row["status"] == "legacy_unverified"]
    complete = [row for row in rows if row["status"] == "complete"]
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "request": {
            "market": args.market,
            "symbol": args.symbol,
            "report_year": args.report_year,
            "dry_run": not getattr(args, "apply", False),
            "apply": bool(getattr(args, "apply", False)),
            "confirm_symbol": bool(getattr(args, "confirm_symbol", None)),
            "limit": args.limit,
        },
        "write_allowed": write_allowed,
        "write_validation_errors": write_errors,
        "write_performed": should_write,
        "summary": {
            "rows_checked": len(rows),
            "complete_rows": len(complete),
            "legacy_unverified_rows": len(legacy),
            "empty_rows": sum(1 for row in rows if row["status"] == "empty"),
            "proposed_write_count": 0 if not should_write else len(rows),
        },
        "coverage": _coverage(rows),
        "idempotency": {
            "safe_to_repeat": True,
            "expected_second_run_write_count": 0 if complete and not legacy else "depends_on_provider_refresh_result",
            "dedupe_key": f"{args.market}:{args.symbol}:{args.report_year}:financial_metric_v1",
        },
        "rollback": {
            "deletes_existing_values": False,
            "old_values_preserved": True,
            "mechanism": "existing Company V2 refresh/cache path; no destructive schema operation",
        },
        "actions": [
            "dry_run_only_no_writes" if not getattr(args, "apply", False) else (
                "delegated_to_build_company_history_dashboard_force_refresh" if should_write else "apply_rejected_no_writes"
            ),
            "legacy rows remain unverified until refreshed with financial_metric_v1 provenance",
        ],
        "rows": rows,
    }
    return _redact_sensitive(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="CN")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--report-year", type=int, required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true", default=True, help="Kept for compatibility; dry-run is the default.")
    parser.add_argument("--apply", action="store_true", help="Enable the write-capable path for one explicitly confirmed symbol.")
    parser.add_argument("--confirm-symbol", help="Must exactly match --symbol when --apply is used.")
    parser.add_argument("--write", dest="apply", action="store_true", help="Deprecated alias for --apply.")
    parser.add_argument("--output")
    args = parser.parse_args()
    with contextlib.redirect_stdout(sys.stderr):
        payload = asyncio.run(_run(args))
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
