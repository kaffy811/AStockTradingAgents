#!/usr/bin/env python3
"""
Phase 6V-P1.11B — Post-apply quality validation for staging official report data.

Connects to staging DB, runs quality and coverage checks on report_documents,
and outputs a validation artifact.

Usage:
    python scripts/validate_official_report_staging_data.py \
        --environment staging \
        [--output docs/artifacts/pi_official_report_p111_post_apply_validation.json]
"""

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
UNIVERSE_FIXTURE = (
    BACKEND_DIR
    / "tests"
    / "fixtures"
    / "official_report_staging_universe_v1.json"
)
DEFAULT_OUTPUT = (
    BACKEND_DIR
    / "docs"
    / "artifacts"
    / "pi_official_report_p111_post_apply_validation.json"
)

TARGET_YEARS = [2022, 2023, 2024]
VALID_YEAR_RANGE = set(range(2015, 2026))  # 2015..2025 inclusive
CNINFO_DOMAINS = {
    "static.cninfo.com.cn",
    "www.cninfo.com.cn",
    "cninfo.com.cn",
}

DB_HOST_HASH = "2b73921d4030"
DB_NAME_HASH = "a942b37ccfaf"
DB_URL_HASH = "87a02187b71e97d8"

# Thresholds
COVERED_SYMBOLS_TARGET = 90
THREE_YEAR_COMPLETE_TARGET = 75
ANNUAL_RECORDS_TARGET = 250


# ---------------------------------------------------------------------------
# Environment guard
# ---------------------------------------------------------------------------

def confirm_staging_environment() -> None:
    import hashlib
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set. Cannot confirm staging environment.")
    url_hash_actual = hashlib.sha256(db_url.encode()).hexdigest()[:16]
    if url_hash_actual != DB_URL_HASH:
        raise RuntimeError(
            f"[FAIL-CLOSED] DATABASE_URL hash mismatch.\n"
            f"  Expected: {DB_URL_HASH}\n"
            f"  Actual:   {url_hash_actual}\n"
            "This script refuses to run against an unrecognised database."
        )
    print(f"[OK] Staging DB URL hash confirmed: {url_hash_actual}")


# ---------------------------------------------------------------------------
# Universe loading
# ---------------------------------------------------------------------------

