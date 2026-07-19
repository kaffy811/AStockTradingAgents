# Pi-Compatible official_report_pdf Live Shadow Summary

- Agent: `official_report_pdf_pi_v1`
- Planned samples: 3
- Executed samples: 3
- Accepted samples: 3
- Scenario counts: `{'smoke_multi_turn_current_report': 1, 'smoke_explicit_stock_code': 1, 'smoke_ambiguity': 1}`
- Status/entity/year/type/url match: `1.0` / `None` / `None` / `None` / `None`
- Source URL / clarification match: `None` / `1.0`
- Provenance completeness: `1.0`
- Unsupported URL count: `None`
- Deterministic LLM calls: `None`
- Latency p50/p95 ms: `None` / `None`
- Side effect count: `0`
- Context mutation / double writes / raw 500: `None` / `0` / `0`
- Browser acceptance: `{'executed': False, 'passed': False, 'notes': 'not_run'}`
- Gate passed: `False`
- Smoke passed: `True`
- Recommended to run full 30: `True`
- Recommended for next authorization: `False`

## Blockers

- Gate thresholds were not fully met.

Production defaults remain disabled: `AGENT_EXECUTOR_MODE=legacy`, `PI_AGENT_SHADOW_ENABLED=false`, `CHAT_RUNTIME_MODE=legacy`, `authorized_agents=[]`.