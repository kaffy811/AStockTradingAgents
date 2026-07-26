# official_report_pdf P1.6.7 Browser Acceptance

- Acceptance SHA: `49282435fafb534a7c98b646913f027814323300`
- Environment: `local_live` (frontend 5173 → backend 8022, same clean clone)
- Browser: headless Google Chrome (Playwright, scratch venv — repo dependencies untouched)
- Identity: dedicated acceptance account, runtime-only token, injected via localStorage like the auth store
- Preflight: `{'backend_health': True, 'login_ok': True, 'auth_me_ok': True, 'frontend_reachable': True, 'notes': [], 'chat_ui_loaded': True, 'initial_console_errors': 1, 'shadow_ui_components': 0}`
- HTTP 5xx during all cases: `{'500': 0, '503': 0}`
- Overall passed: `False`

| Case | Passed | Loading | Assistant msgs | Links | Official domain | Console errors | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B01 | True | True | 2 | 1 | True | 0 | assistant_after_turn1=1 |
| B02 | True | True | 1 | 1 | True | 0 | explicit 000858 2025 annual |
| B03 | False | True | 1 | 0 | True | 0 | Legacy clarification answer does not display 平安银行/中国平安 candidate list (pre-existing Legacy UX defect; Pi shadow produced correct deduplicate |
| B04 | True | True | 1 | 0 | True | 0 | User-visible copy: 当前官方报告 PDF 工具仅支持年度报告；未返回其他期间链接。 — reasonable, no internal error code. |
| B05 | True | True | 1 | 0 | True | 0 | User-visible copy: 未找到 CN/999999 的可用正式财报。 — reasonable unavailable, no fabrication. |

## Blocker

- **B03**: Legacy clarification for ambiguous 平安 does not display the 平安银行/中国平安 candidate list (pre-existing Legacy UX defect; Pi shadow produced correct deduplicated candidates). All safety sub-checks passed (no auto-selection, no PDF URL, no internal status leak, no console errors).

No tokens, full user ids, screenshots or Authorization headers are stored in this artifact.
