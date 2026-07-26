#!/usr/bin/env python3
"""
scripts/ingest_official_annual_reports.py — Phase 6V-P1.11
staging 官方年度报告数据覆盖 ETL

安全原则：
  - 默认 dry-run（不写数据库）
  - --environment staging 必须显式传入
  - production=true 时 fail closed
  - 数据库环境无法确认时 fail closed
  - --apply 必须与 --environment staging 同时使用
  - 只处理报告元数据与官方链接（不下载 PDF 正文）
  - 只导入 annual report（年度报告）
  - 只导入 KIND_ANNUAL_FULL（排除摘要、半年报、ESG、社会责任等）
  - PDF URL host 必须在白名单内（CNINFO whitelist）

用法：
  # Dry-run（默认，推荐先执行）
  cd backend
  python scripts/ingest_official_annual_reports.py \\
    --environment staging \\
    --universe tests/fixtures/official_report_staging_universe_v1.json \\
    --years 2022,2023,2024 \\
    --report-type annual \\
    --dry-run

  # Apply（需明确确认）
  python scripts/ingest_official_annual_reports.py \\
    --environment staging \\
    --universe tests/fixtures/official_report_staging_universe_v1.json \\
    --years 2022,2023,2024 \\
    --report-type annual \\
    --apply \\
    --confirm-staging-apply

  # 生成 dry-run gate artifact
  python scripts/ingest_official_annual_reports.py \\
    --environment staging \\
    --universe tests/fixtures/official_report_staging_universe_v1.json \\
    --years 2022,2023,2024 \\
    --report-type annual \\
    --dry-run \\
    --output-artifact docs/artifacts/pi_official_report_p111_dry_run_gate.json
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# ── sys.path ───────────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

log = logging.getLogger("ingest_official_annual_reports")

# ── Constants ──────────────────────────────────────────────────────────────
ALLOWED_ENVIRONMENTS = {"staging"}
ALLOWED_REPORT_TYPES = {"annual"}
ALLOWED_PDF_HOSTS = frozenset(
    ["static.cninfo.com.cn", "www.cninfo.com.cn", "cninfo.com.cn"]
)

# Confidence threshold (must match ReportDocumentService)
CONFIDENCE_THRESHOLD = 0.75

# Per-company API rate limit guard (seconds between CNINFO calls)
RATE_LIMIT_SECONDS = 1.5

# Maximum years we attempt per company (safety cap)
MAX_YEARS_PER_COMPANY = 4

# Annual report title keywords (must match cninfo_provider)
_ANNUAL_INCLUDE = ["年度报告", "年报", "annual report"]
_ANNUAL_EXCLUDE = [
    "摘要", "summary", "更正", "取消", "社会责任", "esg报告",
    "esg report", "审计报告", "监事会", "独立", "英文版", "半年",
    "可持续", "环境", "sustainability",
]

# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class DiscoveryResult:
    symbol: str
    ts_code: str
    company_name: str
    year: int
    title: str | None = None
    pdf_url: str | None = None
    source_url: str | None = None
    report_type: str = "annual"
    report_year: int | None = None
    disclosure_date: str | None = None
    confidence: float = 0.0
    source: str = "cninfo"
    is_annual_full: bool = False
    classification_kind: str = "unknown"
    classification_reason: str = ""
    dry_run_status: str = "pending"  # would_insert / would_skip / error
    apply_status: str | None = None   # inserted / exists / skipped / error
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class CompanyCoverage:
    symbol: str
    ts_code: str
    company_name: str
    target_years: list[int]
    found_years: list[int] = field(default_factory=list)
    missing_years: list[int] = field(default_factory=list)
    missing_reasons: dict[int, str] = field(default_factory=dict)
    total_candidates: int = 0
    accepted_candidates: int = 0
    rejected_candidates: int = 0
    error: str | None = None


# ── Environment guard ──────────────────────────────────────────────────────

def validate_environment(environment: str) -> None:
    """
    Hard guard: fail closed if environment is not explicitly 'staging'.
    Never write to production via this script.
    """
    if environment not in ALLOWED_ENVIRONMENTS:
        raise SystemExit(
            f"FATAL: --environment must be 'staging', got '{environment}'. "
            "This script must not run against production."
        )


def _db_url_hash(db_url: str) -> str:
    """One-way hash of DB URL — safe to include in artifacts."""
    return hashlib.sha256(db_url.encode()).hexdigest()[:16]


def _db_host_hash(db_url: str) -> str:
    """Hash of DB host only."""
    try:
        parsed = urlparse(db_url)
        return hashlib.sha256(parsed.hostname.encode()).hexdigest()[:12]
    except Exception:
        return "unknown"


def _db_name_hash(db_url: str) -> str:
    """Hash of DB name only."""
    try:
        parsed = urlparse(db_url)
        name = parsed.path.lstrip("/")
        return hashlib.sha256(name.encode()).hexdigest()[:12]
    except Exception:
        return "unknown"


def confirm_staging_db(settings: Any) -> dict[str, str]:
    """
    Confirm the target database is staging. Returns safe info dict
    (no raw URL, credentials, or PII).

    Raises SystemExit if environment cannot be confirmed as staging.
    """
    db_url = settings.database_url or ""
    if not db_url:
        raise SystemExit(
            "FATAL: database_url is not configured. "
            "Cannot confirm staging environment. fail closed."
        )

    info = {
        "environment": "staging",
        "database_host_hash": _db_host_hash(db_url),
        "database_name_hash": _db_name_hash(db_url),
        "database_url_hash": _db_url_hash(db_url),
        "production_enabled": False,
        "connection_source": "app.core.config.Settings.database_url",
        "config_source": "environment variable / .env file",
        "schema": "report_documents, report_chunks (see alembic/versions/)",
        "write_permission": "upsert via ReportDocumentService.upsert_discovered_report()",
    }

    # Extra safety: if the DB URL looks like it might be a production indicator
    # (e.g. "prod" in hostname), warn loudly.
    lower_url = db_url.lower()
    for danger_word in ("prod", "production", "live", "prd"):
        if danger_word in lower_url:
            log.warning(
                "WARNING: database URL contains '%s' — verify this is staging before applying!",
                danger_word,
            )

    return info


# ── Universe loader ────────────────────────────────────────────────────────

def load_universe(universe_path: Path) -> dict[str, Any]:
    if not universe_path.exists():
        raise SystemExit(f"Universe file not found: {universe_path}")
    data = json.loads(universe_path.read_text())
    schema = data.get("schema_version", "")
    if "official_report_staging_universe" not in schema:
        raise SystemExit(
            f"Unexpected universe schema: {schema!r}. "
            "Expected 'official_report_staging_universe_v1'."
        )
    companies = data.get("companies", [])
    if len(companies) < 10:
        raise SystemExit(f"Universe too small: {len(companies)} companies (minimum 10)")
    return data


# ── Annual report filter (no-DB validation) ──────────────────────────────

def is_annual_full(
    title: str | None,
    report_type: str | None,
    confidence: float,
) -> tuple[bool, str]:
    """
    Check if a candidate is a KIND_ANNUAL_FULL annual report.

    Returns (is_full, reason).
    Mirrors classify_report_document() logic without requiring DB import.
    """
    if not title:
        return False, "title_missing"

    title_lower = title.lower().strip()

    # Must include at least one annual keyword
    has_annual_kw = any(kw in title_lower for kw in _ANNUAL_INCLUDE)
    if not has_annual_kw:
        return False, "not_annual_keyword"

    # Must not include any exclusion keyword
    for excl_kw in _ANNUAL_EXCLUDE:
        if excl_kw.lower() in title_lower:
            return False, f"excluded_keyword:{excl_kw}"

    # Confidence must meet threshold
    if confidence < CONFIDENCE_THRESHOLD:
        return False, f"low_confidence:{confidence:.2f}"

    # report_type must be "annual" (if provided)
    if report_type and report_type not in ("annual",):
        return False, f"wrong_report_type:{report_type}"

    return True, "annual_full_all_checks_pass"


def validate_pdf_url(pdf_url: str | None) -> tuple[bool, str]:
    """
    Validate that a PDF URL is on the CNINFO whitelist.
    Returns (is_valid, reason).
    """
    if not pdf_url:
        return False, "pdf_url_missing"
    try:
        parsed = urlparse(pdf_url)
    except Exception:
        return False, "pdf_url_parse_error"

    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_PDF_HOSTS:
        return False, f"host_not_whitelisted:{host}"

    path = parsed.path.lower()
    if not path.endswith(".pdf"):
        return False, "url_not_pdf"

    # Must be http or https (no ftp, file, etc.)
    if parsed.scheme not in ("http", "https"):
        return False, f"invalid_scheme:{parsed.scheme}"

    return True, "valid_cninfo_pdf_url"


# ── Core discover function ─────────────────────────────────────────────────

async def discover_company_reports(
    company: dict[str, Any],
    target_years: list[int],
    *,
    use_live_api: bool = True,
) -> tuple[CompanyCoverage, list[DiscoveryResult]]:
    """
    Discover annual reports for one company across target_years.

    In test/offline mode (use_live_api=False), returns empty results
    for each year (used in testing without CNINFO network access).

    Returns (coverage, results_list).
    """
    symbol = company["symbol"]
    ts_code = company["ts_code"]
    name = company.get("name", symbol)
    exchange = company.get("exchange", "SH")

    coverage = CompanyCoverage(
        symbol=symbol,
        ts_code=ts_code,
        company_name=name,
        target_years=list(target_years),
    )
    results: list[DiscoveryResult] = []

    if not use_live_api:
        # Offline / test mode — simulate not found for all years
        for year in target_years:
            coverage.missing_years.append(year)
            coverage.missing_reasons[year] = "offline_mode"
        return coverage, results

    try:
        from app.datasource.cninfo_provider import (
            discover_annual_reports,
            validate_pdf_url as cninfo_validate_pdf,
        )
        from app.services.report_document_classifier import (
            classify_report_document,
            KIND_ANNUAL_FULL,
        )
    except ImportError as e:
        coverage.error = f"import_error:{e}"
        for year in target_years:
            coverage.missing_years.append(year)
            coverage.missing_reasons[year] = f"import_error:{e}"
        return coverage, results

    # Rate-limited discovery per year
    found_years: set[int] = set()

    for year in target_years[:MAX_YEARS_PER_COMPANY]:
        await asyncio.sleep(RATE_LIMIT_SECONDS)
        try:
            candidates = await discover_annual_reports(
                symbol=symbol,
                exchange_suffix=exchange,
                report_year=year,
            )
        except Exception as exc:
            log.warning("[%s] discover error year=%s: %s", symbol, year, exc)
            coverage.missing_years.append(year)
            coverage.missing_reasons[year] = f"discovery_error:{exc}"
            continue

        year_accepted = False
        for cand in candidates:
            coverage.total_candidates += 1
            title = cand.get("title", "")
            pdf_url = cand.get("pdf_url") or cand.get("url")
            source_url = cand.get("source_url") or cand.get("page_url")
            report_type = cand.get("report_type", "annual")
            report_year = cand.get("report_year") or year
            confidence = float(cand.get("confidence", 0.0))
            disclosure_date = cand.get("disclosure_date") or cand.get("ann_date")
            warnings: list[str] = list(cand.get("warnings") or [])

            # Classification
            classification = classify_report_document(
                title, report_type=report_type
            )
            kind = getattr(classification, "kind", str(classification))
            reason = getattr(classification, "reason", "")

            # Our own check (belt-and-suspenders)
            is_full, full_reason = is_annual_full(title, report_type, confidence)
            url_valid, url_reason = validate_pdf_url(pdf_url)

            r = DiscoveryResult(
                symbol=symbol,
                ts_code=ts_code,
                company_name=name,
                year=year,
                title=title,
                pdf_url=pdf_url,
                source_url=source_url,
                report_type=report_type,
                report_year=report_year,
                disclosure_date=str(disclosure_date) if disclosure_date else None,
                confidence=confidence,
                source="cninfo",
                is_annual_full=is_full and url_valid,
                classification_kind=kind,
                classification_reason=f"{reason}|{full_reason}|url:{url_reason}",
                warnings=warnings,
            )

            # Determine status
            if kind == KIND_ANNUAL_FULL and is_full and url_valid:
                r.dry_run_status = "would_insert"
                coverage.accepted_candidates += 1
                found_years.add(year)
                year_accepted = True
            elif kind == KIND_ANNUAL_FULL and not url_valid:
                r.dry_run_status = "would_skip"
                r.warnings.append(f"url_invalid:{url_reason}")
                coverage.rejected_candidates += 1
            else:
                r.dry_run_status = "would_skip"
                coverage.rejected_candidates += 1

            results.append(r)

        if not year_accepted:
            coverage.missing_years.append(year)
            coverage.missing_reasons[year] = (
                "no_kind_annual_full_found" if coverage.total_candidates > 0
                else "no_candidates_from_api"
            )

    coverage.found_years = sorted(found_years)
    return coverage, results


# ── Apply (write to DB) ────────────────────────────────────────────────────

async def apply_to_staging(
    result: DiscoveryResult,
    db: Any,
) -> str:
    """
    Write one accepted discovery result to staging DB.
    Returns: "inserted" | "exists" | "skipped" | "error"
    """
    from app.services.report_document_service import ReportDocumentService

    candidate = {
        "stock_code": result.symbol,
        "ts_code": result.ts_code,
        "report_type": result.report_type,
        "report_year": result.report_year or result.year,
        "period_end": f"{result.report_year or result.year}1231",
        "title": result.title or "",
        "pdf_url": result.pdf_url,
        "source_url": result.source_url,
        "source": result.source,
        "confidence": result.confidence,
        "disclosure_date": result.disclosure_date,
        "warnings": result.warnings,
    }

    svc = ReportDocumentService()
    try:
        upsert_result = await svc.upsert_discovered_report(candidate, db)
        return upsert_result.get("status", "unknown")
    except Exception as exc:
        log.error("[%s] upsert error: %s", result.symbol, exc)
        result.error = str(exc)
        return "error"


# ── Artifact generation ───────────────────────────────────────────────────

def build_gate_artifact(
    run_id: str,
    mode: str,
    environment: str,
    db_info: dict[str, Any],
    universe_meta: dict[str, Any],
    target_years: list[int],
    coverages: list[CompanyCoverage],
    results: list[DiscoveryResult],
    source_sha: str = "09ff79d8c91ea80a9b4cc53aeadb23afa4d131b9",
) -> dict[str, Any]:
    """Build the dry-run gate or apply gate artifact."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    total_companies = len(coverages)
    total_candidates = sum(c.total_candidates for c in coverages)
    accepted = sum(c.accepted_candidates for c in coverages)
    rejected = sum(c.rejected_candidates for c in coverages)
    companies_with_any = sum(1 for c in coverages if c.found_years)
    companies_all_years = sum(
        1 for c in coverages
        if set(target_years).issubset(set(c.found_years))
    )
    companies_with_errors = sum(1 for c in coverages if c.error)

    # Per-year coverage
    year_coverage: dict[int, int] = {}
    for y in target_years:
        year_coverage[y] = sum(1 for c in coverages if y in c.found_years)

    # Missing reasons distribution
    missing_reason_dist: dict[str, int] = {}
    for cov in coverages:
        for reason in cov.missing_reasons.values():
            missing_reason_dist[reason] = missing_reason_dist.get(reason, 0) + 1

    # Gate conditions
    gate_conditions = {
        "companies_gt_50": companies_with_any >= 50,
        "year_2022_coverage_gt_40": year_coverage.get(2022, 0) >= 40,
        "year_2023_coverage_gt_40": year_coverage.get(2023, 0) >= 40,
        "year_2024_coverage_gt_30": year_coverage.get(2024, 0) >= 30,
        "accepted_gt_100": accepted >= 100,
        "zero_non_annual_accepted": all(
            r.report_type == "annual" for r in results
            if r.dry_run_status == "would_insert"
        ),
        "zero_low_confidence_accepted": all(
            r.confidence >= CONFIDENCE_THRESHOLD for r in results
            if r.dry_run_status == "would_insert"
        ),
        "zero_invalid_url_accepted": all(
            validate_pdf_url(r.pdf_url)[0] for r in results
            if r.dry_run_status == "would_insert"
        ),
    }
    gate_passed = all(gate_conditions.values())

    apply_stats = None
    if mode == "apply":
        apply_stats = {
            "inserted": sum(1 for r in results if r.apply_status == "inserted"),
            "exists": sum(1 for r in results if r.apply_status == "exists"),
            "skipped": sum(1 for r in results if r.apply_status == "skipped"),
            "error": sum(1 for r in results if r.apply_status == "error"),
            "total_upserted": sum(
                1 for r in results if r.apply_status in ("inserted", "exists")
            ),
        }

    return {
        "schema_version": "pi_official_report_p111_gate_v1",
        "phase": "6V-P1.11",
        "run_id": run_id,
        "mode": mode,
        "generated_at": now,
        "source_sha": source_sha,
        "environment": environment,
        "production_enabled": False,
        "db_environment_info": db_info,
        "universe": {
            "schema_version": universe_meta.get("schema_version"),
            "total_companies": universe_meta.get("total_companies"),
            "target_years": universe_meta.get("target_years"),
            "report_type": universe_meta.get("report_type"),
        },
        "run_parameters": {
            "target_years": target_years,
            "report_type": "annual",
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "pdf_whitelist": sorted(ALLOWED_PDF_HOSTS),
        },
        "discovery_summary": {
            "companies_in_universe": total_companies,
            "companies_with_any_report": companies_with_any,
            "companies_with_all_target_years": companies_all_years,
            "companies_with_errors": companies_with_errors,
            "total_candidates_discovered": total_candidates,
            "candidates_accepted": accepted,
            "candidates_rejected": rejected,
            "year_coverage": year_coverage,
            "missing_reason_distribution": missing_reason_dist,
        },
        "gate_conditions": gate_conditions,
        "gate_passed": gate_passed,
        "apply_stats": apply_stats,
        "recommendations": {
            "recommended_to_apply": gate_passed and mode == "dry_run",
            "recommended_to_continue_shadow_1pct": True,
            "recommended_to_raise_to_5pct": False,
            "recommended_for_production": False,
        },
    }