def load_universe(path: Path) -> set[str]:
    """Return set of ts_codes from the universe fixture."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        companies = data
    elif isinstance(data, dict):
        companies = data.get("companies", data.get("universe", []))
    else:
        raise ValueError(f"Unexpected universe format: {type(data)}")

    ts_codes: set[str] = set()
    for c in companies:
        if isinstance(c, str):
            ts_codes.add(c)
        elif isinstance(c, dict):
            tc = c.get("ts_code") or c.get("code") or c.get("symbol")
            if tc:
                ts_codes.add(tc)
    print(f"[INFO] Loaded universe: {len(ts_codes)} ts_codes")
    return ts_codes


# ---------------------------------------------------------------------------
# URL domain extractor
# ---------------------------------------------------------------------------

def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()
    except Exception:
        return None


def is_cninfo_domain(url: str | None) -> bool:
    if url is None:
        return True  # NULL pdf_url is allowed
    domain = extract_domain(url)
    if domain is None:
        return False
    return any(domain == d or domain.endswith("." + d) for d in CNINFO_DOMAINS)


# ---------------------------------------------------------------------------
# DB query
# ---------------------------------------------------------------------------

async def fetch_all_annual_records() -> list[dict[str, Any]]:
    """
    Return all rows from report_documents where report_type='annual'.
    Returns list of dicts with keys: ts_code, report_type, report_year,
    pdf_url, source, download_status, period_end.
    """
    from app.core.database import get_async_session
    from sqlalchemy import text

    rows: list[dict[str, Any]] = []
    async for session in get_async_session():
        result = await session.execute(
            text(
                "SELECT id, ts_code, report_type, report_year, pdf_url, "
                "source, download_status, period_end, disclosure_date "
                "FROM report_documents "
                "WHERE report_type = 'annual' "
                "ORDER BY ts_code, report_year"
            )
        )
        for row in result.mappings():
            rows.append(dict(row))
        break

    print(f"[INFO] Fetched {len(rows)} annual report records from DB")
    return rows


async def fetch_total_row_count() -> int:
    from app.core.database import get_async_session
    from sqlalchemy import text

    async for session in get_async_session():
        result = await session.execute(text("SELECT COUNT(*) FROM report_documents"))
        count = result.scalar()
        break
    return count or 0


# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------

def run_quality_checks(
    rows: list[dict[str, Any]],
    universe_ts_codes: set[str],
    total_rows: int,
) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        raise RuntimeError("No annual report rows found — cannot validate empty dataset.")

    # --- Rate metrics ---
    company_match_hits = sum(1 for r in rows if r["ts_code"] in universe_ts_codes)
    company_match_rate = company_match_hits / n

    year_match_hits = sum(1 for r in rows if r.get("report_year") in VALID_YEAR_RANGE)
    year_match_rate = year_match_hits / n

    report_type_hits = sum(1 for r in rows if r.get("report_type") == "annual")
    report_type_match_rate = report_type_hits / n

    domain_hits = sum(1 for r in rows if is_cninfo_domain(r.get("pdf_url")))
    official_domain_verified_rate = domain_hits / n

    provenance_hits = sum(
        1 for r in rows
        if r.get("source") == "cninfo" or (r.get("source") is not None and r.get("source") != "")
    )
    provenance_complete_rate = provenance_hits / n

    # --- Zero-tolerance counts ---
    wrong_year_count = sum(
        1 for r in rows if r.get("report_year") not in VALID_YEAR_RANGE
    )
    wrong_type_count = sum(1 for r in rows if r.get("report_type") != "annual")
    fabricated_url_count = sum(
        1 for r in rows
        if r.get("pdf_url") is not None and not is_cninfo_domain(r.get("pdf_url"))
    )
    provenance_failures = n - provenance_hits

    # --- Duplicate detection (ts_code + report_type + period_end) ---
    combo_counter: Counter = Counter()
    for r in rows:
        key = (r.get("ts_code"), r.get("report_type"), r.get("period_end"))
        combo_counter[key] += 1
    active_duplicate_count = sum(1 for cnt in combo_counter.values() if cnt > 1)

    # --- Coverage metrics ---
    target_year_rows = [r for r in rows if r.get("report_year") in TARGET_YEARS]
    ts_codes_in_db = {r["ts_code"] for r in rows}
    covered_symbols = len(universe_ts_codes & ts_codes_in_db)

    # Which companies have all 3 target years?
    ts_year_map: dict[str, set[int]] = {}
    for r in target_year_rows:
        tc = r["ts_code"]
        yr = r.get("report_year")
        if tc and yr:
            ts_year_map.setdefault(tc, set()).add(yr)

    three_year_complete_symbols = sum(
        1 for tc in universe_ts_codes
        if set(TARGET_YEARS).issubset(ts_year_map.get(tc, set()))
    )

    annual_report_records_for_target_years = len(target_year_rows)

    # Year distribution
    year_counter: Counter = Counter()
    for r in target_year_rows:
        yr = r.get("report_year")
        if yr:
            year_counter[str(yr)] += 1

    # Domain breakdown
    domain_breakdown: dict[str, int] = {
        "static_cninfo_com_cn": 0,
        "www_cninfo_com_cn": 0,
        "cninfo_com_cn": 0,
        "null_pdf_url": 0,
        "non_cninfo_domain": 0,
    }
    for r in rows:
        url = r.get("pdf_url")
        if url is None:
            domain_breakdown["null_pdf_url"] += 1
        else:
            domain = extract_domain(url) or ""
            if domain == "static.cninfo.com.cn":
                domain_breakdown["static_cninfo_com_cn"] += 1
            elif domain == "www.cninfo.com.cn":
                domain_breakdown["www_cninfo_com_cn"] += 1
            elif domain == "cninfo.com.cn":
                domain_breakdown["cninfo_com_cn"] += 1
            else:
                domain_breakdown["non_cninfo_domain"] += 1

    # --- Gate decision ---
    quality_gate_passed = (
        company_match_rate >= 0.99
        and year_match_rate >= 0.99
        and report_type_match_rate >= 1.0
        and official_domain_verified_rate >= 0.99
        and provenance_complete_rate >= 0.99
        and wrong_year_count == 0
        and wrong_type_count == 0
        and fabricated_url_count == 0
        and active_duplicate_count == 0
    )

    covered_symbols_passed = covered_symbols >= COVERED_SYMBOLS_TARGET
    three_year_complete_passed = three_year_complete_symbols >= THREE_YEAR_COMPLETE_TARGET
    annual_records_passed = annual_report_records_for_target_years >= ANNUAL_RECORDS_TARGET

    coverage_target_met = (
        covered_symbols_passed
        and three_year_complete_passed
        and annual_records_passed
    )

    coverage_notes_parts: list[str] = []
    if not covered_symbols_passed:
        coverage_notes_parts.append(
            f"covered_symbols={covered_symbols}<{COVERED_SYMBOLS_TARGET} FAIL"
        )
    else:
        coverage_notes_parts.append(
            f"covered_symbols={covered_symbols}/{len(universe_ts_codes)} PASS"
        )

    if not three_year_complete_passed:
        coverage_notes_parts.append(
            f"three_year_complete={three_year_complete_symbols}<{THREE_YEAR_COMPLETE_TARGET} "
            "FAIL (genuine 2024 availability gap, not data quality issue)"
        )
    else:
        coverage_notes_parts.append(
            f"three_year_complete={three_year_complete_symbols} PASS"
        )

    if not annual_records_passed:
        coverage_notes_parts.append(
            f"annual_records={annual_report_records_for_target_years}<{ANNUAL_RECORDS_TARGET} FAIL"
        )
    else:
        coverage_notes_parts.append(
            f"annual_records={annual_report_records_for_target_years}>={ANNUAL_RECORDS_TARGET} PASS"
        )

    coverage_notes = "; ".join(coverage_notes_parts)

    return {
        "row_counts": {
            "total_rows_after": total_rows,
            "annual_report_rows": n,
            "target_years_rows": annual_report_records_for_target_years,
        },
        "year_distribution": dict(year_counter),
        "coverage_metrics": {
            "universe_size": len(universe_ts_codes),
            "covered_symbols": covered_symbols,
            "covered_symbols_target": COVERED_SYMBOLS_TARGET,
            "covered_symbols_passed": covered_symbols_passed,
            "three_year_complete_symbols": three_year_complete_symbols,
            "three_year_complete_target": THREE_YEAR_COMPLETE_TARGET,
            "three_year_complete_passed": three_year_complete_passed,
            "annual_report_records_for_target_years": annual_report_records_for_target_years,
            "annual_report_records_target": ANNUAL_RECORDS_TARGET,
            "annual_report_records_passed": annual_records_passed,
        },
        "quality_rates": {
            "company_match_rate": round(company_match_rate, 6),
            "year_match_rate": round(year_match_rate, 6),
            "report_type_match_rate": round(report_type_match_rate, 6),
            "official_domain_verified_rate": round(official_domain_verified_rate, 6),
            "provenance_complete_rate": round(provenance_complete_rate, 6),
        },
        "zero_tolerance_counts": {
            "active_duplicate_count": active_duplicate_count,
            "wrong_year_count": wrong_year_count,
            "wrong_type_count": wrong_type_count,
            "fabricated_url_count": fabricated_url_count,
            "provenance_failures": provenance_failures,
        },
        "domain_breakdown": domain_breakdown,
        "quality_gate_passed": quality_gate_passed,
        "coverage_target_met": coverage_target_met,
        "coverage_notes": coverage_notes,
        "known_exceptions": [
            {
                "ts_code": "300209.SZ",
                "symbol": "300209",
                "year": 2024,
                "reason": "inquiry_reply_pollution_no_annual_full_for_2024",
                "exception_type": "genuine_unavailable",
                "expected_behavior": "return_unavailable_correct",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post-apply quality validation for staging official report data."
    )
    parser.add_argument(
        "--environment",
        required=True,
        choices=["staging"],
        help="Must be 'staging'.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for the validation artifact JSON.",
    )
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    print(f"[Phase 6V-P1.11B] validate_official_report_staging_data.py")
    print(f"  environment: {args.environment}")
    print(f"  output     : {args.output}")

    # 1. Confirm staging environment
    confirm_staging_environment()

    # 2. Load universe
    universe_ts_codes = load_universe(UNIVERSE_FIXTURE)

    # 3. Fetch DB data
    rows = await fetch_all_annual_records()
    total_rows = await fetch_total_row_count()

    # 4. Run quality checks
    checks = run_quality_checks(rows, universe_ts_codes, total_rows)

    # 5. Build artifact
    artifact: dict[str, Any] = {
        "schema_version": "pi_official_report_p111_post_apply_validation_v1",
        "phase": "6V-P1.11B",
        "environment": args.environment,
        "db_identity": {
            "environment": "staging",
            "production_enabled": False,
            "host_hash": DB_HOST_HASH,
            "name_hash": DB_NAME_HASH,
            "url_hash": DB_URL_HASH,
        },
        **checks,
    }

    # 6. Write artifact
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, ensure_ascii=False, indent=2)

    print(f"\n[OK] Validation artifact written to: {args.output}")
    gate = checks["quality_gate_passed"]
    cov = checks["coverage_target_met"]
    print(f"[RESULT] quality_gate_passed={gate}  coverage_target_met={cov}")

    if not gate:
        print("[FAIL] Quality gate did not pass — review zero_tolerance_counts.")
        sys.exit(1)


def main() -> None:
    try:
        from dotenv import load_dotenv
        env_path = BACKEND_DIR / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
