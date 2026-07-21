# Official Report Stale Detection Policy — Phase 6V-P1.12

## Stale Types

### S1: URL Failure
- official URL returns HTTP 404 or 410 (permanent)
- provider explicitly marks document as withdrawn
- Source page no longer exists
- Direct PDF inaccessible with no replacement
- Action: stale_review → inactive (after confirmation)

### S2: Superseded by New Version
- Same company/year/type has a confirmed newer revision
- Old record not yet marked superseded
- Action: mark old as superseded=true, new as active=true

### S3: Provenance Expired/Incomplete
- provider_identity missing
- verification_status anomalous
- official_domain_verified missing
- Action: stale_review, re-verification required

### S4: Structural Conflict
- title_year ≠ report_year
- report_type ≠ title classification
- symbol/company mismatch
- Action: rejected, manual review

### S5: Long Unverified
- Not re-verified in 180+ days
- URL still accessible but metadata unconfirmed
- Action: stale_review (NOT auto-inactive)

## URL Health Check Rules

### Allowed Methods
- HTTP HEAD request
- HTTP Range GET (first 1KB only)
- Provider metadata API
- Redirect chain check (max 3 hops)

### Classification
| Status | Condition |
|---|---|
| healthy | 200/206, cninfo domain, PDF content-type |
| temporary_failure | 5xx, timeout, connection reset |
| permanent_failure | 404, 410, or 3+ permanent redirects away |
| redirected_official | Redirect to another cninfo subdomain |
| redirected_third_party | Redirect to non-cninfo domain |
| unverifiable | Response ambiguous after 3 retries |

### Rules
- NEVER download complete PDF body
- NEVER save response body
- Temporary failure ≠ inactive (min 3 checks before stale_review)
- Single timeout ≠ inactive
- Only permanent_failure or third_party redirect can trigger inactive path
- Physical delete NEVER allowed

## Superseded Rules
1. Confirm new record is annual full
2. Verify same ts_code/year/report_type
3. Confirm newer disclosure_date or explicit revision marker
4. Set new active=true
5. Set old superseded=true
6. Both records preserved with full provenance
7. Selection returns only active record
8. Only ONE active record per symbol/year/type at all times
9. If ambiguous: mark manual_review, do NOT auto-switch
