# Pi-Compatible official_report_pdf Live Shadow Summary

- Agent: `official_report_pdf_pi_v1`
- Planned samples: 30
- Executed samples: 0
- Accepted samples: 0
- Scenario counts: `{}`
- Status/entity/year/type/url match: `None` / `None` / `None` / `None` / `None`
- Provenance completeness: `None`
- Unsupported URL count: `None`
- Deterministic LLM calls: `None`
- Latency p50/p95 ms: `None` / `None`
- Side effect count: `None`
- Context mutation / double writes / raw 500: `None` / `None` / `None`
- Browser acceptance: `{'executed': False, 'passed': False, 'notes': 'not_run'}`
- Gate passed: `False`
- Recommended for next authorization: `False`

## Blockers

- Live shadow samples incomplete: executed 0/30.
- Pi shadow env is not enabled with the explicit P1.2 values.
- PI_AGENT_SHADOW_DIAGNOSTICS_PATH is required for HTTP shadow result polling.
- PI_SHADOW_ACCEPTANCE_BASE_URL / --base-url is required for HTTP Chat acceptance.
- Database readiness check failed.
- No acceptance service account token/user id and local fixture creation was not explicitly allowed.

Production defaults remain disabled: `AGENT_EXECUTOR_MODE=legacy`, `PI_AGENT_SHADOW_ENABLED=false`, `CHAT_RUNTIME_MODE=legacy`, `authorized_agents=[]`.