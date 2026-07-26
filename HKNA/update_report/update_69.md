---
目前完成的工作汇总：

已完成

1. `backend/scripts/backfill_financial_metric_provenance.py`
- 将 provenance backfill 收口为默认 dry-run。
- 新增 `--apply` 与 `--confirm-symbol` 双重确认，避免误触发全市场或单股票非确认写入。
- 写入路径只委托既有 `build_company_history_dashboard` refresh/cache，不新增第二套持久化机制。
- 输出 coverage、idempotency、rollback、安全脱敏字段，便于 live 环境验收。
- 将 provider 执行阶段 stdout 隔离到 stderr，保持 JSON artifact 可解析。

2. `backend/tests/fundamental/test_phase6u_e1_3_4_financial_provenance.py`
- 新增 dry-run 零写入、apply 缺确认拒绝写入、确认后触发既有 refresh path、artifact 脱敏测试。
- 保留 legacy provenance missing 不自动升级为 verified 的严格行为。

3. `backend/docs/artifacts/financial_provenance_*.json`
- 生成本地 E1.3.5 artifacts：
  - `financial_provenance_backfill_dry_run.json`
  - `financial_provenance_backfill_results.json`
  - `financial_provenance_sample_coverage.json`
  - `financial_provenance_page_chat_consistency.json`
  - `financial_provenance_audit_000858_revenue.json`
  - `financial_provenance_audit_000858_roe.json`
- 本地 preflight 显示 `environment_ready=false`，因此未执行 apply。
- 非沙箱 preflight 后 Provider 可部分访问，但 Postgres/RAG 仍未 ready，因此仍未执行 apply。
- 000858 revenue dry-run 已取得 2025 annual/CNY provenance；000858 ROE 的 2025 annual 目标候选仍不可用，继续安全标记 unverified。
- 六家公司 dry-run 汇总：sample_count=6，write_count=0，rows_checked=6，verified_metrics=16，legacy_unverified=9。

4. 验证结果
- Targeted provenance/comparability：17 passed。
- Backend default full：3291 passed, 15 skipped。
- Frontend Vitest：679 passed。
- Frontend build：passed。

---
下一步：你需要操作

第一步：在阿里云首尔或其他稳定外部环境配置真实 Provider/DB/Redis secrets，运行：
`cd backend && python scripts/live_environment_preflight.py --out docs/artifacts/live_environment_preflight.json`

第二步：preflight 通过后，对六家公司逐个 dry-run：
`python scripts/backfill_financial_metric_provenance.py --market CN --symbol 000858 --report-year 2025 --dry-run --output docs/artifacts/financial_provenance_backfill_dry_run_000858.json`

第三步：只有 dry-run 输出 provenance 完整且无冲突时，单公司显式执行 apply：
`python scripts/backfill_financial_metric_provenance.py --market CN --symbol 000858 --report-year 2025 --apply --confirm-symbol 000858 --output docs/artifacts/financial_provenance_backfill_apply_000858.json`

第四步：重复执行同一 apply，确认第二次 write count 为 0 或 metadata no-op。

第五步：重新打开 Company 页面和 Chat 比较流程，确认 Provider -> Company 页面 -> CompanyChatDataService 的 period/unit/source metadata 不丢失。