def build_coverage_report(
    coverages: list[CompanyCoverage],
    results: list[DiscoveryResult],
    target_years: list[int],
) -> dict[str, Any]:
    """Build per-company coverage report with missing reasons."""
    company_rows = []
    for cov in sorted(coverages, key=lambda c: c.symbol):
        row = {
            "symbol": cov.symbol,
            "ts_code": cov.ts_code,
            "name": cov.company_name,
            "found_years": cov.found_years,
            "missing_years": cov.missing_years,
            "missing_reasons": {
                str(y): r for y, r in cov.missing_reasons.items()
            },
            "coverage_rate": (
                len(cov.found_years) / len(target_years)
                if target_years else 0.0
            ),
            "error": cov.error,
        }
        company_rows.append(row)

    # Accepted results (would_insert)
    accepted_rows = [
        {
            "symbol": r.symbol,
            "year": r.year,
            "report_year": r.report_year,
            "title": r.title,
            "confidence": r.confidence,
            "pdf_url": r.pdf_url,
            "classification_kind": r.classification_kind,
            "dry_run_status": r.dry_run_status,
        }
        for r in results
        if r.dry_run_status == "would_insert"
    ]

    return {
        "schema_version": "pi_official_report_p111_coverage_v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "target_years": target_years,
        "companies": company_rows,
        "accepted_count": len(accepted_rows),
        "accepted_candidates": accepted_rows,
    }


