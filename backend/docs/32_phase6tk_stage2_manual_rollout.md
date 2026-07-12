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

## Phase 6T-Q Same-Region Acceptance

Use the same-region runner only. Cross-region measurements are diagnostic and do
not replace acceptance.

Prerequisites:

- `SECRET_KEY` set
- `DATABASE_URL` set
- `COMPANY_V2_FINANCIAL_FUSION_SYMBOL_ALLOWLIST=601686,600519,300750,000725,000001`
- `COMPANY_V2_FINANCIAL_FUSION_AUTO_RUN=false`
- `COMPANY_V2_FINANCIAL_FUSION_ROLLOUT_PERCENT=0`

Start the API on localhost:

```bash
cd backend
source .venv/bin/activate
source ~/.tradingagents_env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run acceptance:

```bash
cd backend
source .venv/bin/activate
source ~/.tradingagents_env
.venv/bin/python scripts/company_v2_financial_fusion_phase6tq_acceptance.py \
  --base-url http://127.0.0.1:8000 \
  --warmup 10 \
  --samples 50 \
  --symbols 601686,600519,300750,000725,000001 \
  --out-json docs/artifacts/company_v2_phase6tq_same_region_acceptance.json \
  --out-md docs/artifacts/company_v2_phase6tq_same_region_acceptance.md
```

Gate conditions:

- `p50 <= 300 ms`
- `p95 <= 1000 ms`
- live Supabase tests pass
- active jobs are cleaned up to `0`

Cleanup rules:

- Only cancel jobs created by the acceptance script by default.
- Do not cancel unknown production jobs unless `--cleanup-known-job-ids` is
  explicitly provided.
- Check active queued/running jobs before release.

Do not enable automatic execution.
Do not authorize Stage 3.
