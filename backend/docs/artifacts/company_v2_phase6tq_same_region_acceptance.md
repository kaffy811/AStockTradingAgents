# Phase 6T-Q Same-Region Acceptance

- status: passed
- runner provisioned: true
- runner region: ap-northeast-2
- HTTP acceptance: true
- warmup total: 10
- samples total: 50
- create p50: 27.873 ms
- create p95: 29.707 ms
- create min: 27.122 ms
- create max: 236.267 ms
- auto_run: false
- rollout_percent: 0
- manual jobs remained queued: true
- jobs cancelled: 50
- duplicate active jobs: 0
- preexisting active jobs found: 5
- preexisting active jobs cancelled: 5
- active jobs after cleanup: 0
- cleanup completed: true

This result confirms allowlist manual admission only and does not authorize
Stage 3 or automatic rollout.