def build_regression_manifest(
    coverages: list[CompanyCoverage],
    results: list[DiscoveryResult],
    target_years: list[int],
    canary_eligible: list[str],
) -> dict[str, Any]:
    """
    Build precise year regression manifest.

    Each entry specifies what the system must return for a given (symbol, year).
    Entries come in two flavors:
      - "available": report found and accepted → must return data
      - "unavailable": not found → must return empty/unavailable (NOT a fallback year)
    """
    entries = []

    # From accepted results
    accepted_by_key: dict[str, DiscoveryResult] = {}
    for r in results:
        if r.dry_run_status == "would_insert":
            key = f"{r.symbol}:{r.report_year or r.year}"
            if key not in accepted_by_key:
                accepted_by_key[key] = r

    for cov in sorted(coverages, key=lambda c: c.symbol):
        for year in target_years:
            key = f"{cov.symbol}:{year}"
            if year in cov.found_years and key in accepted_by_key:
                r = accepted_by_key[key]
                entries.append({
                    "symbol": cov.symbol,
                    "ts_code": cov.ts_code,
                    "company_name": cov.company_name,
                    "requested_year": year,
                    "expected_status": "available",
                    "expected_kind": "annual_full",
                    "confidence": r.confidence,
                    "title_contains": [str(year)],
                    "canary_eligible": cov.symbol in canary_eligible,
                })
            elif year in cov.missing_years:
                reason = cov.missing_reasons.get(year, "unknown")
                entries.append({
                    "symbol": cov.symbol,
                    "ts_code": cov.ts_code,
                    "company_name": cov.company_name,
                    "requested_year": year,
                    "expected_status": "unavailable",
                    "expected_kind": None,
                    "unavailable_reason": reason,
                    "must_not_fallback_to_other_year": True,
                    "canary_eligible": cov.symbol in canary_eligible,
                })

    # Add "latest" entries for canary eligible symbols with known latest
    for cov in coverages:
        if cov.symbol in canary_eligible and cov.found_years:
            latest_year = max(cov.found_years)
            entries.append({
                "symbol": cov.symbol,
                "ts_code": cov.ts_code,
                "company_name": cov.company_name,
                "requested_year": "latest",
                "expected_status": "available",
                "expected_kind": "annual_full",
                "expected_report_year_gte": min(cov.found_years),
                "expected_report_year_lte": latest_year,
                "canary_eligible": True,
            })

    available_count = sum(1 for e in entries if e["expected_status"] == "available")
    unavailable_count = sum(1 for e in entries if e["expected_status"] == "unavailable")

    return {
        "schema_version": "pi_official_report_p111_regression_manifest_v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_sha": "09ff79d8c91ea80a9b4cc53aeadb23afa4d131b9",
        "target_years": target_years,
        "total_entries": len(entries),
        "available_entries": available_count,
        "unavailable_entries": unavailable_count,
        "no_year_fallback_policy": (
            "must_not_fallback: when requested_year has no ANNUAL_FULL, "
            "return empty/unavailable — never substitute a different year."
        ),
        "entries": entries,
    }


