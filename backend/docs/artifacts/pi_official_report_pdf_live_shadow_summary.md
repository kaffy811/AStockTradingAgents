# Pi-Compatible official_report_pdf Live Shadow Summary

- Agent: `official_report_pdf_pi_v1`
- Planned samples: 30
- Executed samples: 30
- Accepted samples: 15
- Scenario counts: `{'multi_turn_current_report': 3, 'explicit_company_name': 7, 'explicit_stock_code': 6, 'report_type': 5, 'ambiguity': 2, 'missing': 7}`
- Status/entity/year/type/url match: `0.6333` / `1.0` / `1.0` / `1.0` / `0.8667`
- Source URL / clarification match: `1.0` / `1.0`
- Provenance completeness: `1.0`
- Unsupported URL count: `0`
- Deterministic LLM calls: `0`
- Latency p50/p95 ms: `914` / `1444`
- Side effect count: `0`
- Context mutation / double writes / raw 500: `0` / `0` / `0`
- Browser acceptance: `{'executed': False, 'passed': False, 'notes': 'not_run'}`
- Gate passed: `False`
- Smoke passed: `False`
- Recommended to run full 30: `False`
- Recommended for next authorization: `False`

## Blockers

- Gate thresholds were not fully met.

Production defaults remain disabled: `AGENT_EXECUTOR_MODE=legacy`, `PI_AGENT_SHADOW_ENABLED=false`, `CHAT_RUNTIME_MODE=legacy`, `authorized_agents=[]`.