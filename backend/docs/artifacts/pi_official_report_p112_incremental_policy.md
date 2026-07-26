# Official Report Incremental Refresh Policy — Phase 6V-P1.12

## Overview
Incremental refresh replaces full-universe ETL with a targeted, since-based approach.

## Commands
### Dry-run (default):
python scripts/ingest_official_annual_reports.py \
  --environment staging \
  --universe backend/tests/fixtures/official_report_staging_universe_v1.json \
  --incremental \
  --since 2026-01-01 \
  --dry-run

### Apply:
python scripts/ingest_official_annual_reports.py \
  --environment staging \
  --universe backend/tests/fixtures/official_report_staging_universe_v1.json \
  --incremental \
  --since 2026-01-01 \
  --apply \
  --confirm-staging-write

## Candidate Classification Rules
| Class | Rule |
|---|---|
| new_document | pdf_url not in DB AND ts_code+year+type not in DB |
| unchanged_document | pdf_url match AND metadata unchanged |
| metadata_update | pdf_url match AND title/disclosure_date changed |
| revised_document | pdf_url differs, same ts_code+year+type, newer disclosure_date |
| superseding_document | explicit revision note in title (修订版/更正) |
| inactive_document | provider marks as withdrawn/corrected |
| rejected_document | fails is_annual_full() OR validate_pdf_url() |
| provider_pollution | title matches exclusion keywords |
| unsupported_report_type | semi/q1/q3/esg/csr |
| unverifiable_url | URL not on cninfo allowlist |

## Title-Change Rule
- Title variation alone (e.g. spacing, typo fix) does NOT trigger new_document
- URL query parameter change does NOT trigger new_document
- Provider fetch timestamp change does NOT trigger new_document
- Only new pdf_url or explicit revision/supersession counts as new_document

## Superseded Handling
1. New record confirmed annual full
2. Same company/year/type
3. Newer disclosure_date or explicit revision marker
4. New → active=true; Old → superseded=true
5. Old record preserved with provenance intact
6. Only one active record per symbol/year/type

## Since/Cursor/Resume
- --since accepts ISO date or datetime
- cursor written to run artifact after each batch
- resume: pass --run-id of prior interrupted run
- max_retries=3 per symbol before marking provider_error
- rate_limit=2 req/s per provider

## Idempotency
- Second run with same --since: inserted=0
- candidate checksum must be stable
- no duplicate actives created