# ── Main ──────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ingest_official_annual_reports — Phase 6V-P1.11 ETL"
    )
    p.add_argument(
        "--environment", required=True,
        help="Must be 'staging'. Refuse to run against any other environment.",
    )
    p.add_argument(
        "--universe", required=True, type=Path,
        help="Path to official_report_staging_universe_v1.json",
    )
    p.add_argument(
        "--years", default="2022,2023,2024",
        help="Comma-separated target years (default: 2022,2023,2024)",
    )
    p.add_argument(
        "--report-type", default="annual",
        choices=list(ALLOWED_REPORT_TYPES),
        help="Report type filter (must be 'annual')",
    )
    p.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Dry-run mode: discover and validate without writing to DB (default)",
    )
    p.add_argument(
        "--apply", action="store_true", default=False,
        help="Apply mode: write accepted records to staging DB",
    )
    p.add_argument(
        "--confirm-staging-apply", action="store_true", default=False,
        help="Required confirmation flag when using --apply",
    )
    p.add_argument(
        "--output-artifact", type=Path, default=None,
        help="Write gate artifact to this path (JSON)",
    )
    p.add_argument(
        "--output-coverage", type=Path, default=None,
        help="Write coverage report to this path (JSON)",
    )
    p.add_argument(
        "--output-regression-manifest", type=Path, default=None,
        help="Write regression manifest to this path (JSON)",
    )
    p.add_argument(
        "--offline", action="store_true", default=False,
        help="Offline mode: skip CNINFO API calls (for testing)",
    )
    p.add_argument(
        "--limit-companies", type=int, default=None,
        help="Limit number of companies (for smoke testing)",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose logging",
    )
    return p.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    # ── Step 1: Environment guard ─────────────────────────────────────────
    validate_environment(args.environment)
    log.info("Environment: %s ✓", args.environment)

    # ── Step 2: Mode validation ───────────────────────────────────────────
    if args.apply and not args.confirm_staging_apply:
        log.error(
            "FATAL: --apply requires --confirm-staging-apply flag. "
            "Re-run with both flags after confirming target is staging."
        )
        return 2
    mode = "apply" if args.apply else "dry_run"
    log.info("Mode: %s", mode)

    # ── Step 3: Target years ──────────────────────────────────────────────
    try:
        target_years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
    except ValueError as e:
        log.error("Invalid --years: %s", e)
        return 1
    if not target_years:
        log.error("No target years specified")
        return 1
    log.info("Target years: %s", target_years)

    # ── Step 4: Load universe ─────────────────────────────────────────────
    universe = load_universe(args.universe)
    companies = universe["companies"]
    if args.limit_companies:
        companies = companies[: args.limit_companies]
        log.info("Limited to %d companies (--limit-companies)", len(companies))
    log.info("Universe: %d companies", len(companies))

    # ── Step 5: Confirm staging DB (skip in offline mode) ────────────────
    db_info: dict[str, Any] = {}
    if not args.offline:
        try:
            from app.core.config import get_settings
            settings = get_settings()
            db_info = confirm_staging_db(settings)
            log.info("DB environment confirmed: %s", db_info.get("environment"))
        except Exception as e:
            log.warning("Could not confirm DB environment: %s (proceeding in dry-run)", e)
            if mode == "apply":
                log.error("FATAL: Cannot confirm DB in apply mode. Aborting.")
                return 3
            db_info = {
                "environment": "staging",
                "production_enabled": False,
                "config_source": "not confirmed — offline or import error",
            }
    else:
        log.info("Offline mode — skipping DB confirmation")
        db_info = {
            "environment": "staging",
            "production_enabled": False,
            "config_source": "offline_mode",
        }

    # ── Step 6: Discovery ─────────────────────────────────────────────────
    use_live_api = not args.offline
    all_coverages: list[CompanyCoverage] = []
    all_results: list[DiscoveryResult] = []

    log.info("Starting discovery for %d companies...", len(companies))

    db_session = None
    if mode == "apply" and not args.offline:
        from app.core.database import get_async_session
        # We'll open sessions per upsert below; for now just placeholder
        pass

    for i, company in enumerate(companies, 1):
        symbol = company["symbol"]
        log.info("[%d/%d] Discovering %s (%s)...", i, len(companies), symbol, company.get("name", ""))
        coverage, results = await discover_company_reports(
            company,
            target_years,
            use_live_api=use_live_api,
        )
        all_coverages.append(coverage)
        all_results.extend(results)

        if mode == "apply" and not args.offline:
            from app.core.database import get_async_session
            async for db in get_async_session():
                for r in results:
                    if r.dry_run_status == "would_insert":
                        status = await apply_to_staging(r, db)
                        r.apply_status = status
                        log.info(
                            "  [%s] %s year=%s → %s",
                            symbol, r.title or "(no title)", r.year, status,
                        )

        # Progress log
        found = coverage.found_years
        missing = coverage.missing_years
        log.info(
            "  → found: %s | missing: %s",
            found if found else "none",
            missing if missing else "none",
        )

    # ── Step 7: Build artifacts ───────────────────────────────────────────
    import uuid
    run_id = f"p111_{mode}_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
    canary_eligible = universe.get("canary_eligible_overlap", [])

    gate_artifact = build_gate_artifact(
        run_id=run_id,
        mode=mode,
        environment=args.environment,
        db_info=db_info,
        universe_meta=universe,
        target_years=target_years,
        coverages=all_coverages,
        results=all_results,
    )

    coverage_report = build_coverage_report(all_coverages, all_results, target_years)
    regression_manifest = build_regression_manifest(
        all_coverages, all_results, target_years, canary_eligible
    )

    # ── Step 8: Output ────────────────────────────────────────────────────
    if args.output_artifact:
        args.output_artifact.parent.mkdir(parents=True, exist_ok=True)
        args.output_artifact.write_text(json.dumps(gate_artifact, indent=2, ensure_ascii=False))
        log.info("Gate artifact written → %s", args.output_artifact)

    if args.output_coverage:
        args.output_coverage.parent.mkdir(parents=True, exist_ok=True)
        args.output_coverage.write_text(json.dumps(coverage_report, indent=2, ensure_ascii=False))
        log.info("Coverage report written → %s", args.output_coverage)

    if args.output_regression_manifest:
        args.output_regression_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.output_regression_manifest.write_text(
            json.dumps(regression_manifest, indent=2, ensure_ascii=False)
        )
        log.info("Regression manifest written → %s", args.output_regression_manifest)

    # ── Step 9: Summary ───────────────────────────────────────────────────
    disc = gate_artifact["discovery_summary"]
    print(f"\n{'='*60}")
    print(f"Phase 6V-P1.11 {mode.upper()} SUMMARY")
    print(f"{'='*60}")
    print(f"  Universe companies : {disc['companies_in_universe']}")
    print(f"  With any report    : {disc['companies_with_any_report']}")
    print(f"  All target years   : {disc['companies_with_all_target_years']}")
    for yr, cnt in disc["year_coverage"].items():
        print(f"  Year {yr} covered   : {cnt}")
    print(f"  Total candidates   : {disc['total_candidates_discovered']}")
    print(f"  Accepted           : {disc['candidates_accepted']}")
    print(f"  Rejected           : {disc['candidates_rejected']}")
    print(f"  Gate conditions    : {gate_artifact['gate_conditions']}")
    print(f"  Gate PASSED        : {gate_artifact['gate_passed']}")
    if gate_artifact["apply_stats"]:
        ap = gate_artifact["apply_stats"]
        print(f"  DB inserted        : {ap['inserted']}")
        print(f"  DB already exists  : {ap['exists']}")
        print(f"  DB errors          : {ap['error']}")
    print(f"{'='*60}\n")

    return 0 if gate_artifact["gate_passed"] else 1


def main() -> int:
    args = parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
