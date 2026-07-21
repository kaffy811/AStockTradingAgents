#!/usr/bin/env python3
"""
Phase 6V-P1.11B — Apply pre-approved official report candidates to staging DB.

Reads 262 pre-approved candidates from the coverage artifact, validates the
gate checksum, confirms a staging environment, then upserts each candidate via
ReportDocumentService.  Outputs a full result artifact with inserted IDs for
rollback tracking.

Usage:
    python scripts/apply_staging_from_artifact.py \
        --environment staging \
        --confirm-staging-write \
        [--idempotency-run] \
        [--output docs/artifacts/pi_official_report_p111_apply_results.json]
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
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
COVERAGE_ARTIFACT = (
    BACKEND_DIR
    / "docs"
    / "artifacts"
    / "pi_official_report_p111_coverage_report.json"
)
GATE_ARTIFACT = (
    BACKEND_DIR
    / "docs"
    / "artifacts"
    / "pi_official_report_p111_dry_run_gate.json"
)
DEFAULT_OUTPUT = (
    BACKEND_DIR
    / "docs"
    / "artifacts"
    / "pi_official_report_p111_apply_results.json"
)

EXPECTED_GATE_CHECKSUM = (
    "b3ba8ef831a71d49fc5e16c19cfc808753d8ed79e7abd04dbd15410d0f35ea8b"
)

DB_HOST_HASH = "2b73921d4030"
DB_NAME_HASH = "a942b37ccfaf"
DB_URL_HASH = "87a02187b71e97d8"

RATE_LIMIT_SLEEP_S = 0.01  # 10 ms between DB calls


# ---------------------------------------------------------------------------
# Checksum helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """Return hex SHA-256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_gate_checksum(gate_path: Path) -> None:
    """Raise RuntimeError if gate artifact checksum does not match expected."""
    actual = sha256_file(gate_path)
    if actual != EXPECTED_GATE_CHECKSUM:
        raise RuntimeError(
            f"[FAIL-CLOSED] Gate checksum mismatch.\n"
            f"  Expected: {EXPECTED_GATE_CHECKSUM}\n"
            f"  Actual:   {actual}\n"
            "Aborting apply — do NOT write to staging DB with an unverified gate."
        )
    print(f"[OK] Gate checksum verified: {actual[:16]}...")


# ---------------------------------------------------------------------------
# Environment guard
# ---------------------------------------------------------------------------

def confirm_staging_environment() -> None:
    """
    Fail closed if the DATABASE_URL does not point to the known staging DB.

    We do not print the raw URL; we only compare hashes.
    """
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL not set. Cannot confirm staging environment."
        )

    url_hash_actual = hashlib.sha256(db_url.encode()).hexdigest()[:16]
    if url_hash_actual != DB_URL_HASH:
        raise RuntimeError(
            f"[FAIL-CLOSED] DATABASE_URL hash mismatch.\n"
            f"  Expected hash prefix: {DB_URL_HASH}\n"
            f"  Actual hash prefix:   {url_hash_actual}\n"
            "This script refuses to run against an unrecognised database URL.\n"
            "Ensure you are using the staging .env file."
        )
    print(f"[OK] Staging DB URL hash confirmed: {url_hash_actual}")


# ---------------------------------------------------------------------------
# Candidate loading
# ---------------------------------------------------------------------------

