# Pi Shadow Live Environment Bootstrap

- Phase: `6V-P1.5`
- Environment type: `local_live`
- Branch: `release/demo-staging`
- Commit SHA: `bbc3379790b9a5308ed0089b98ad276b44d71adf`
- Backend: `127.0.0.1:8000`, started from the project backend with explicit shadow-only environment variables
- Backend env: `CHAT_RUNTIME_MODE=legacy`, `AGENT_EXECUTOR_MODE=pi_compatible_shadow`, `PI_AGENT_SHADOW_ENABLED=true`, `PI_AGENT_ALLOWED_AGENTS=official_report_pdf_pi_v1`
- Default config remains disabled: `AGENT_EXECUTOR_MODE=legacy`, `PI_AGENT_SHADOW_ENABLED=false`, `CHAT_RUNTIME_MODE=legacy`, `authorized_agents=[]`
- Diagnostics path: private temp path, present=true, not under `frontend/public`
- Acceptance identity: dedicated local_live test user created through normal `/api/v1/auth/register` and `/api/v1/auth/login`; token_present=true; full user id/token not stored
- DB readiness: backend health passed; DB passed; official report metadata service passed; resolver ready
- SQL logging: `DATABASE_SQL_ECHO=false`, `DATABASE_SQL_HIDE_PARAMETERS=true`; bind parameter exposure count=0
- Preflight: passed after backend restart and fresh short-lived acceptance token
- Smoke: fixed P1.5 smoke set executed through real HTTP/SSE; planned=3, executed=3, accepted=3
- Full 30-case run: not executed in this phase by design
- Browser acceptance: not executed in this phase

Formal Pi path remains disabled: `pi_executor_enabled=false`, `authorized_agents=[]`, `decision=do_not_enable_pi_compatible`.
