---
目前完成的工作汇总：

已完成

1. Phase 6T-J2 单位上下文收尾
- 修复点：table-level 单位上下文恢复，单位 unknown 时禁止 value_conflict，cache key 纳入 official-extractor-unit-context-v2。
- 300750 net_profit：raw=76,786,309 千元，scale=1000，normalized=76,786,309,000 CNY，最终 classification=verified。

2. 真实 Stage 2 fusion audit
- real_execution=true，mock=false，repository_backend=database，persistent=true，report_ids=2,3,4,5。
- symbols_total=4，reports_ready=4，reports_failed=0，fields_total=40。
- value_conflict=0，false_conflict=0，cross_symbol/report leakage=0，citation/source trace blocking issue=0。

3. 600519 revenue 回归
- 仍为 definition_mismatch：structured=main_business_revenue / 营业总收入，official=营业收入。
- confirmed_value_conflict=false，不进入正式 conflict queue。

4. Review queue resolution
- 旧 300750 net_profit value_conflict 作为 resolved_false_positive 记录在 Phase 6T-J2 artifacts。
- resolution_reason=table_level_unit_context_restored，active review queue size=0。

5. Artifacts
- backend/docs/artifacts/company_v2_official_extractor_unit_context_phase6tj2.json/.md
- backend/docs/artifacts/company_v2_financial_fusion_stage2_audit_phase6tj.json/.md
- backend/docs/artifacts/company_v2_phase6tj_final_gate.json/.md
- backend/docs/artifacts/company_v2_financial_fusion_stage2_multistock_phase6tj.json final note

6. 测试
- Targeted Phase 6T-J2/rollout/unit tests: 29 passed。
- Backend full regression: 3026 passed, 236 warnings。
- Frontend npm test: 54 files / 635 tests passed。
- Frontend npm run build: passed；保留 Vite chunk-size warning。

---
下一步：你需要操作

第一步：Stage 2 仅允许 allowlist/manual rollout；保持 rollout_percent=0、auto_run=false，不进入 Stage 3。
第二步：如需发布前复核，读取 backend/docs/artifacts/company_v2_phase6tj_final_gate.json。
第三步：如需重复验证，运行 cd backend && .venv/bin/python -m pytest -q；cd frontend && npm test && npm run build。
