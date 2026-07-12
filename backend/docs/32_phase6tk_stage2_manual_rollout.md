# Phase 6T-K Stage 2 Manual Rollout

Stage 2 financial fusion is allowlist-only and manually triggered.

Configuration template:

```env
COMPANY_V2_FINANCIAL_FUSION_ENABLED=true
COMPANY_V2_FINANCIAL_FUSION_ROLLOUT_PERCENT=0
COMPANY_V2_FINANCIAL_FUSION_SYMBOL_ALLOWLIST=601686,600519,300750,000725,000001
COMPANY_V2_FINANCIAL_FUSION_AUTO_RUN=false
COMPANY_V2_RAG_REPOSITORY_BACKEND=database
```

Rules:

- Do not enable Stage 3.
- Do not set `COMPANY_V2_FINANCIAL_FUSION_ROLLOUT_PERCENT` above `0`.
- Do not set `COMPANY_V2_FINANCIAL_FUSION_AUTO_RUN=true`.
- Page load may read readiness, eligibility, cached result availability, and job status only.
- Fusion runs only after a user clicks the manual official-report verification action.
- PDF report view remains independent from fusion and only depends on a valid CNINFO URL.

Manual job API:

- `POST /api/v2/company/{market}/{symbol}/financial-fusion/jobs`
- `GET /api/v2/company/{market}/{symbol}/financial-fusion/jobs/{job_id}`
- `GET /api/v2/company/{market}/{symbol}/financial-fusion/jobs/{job_id}/result`
- `POST /api/v2/company/{market}/{symbol}/financial-fusion/jobs/{job_id}/cancel`

The job status response is intentionally lightweight and must not include local file
paths, database connection strings, credentials, or stack traces.