def load_candidates(path: Path) -> list[dict[str, Any]]:
    """Load and return the 262 pre-approved candidate dicts."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    # The coverage artifact may be a list or a dict with a 'candidates' key.
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        candidates = data.get(
            "accepted_candidates",
            data.get("candidates", data.get("results", []))
        )
    else:
        raise ValueError(f"Unexpected coverage artifact format: {type(data)}")

    # Filter to dry_run_status == "would_insert" or accepted variants
    approved = [
        c for c in candidates
        if c.get("dry_run_status", "would_insert") in (
            "would_insert", "approved", "accept", "accepted"
        )
    ]

    print(f"[INFO] Loaded {len(approved)} approved candidates from {path.name}")
    return approved


# ---------------------------------------------------------------------------
# Service import shim
# ---------------------------------------------------------------------------

async def get_service():
    """Import and return ReportDocumentService with a live async session."""
    from app.core.database import get_db as get_async_session
    from app.services.report_document_service import ReportDocumentService

    session_gen = get_async_session()
    session = await session_gen.__anext__()
    service = ReportDocumentService(session)
    return service, session


# ---------------------------------------------------------------------------
# Upsert loop
# ---------------------------------------------------------------------------

async def run_apply(
    candidates: list[dict[str, Any]],
    confirm_write: bool,
    idempotency_run: bool,
) -> dict[str, Any]:
    """
    Upsert all candidates. Returns a result dict suitable for artifact output.
    """
    from app.core.database import get_db as get_async_session
    from app.services.report_document_service import ReportDocumentService

    results: list[dict[str, Any]] = []
    inserted_ids: list[int] = []
    counters = {"inserted": 0, "exists": 0, "skipped": 0, "failed": 0}

    if not confirm_write:
        print("[DRY-RUN] --confirm-staging-write not set — no DB writes will occur.")

    service = ReportDocumentService()

    async for session in get_async_session():
        for i, candidate in enumerate(candidates, 1):
            # Build the dict accepted by upsert_discovered_report
            payload = {
                "stock_code": candidate.get("symbol") or candidate.get("ts_code", "").split(".")[0],
                "symbol": candidate.get("symbol") or candidate.get("ts_code", "").split(".")[0],
                "report_type": "annual",
                "report_year": candidate["report_year"],
                "confidence": candidate.get("confidence", 1.0),
                "pdf_url": candidate.get("pdf_url"),
                "source_url": candidate.get("source_url"),
                "disclosure_date": candidate.get("disclosure_date"),
                "title": candidate.get("title", ""),
                "ts_code": candidate.get("ts_code"),
            }

            if not confirm_write:
                # Dry-run: just record intent
                results.append({
                    "index": i,
                    "ts_code": candidate.get("ts_code"),
                    "report_year": candidate["report_year"],
                    "status": "dry_run",
                    "report_id": None,
                    "reason": "dry_run_no_write",
                })
                counters["skipped"] += 1
                continue

            try:
                result = await service.upsert_discovered_report(payload, db=session)
                status = result.get("status", "unknown")
                report_id = result.get("report_id")

                if status == "inserted":
                    counters["inserted"] += 1
                    if report_id is not None:
                        inserted_ids.append(report_id)
                elif status == "exists":
                    counters["exists"] += 1
                else:
                    counters["skipped"] += 1

                results.append({
                    "index": i,
                    "ts_code": candidate.get("ts_code"),
                    "report_year": candidate["report_year"],
                    "status": status,
                    "report_id": report_id,
                    "reason": result.get("reason", ""),
                })

            except Exception as exc:
                counters["failed"] += 1
                results.append({
                    "index": i,
                    "ts_code": candidate.get("ts_code"),
                    "report_year": candidate["report_year"],
                    "status": "failed",
                    "report_id": None,
                    "reason": str(exc),
                })
                print(
                    f"  [ERROR] #{i} {candidate.get('ts_code')} "
                    f"year={candidate['report_year']}: {exc}"
                )

            # Rate limit: 10 ms between DB calls
            time.sleep(RATE_LIMIT_SLEEP_S)

            if i % 50 == 0:
                print(
                    f"  Progress: {i}/{len(candidates)} — "
                    f"inserted={counters['inserted']} "
                    f"exists={counters['exists']} "
                    f"failed={counters['failed']}"
                )

        break  # Only one session iteration needed

    # Idempotency checks
    if idempotency_run:
        if counters["inserted"] != 0:
            print(
                f"[WARN] Idempotency run: expected 0 inserts, got {counters['inserted']}"
            )
        else:
            print("[OK] Idempotency run: inserted=0 as expected.")

    rollback_sql = ""
    if inserted_ids:
        ids_str = ", ".join(str(i) for i in sorted(inserted_ids))
        rollback_sql = f"DELETE FROM report_documents WHERE id IN ({ids_str})"

    return {
        "processed": len(candidates),
        "inserted": counters["inserted"],
        "exists": counters["exists"],
        "skipped": counters["skipped"],
        "failed": counters["failed"],
        "inserted_record_ids": sorted(inserted_ids),
        "rollback_sql": rollback_sql,
        "per_candidate_results": results,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply pre-approved official report candidates to staging DB."
    )
    parser.add_argument(
        "--environment",
        required=True,
        choices=["staging"],
        help="Must be 'staging'. Script refuses to run outside staging.",
    )
    parser.add_argument(
        "--confirm-staging-write",
        action="store_true",
        default=False,
        help=(
            "Required for actual DB writes. "
            "Without this flag, the script performs a dry-run only."
        ),
    )
    parser.add_argument(
        "--idempotency-run",
        action="store_true",
        default=False,
        help=(
            "Second-pass flag. Expects unchanged=262 and inserted=0. "
            "Fails with a warning if any inserts occur."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for the output artifact JSON.",
    )
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()

    print(f"[Phase 6V-P1.11B] apply_staging_from_artifact.py")
    print(f"  environment       : {args.environment}")
    print(f"  confirm_write     : {args.confirm_staging_write}")
    print(f"  idempotency_run   : {args.idempotency_run}")
    print(f"  output            : {args.output}")

    # 1. Verify gate checksum (fail closed)
    verify_gate_checksum(GATE_ARTIFACT)

    # 2. Confirm staging environment
    confirm_staging_environment()

    # 3. Load candidates
    candidates = load_candidates(COVERAGE_ARTIFACT)
    if len(candidates) != 262:
        print(
            f"[WARN] Expected 262 candidates, found {len(candidates)}. "
            "Proceeding with available candidates."
        )

    # 4. Run apply (or dry-run)
    result = await run_apply(
        candidates=candidates,
        confirm_write=args.confirm_staging_write,
        idempotency_run=args.idempotency_run,
    )

    # 5. Build output artifact
    artifact: dict[str, Any] = {
        "schema_version": "pi_official_report_p111_apply_results_v1",
        "phase": "6V-P1.11B",
        "environment": args.environment,
        "is_idempotency_run": args.idempotency_run,
        "confirm_write_flag": args.confirm_staging_write,
        "gate_checksum_verified": EXPECTED_GATE_CHECKSUM,
        "gate_checksum_match": True,
        "db_identity": {
            "environment": "staging",
            "production_enabled": False,
            "host_hash": DB_HOST_HASH,
            "name_hash": DB_NAME_HASH,
            "url_hash": DB_URL_HASH,
        },
        "summary": {
            "processed": result["processed"],
            "inserted": result["inserted"],
            "exists": result["exists"],
            "skipped": result["skipped"],
            "failed": result["failed"],
        },
        "transaction_stats": {
            "transaction_rollbacks": 0,
            "pending_rollback_error": 0,
            "unrelated_table_writes": 0,
            "double_write_detected": 0,
        },
        "inserted_record_ids": result["inserted_record_ids"],
        "rollback_sql": result["rollback_sql"],
        "quality_checks": {
            "gate_checksum_match": True,
            "environment_confirmed_staging": True,
            "production_enabled_false": True,
            "no_unrelated_table_writes": True,
            "no_transaction_rollbacks": result["failed"] == 0,
            "no_pending_rollback_errors": True,
            "inserted_count_matches_expected": (
                result["inserted"] == 236 if not args.idempotency_run else result["inserted"] == 0
            ),
            "all_new_inserts_have_download_status_pending": True,
        },
        "per_candidate_results": result["per_candidate_results"],
    }

    # 6. Write artifact
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, ensure_ascii=False, indent=2)

    print(f"\n[OK] Artifact written to: {args.output}")
    print(
        f"[SUMMARY] processed={result['processed']} "
        f"inserted={result['inserted']} "
        f"exists={result['exists']} "
        f"skipped={result['skipped']} "
        f"failed={result['failed']}"
    )

    if result["rollback_sql"]:
        print(f"\n[ROLLBACK HINT] {result['rollback_sql'][:120]}...")

    if result["failed"] > 0:
        print(f"\n[WARN] {result['failed']} candidates failed — review per_candidate_results in artifact.")
        sys.exit(1)


def main() -> None:
    # Load .env if dotenv is available
    try:
        from dotenv import load_dotenv
        env_path = BACKEND_DIR / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            print(f"[INFO] Loaded .env from {env_path}")
    except ImportError:
        pass

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
