"""Phase 6T-Q same-region HTTP acceptance for Company V2 financial fusion."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable

import httpx
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob
from app.models.report_document import ReportDocument
from app.services.company_v2_financial_evidence_fusion_service import DEFAULT_FUSION_FIELDS


ARTIFACT_DIR = ROOT / "docs" / "artifacts"
DEFAULT_SYMBOLS = ["601686", "600519", "300750", "000725", "000001"]
DEFAULT_FIELDS = list(DEFAULT_FUSION_FIELDS)
SENSITIVE_KEY_PARTS = {
    "database_url",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "private_key",
    "ssh",
    "dsn",
}
PRIVATE_PATH_KEYS = {"local_path", "path", "sidecar_path"}


class Phase6TQAcceptanceError(RuntimeError):
    def __init__(self, code: str, message: str, *, context: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.context = context or {}


@dataclass(slots=True)
class ReportRef:
    symbol: str
    report_id: int
    report_year: int | None
    report_type: str | None
    ts_code: str | None


def _parse_symbols(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if percentile <= 0:
        return round(min(values), 3)
    if percentile >= 100:
        return round(max(values), 3)
    ordered = sorted(float(item) for item in values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * (percentile / 100.0)
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    if lower_index == upper_index:
        return round(lower_value, 3)
    weight = position - lower_index
    return round(lower_value + (upper_value - lower_value) * weight, 3)


def _sanitize(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for child_key, child_value in value.items():
            lowered = child_key.lower()
            if lowered in PRIVATE_PATH_KEYS:
                continue
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                sanitized[child_key] = "[redacted]"
                continue
            sanitized[child_key] = _sanitize(child_value, key=child_key)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item, key=key) for item in value]
    if isinstance(value, str):
        if key and key.lower() in PRIVATE_PATH_KEYS:
            return "[redacted]"
        if value.startswith("/Users/") or value.startswith("/private/") or value.startswith("/tmp/"):
            return "[redacted]"
    return value


def _padded_job_field() -> list[str]:
    return list(DEFAULT_FIELDS)


def _report_sort_key(doc: ReportDocument) -> tuple[int, int]:
    return (int(doc.report_year or 0), int(doc.id or 0))


async def _resolve_symbol_reports(
    symbols: list[str],
    *,
    session_factory: Callable[[], Any] = AsyncSessionLocal,
) -> dict[str, ReportRef]:
    resolved: dict[str, ReportRef] = {}
    async with session_factory() as db:
        for symbol in symbols:
            result = await db.execute(select(ReportDocument).where(ReportDocument.ts_code.like(f"{symbol}.%")))
            docs = list(result.scalars().all())
            annuals = [doc for doc in docs if (doc.report_type or "").lower() == "annual"]
            pool = annuals or docs
            if not pool:
                raise Phase6TQAcceptanceError(
                    "REPORT_NOT_FOUND",
                    f"no report document found for symbol {symbol}",
                    context={"symbol": symbol},
                )
            doc = sorted(pool, key=_report_sort_key, reverse=True)[0]
            resolved[symbol] = ReportRef(
                symbol=symbol,
                report_id=int(doc.id),
                report_year=int(doc.report_year or 0) if doc.report_year is not None else None,
                report_type=doc.report_type,
                ts_code=doc.ts_code,
            )
    return resolved


async def _list_active_jobs(*, session_factory: Callable[[], Any] = AsyncSessionLocal) -> list[dict[str, Any]]:
    async with session_factory() as db:
        result = await db.execute(
            select(CompanyV2FinancialFusionJob).where(
                CompanyV2FinancialFusionJob.status.in_(["queued", "running"])
            ).order_by(CompanyV2FinancialFusionJob.created_at.asc())
        )
        rows = list(result.scalars().all())
    return [
        {
            "job_id": row.job_id,
            "symbol": row.symbol,
            "report_id": row.report_id,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def _load_known_jobs(
    job_ids: list[str],
    *,
    session_factory: Callable[[], Any] = AsyncSessionLocal,
) -> list[dict[str, Any]]:
    if not job_ids:
        return []
    async with session_factory() as db:
        result = await db.execute(
            select(CompanyV2FinancialFusionJob).where(CompanyV2FinancialFusionJob.job_id.in_(job_ids))
        )
        rows = list(result.scalars().all())
    return [
        {
            "job_id": row.job_id,
            "symbol": row.symbol,
            "report_id": row.report_id,
            "status": row.status,
        }
        for row in rows
    ]


async def _cancel_job_http(client: httpx.AsyncClient, *, symbol: str, job_id: str) -> dict[str, Any]:
    response = await client.post(f"/api/v2/company/CN/{symbol}/financial-fusion/jobs/{job_id}/cancel")
    data = response.json()
    if response.status_code != 200 or not data.get("ok") or data.get("status") != "cancelled":
        raise Phase6TQAcceptanceError(
            "CANCEL_FAILED",
            f"cancel failed for {job_id}",
            context={"job_id": job_id, "symbol": symbol, "status_code": response.status_code, "body": _sanitize(data)},
        )
    return _sanitize(data)


async def _cleanup_created_jobs(
    client: httpx.AsyncClient,
    created_jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cancelled: list[dict[str, Any]] = []
    for item in created_jobs:
        try:
            cancelled.append(await _cancel_job_http(client, symbol=item["symbol"], job_id=item["job_id"]))
        except Phase6TQAcceptanceError:
            continue
    return cancelled


async def _sample_once(
    client: httpx.AsyncClient,
    *,
    symbol: str,
    report: ReportRef,
    fields: list[str],
    refresh: bool,
    sample_kind: str,
) -> dict[str, Any]:
    payload = {
        "report_id": int(report.report_id),
        "fields": list(fields),
        "refresh": bool(refresh),
    }
    started = perf_counter()
    response = await client.post(f"/api/v2/company/CN/{symbol}/financial-fusion/jobs", json=payload)
    create_elapsed_ms = round((perf_counter() - started) * 1000, 3)
    body = response.json()
    if response.status_code != 202:
        raise Phase6TQAcceptanceError(
            "CREATE_NOT_ACCEPTED",
            f"create returned {response.status_code} for {symbol}",
            context={
                "symbol": symbol,
                "sample_kind": sample_kind,
                "status_code": response.status_code,
                "body": _sanitize(body),
                "create_elapsed_ms": create_elapsed_ms,
            },
        )
    job_id = body.get("job_id")
    if not job_id:
        raise Phase6TQAcceptanceError(
            "CREATE_MISSING_JOB_ID",
            f"create returned no job_id for {symbol}",
            context={"symbol": symbol, "sample_kind": sample_kind, "body": _sanitize(body)},
        )
    if body.get("status") != "queued":
        raise Phase6TQAcceptanceError(
            "CREATE_NOT_QUEUED",
            f"create returned non-queued status for {symbol}",
            context={"symbol": symbol, "sample_kind": sample_kind, "body": _sanitize(body)},
        )

    started = perf_counter()
    status_response = await client.get(f"/api/v2/company/CN/{symbol}/financial-fusion/jobs/{job_id}")
    status_elapsed_ms = round((perf_counter() - started) * 1000, 3)
    status_body = status_response.json()
    if status_response.status_code != 200 or not status_body.get("ok"):
        raise Phase6TQAcceptanceError(
            "STATUS_FAILED",
            f"status check failed for {job_id}",
            context={
                "job_id": job_id,
                "symbol": symbol,
                "sample_kind": sample_kind,
                "status_code": status_response.status_code,
                "body": _sanitize(status_body),
            },
        )
    if status_body.get("status") != "queued" or status_body.get("started_at") is not None:
        raise Phase6TQAcceptanceError(
            "STATUS_NOT_QUEUED",
            f"status moved out of queued for {job_id}",
            context={
                "job_id": job_id,
                "symbol": symbol,
                "sample_kind": sample_kind,
                "body": _sanitize(status_body),
            },
        )

    started = perf_counter()
    cancel_response = await client.post(f"/api/v2/company/CN/{symbol}/financial-fusion/jobs/{job_id}/cancel")
    cancel_elapsed_ms = round((perf_counter() - started) * 1000, 3)
    cancel_body = cancel_response.json()
    if cancel_response.status_code != 200 or not cancel_body.get("ok") or cancel_body.get("status") != "cancelled":
        raise Phase6TQAcceptanceError(
            "CANCEL_FAILED",
            f"cancel failed for {job_id}",
            context={
                "job_id": job_id,
                "symbol": symbol,
                "sample_kind": sample_kind,
                "status_code": cancel_response.status_code,
                "body": _sanitize(cancel_body),
            },
        )

    return {
        "symbol": symbol,
        "report_id": int(report.report_id),
        "job_id": job_id,
        "sample_kind": sample_kind,
        "create_elapsed_ms": create_elapsed_ms,
        "status_elapsed_ms": status_elapsed_ms,
        "cancel_elapsed_ms": cancel_elapsed_ms,
        "create_response": _sanitize(body),
        "status_response": _sanitize(status_body),
        "cancel_response": _sanitize(cancel_body),
        "queued": True,
        "started_at_is_null": status_body.get("started_at") is None,
        "cancelled": True,
    }


def _build_summary(payload: dict[str, Any]) -> dict[str, Any]:
    create_latencies = [float(item["create_elapsed_ms"]) for item in payload.get("formal_samples", [])]
    return {
        "phase": "phase6tq_same_region_acceptance",
        "status": payload.get("status", "failed"),
        "runner_provisioned": bool(payload.get("runner_provisioned")),
        "runner_region": payload.get("runner_region"),
        "http_acceptance": bool(payload.get("http_acceptance")),
        "warmup_total": int(payload.get("warmup_total") or 0),
        "samples_total": int(payload.get("samples_total") or 0),
        "steady_state_create_p50_ms": _percentile(create_latencies, 50),
        "steady_state_create_p95_ms": _percentile(create_latencies, 95),
        "steady_state_create_min_ms": round(min(create_latencies), 3) if create_latencies else None,
        "steady_state_create_max_ms": round(max(create_latencies), 3) if create_latencies else None,
        "auto_run": bool(payload.get("auto_run")),
        "rollout_percent": int(payload.get("rollout_percent") or 0),
        "manual_jobs_remained_queued": bool(payload.get("manual_jobs_remained_queued")),
        "jobs_cancelled": int(payload.get("jobs_cancelled") or 0),
        "duplicate_active_jobs": int(payload.get("duplicate_active_jobs") or 0),
        "preexisting_active_jobs_found": int(payload.get("preexisting_active_jobs_found") or 0),
        "preexisting_active_jobs_cancelled": int(payload.get("preexisting_active_jobs_cancelled") or 0),
        "active_jobs_after_cleanup": int(payload.get("active_jobs_after_cleanup") or 0),
        "cleanup_completed": bool(payload.get("cleanup_completed")),
        "errors": list(payload.get("errors") or []),
    }


def _write_artifacts(payload: dict[str, Any], *, out_json: str, out_md: str) -> None:
    summary = _build_summary(payload)
    json_path = Path(out_json)
    md_path = Path(out_md)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "# Phase 6T-Q Same-Region Acceptance\n\n"
        "```json\n"
        + json.dumps(summary, ensure_ascii=False, indent=2)
        + "\n```\n\n"
        + "## Trace\n\n"
        + json.dumps(_sanitize(payload), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


async def run_acceptance(
    args: argparse.Namespace,
    *,
    client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    session_factory: Callable[[], Any] = AsyncSessionLocal,
) -> dict[str, Any]:
    symbols = _parse_symbols(args.symbols)
    report_map = await _resolve_symbol_reports(symbols, session_factory=session_factory)
    active_jobs = await _list_active_jobs(session_factory=session_factory)
    known_cleanup_ids = [item.strip() for item in (args.cleanup_known_job_ids or "").split(",") if item.strip()]
    preexisting_active = [job for job in active_jobs if job["job_id"] not in set(known_cleanup_ids)]

    payload: dict[str, Any] = {
        "status": "failed",
        "runner_provisioned": True,
        "runner_region": args.runner_region,
        "http_acceptance": True,
        "warmup_total": int(args.warmup),
        "samples_total": int(args.samples),
        "auto_run": bool(getattr(settings, "company_v2_financial_fusion_auto_run", False)),
        "rollout_percent": int(getattr(settings, "company_v2_financial_fusion_rollout_percent", 0) or 0),
        "manual_jobs_remained_queued": False,
        "jobs_cancelled": 0,
        "warmup_jobs_cancelled": 0,
        "duplicate_active_jobs": 0,
        "preexisting_active_jobs_found": len(active_jobs),
        "preexisting_active_jobs_cancelled": 0,
        "active_jobs_after_cleanup": len(active_jobs),
        "cleanup_completed": False,
        "errors": [],
        "report_map": {symbol: asdict(report) for symbol, report in report_map.items()},
        "warmup_samples": [],
        "formal_samples": [],
        "cleanup_attempts": [],
    }

    async with client_factory(base_url=args.base_url, timeout=args.timeout) as client:
        try:
            if preexisting_active:
                payload["errors"].append(
                    {
                        "code": "PREEXISTING_ACTIVE_JOBS",
                        "message": "preexisting active jobs block acceptance by default",
                        "jobs": _sanitize(preexisting_active),
                    }
                )
                raise Phase6TQAcceptanceError(
                    "PREEXISTING_ACTIVE_JOBS",
                    "preexisting active jobs block acceptance by default",
                    context={"jobs": _sanitize(preexisting_active)},
                )

            if known_cleanup_ids:
                known_jobs = await _load_known_jobs(known_cleanup_ids, session_factory=session_factory)
                for job in known_jobs:
                    if job["status"] in {"queued", "running"}:
                        payload["cleanup_attempts"].append(await _cancel_job_http(client, symbol=job["symbol"], job_id=job["job_id"]))
                        payload["preexisting_active_jobs_cancelled"] += 1

            warmup_symbols = [symbols[index % len(symbols)] for index in range(max(0, int(args.warmup)))]
            for index, symbol in enumerate(warmup_symbols):
                result = await _sample_once(
                    client,
                    symbol=symbol,
                    report=report_map[symbol],
                    fields=DEFAULT_FIELDS,
                    refresh=False,
                    sample_kind=f"warmup-{index + 1}",
                )
                payload["warmup_samples"].append(result)
                payload["warmup_jobs_cancelled"] += 1

            formal_symbols = [symbols[index % len(symbols)] for index in range(max(0, int(args.samples)))]
            for index, symbol in enumerate(formal_symbols):
                result = await _sample_once(
                    client,
                    symbol=symbol,
                    report=report_map[symbol],
                    fields=DEFAULT_FIELDS,
                    refresh=False,
                    sample_kind=f"formal-{index + 1}",
                )
                payload["formal_samples"].append(result)
                payload["jobs_cancelled"] += 1

            payload["manual_jobs_remained_queued"] = all(
                bool(item.get("queued")) and bool(item.get("started_at_is_null"))
                for item in payload["warmup_samples"] + payload["formal_samples"]
            )
            active_after = await _list_active_jobs(session_factory=session_factory)
            payload["active_jobs_after_cleanup"] = len(active_after)
            payload["cleanup_completed"] = True
            if active_after:
                payload["errors"].append(
                    {
                        "code": "ACTIVE_JOBS_REMAIN",
                        "message": "active jobs remain after cleanup",
                        "jobs": _sanitize(active_after),
                    }
                )
                raise Phase6TQAcceptanceError(
                    "ACTIVE_JOBS_REMAIN",
                    "active jobs remain after cleanup",
                    context={"jobs": _sanitize(active_after)},
                )

            payload["status"] = "passed"
            return payload
        except Phase6TQAcceptanceError as exc:
            payload["errors"].append({"code": exc.code, "message": str(exc), "context": _sanitize(exc.context)})
            created_jobs = [
                {"job_id": item["job_id"], "symbol": item["symbol"]}
                for item in payload["warmup_samples"] + payload["formal_samples"]
                if item.get("job_id")
            ]
            if exc.context.get("job_id") and exc.context.get("symbol"):
                created_jobs.append({"job_id": str(exc.context["job_id"]), "symbol": str(exc.context["symbol"])})
            if created_jobs:
                await _cleanup_created_jobs(client, created_jobs)
            payload["cleanup_completed"] = True
            active_after = await _list_active_jobs(session_factory=session_factory)
            payload["active_jobs_after_cleanup"] = len(active_after)
            _write_artifacts(payload, out_json=args.out_json, out_md=args.out_md)
            return payload
        except Exception as exc:  # noqa: BLE001
            payload["errors"].append({"code": "INTERNAL_ERROR", "message": str(exc)})
            created_jobs = [
                {"job_id": item["job_id"], "symbol": item["symbol"]}
                for item in payload["warmup_samples"] + payload["formal_samples"]
                if item.get("job_id")
            ]
            if created_jobs:
                await _cleanup_created_jobs(client, created_jobs)
            payload["cleanup_completed"] = True
            active_after = await _list_active_jobs(session_factory=session_factory)
            payload["active_jobs_after_cleanup"] = len(active_after)
            _write_artifacts(payload, out_json=args.out_json, out_md=args.out_md)
            return payload
        finally:
            if payload.get("status") == "passed":
                payload["cleanup_completed"] = True
                payload["active_jobs_after_cleanup"] = len(await _list_active_jobs(session_factory=session_factory))
                _write_artifacts(payload, out_json=args.out_json, out_md=args.out_md)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--symbols", default="601686,600519,300750,000725,000001")
    parser.add_argument("--runner-region", default="ap-northeast-2")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--out-json", default=str(ARTIFACT_DIR / "company_v2_phase6tq_same_region_acceptance.json"))
    parser.add_argument("--out-md", default=str(ARTIFACT_DIR / "company_v2_phase6tq_same_region_acceptance.md"))
    parser.add_argument("--cleanup-known-job-ids", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = asyncio.run(run_acceptance(args))
    print(json.dumps({"status": payload["status"], "samples_total": payload["samples_total"]}, ensure_ascii=False))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
